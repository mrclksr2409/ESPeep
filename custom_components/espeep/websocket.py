"""WebSocket commands behind the ESPeep sidebar panel.

Naming and adding products is open to every user, like the actions are:
anyone in the household should be able to name what they scanned. Deleting
and bulk imports need an administrator.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
import voluptuous as vol

from .logic import clean_name, normalize_ean
from .lookup import ProductLookupError, async_lookup
from .runtime import async_named, get_data, loaded_scanners


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Register the panel's commands."""
    for command in (
        ws_subscribe,
        ws_set,
        ws_delete,
        ws_dismiss,
        ws_import,
        ws_lookup,
        ws_add_to_list,
        ws_learn,
    ):
        websocket_api.async_register_command(hass, command)


def _snapshot(hass: HomeAssistant) -> dict[str, Any]:
    return {
        **get_data(hass).store.as_dict(),
        "scanners": [
            {
                "entry_id": s.entry.entry_id,
                "device_id": s.device_id,
                "name": s.device_name,
            }
            for s in loaded_scanners(hass)
        ],
    }


def _ean_or_error(
    connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> str | None:
    ean = normalize_ean(msg["ean"])
    if ean is None:
        connection.send_error(
            msg["id"], "invalid_ean", "Kein gültiger EAN/UPC-Barcode (Prüfziffer?)"
        )
    return ean


@websocket_api.websocket_command({vol.Required("type"): "espeep/subscribe"})
@callback
def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send the whole database now and again after every change."""

    @callback
    def forward() -> None:
        connection.send_message(websocket_api.event_message(msg["id"], _snapshot(hass)))

    connection.subscriptions[msg["id"]] = get_data(hass).store.async_add_listener(
        forward
    )
    connection.send_result(msg["id"])
    forward()


@websocket_api.websocket_command(
    {
        vol.Required("type"): "espeep/set",
        vol.Required("ean"): str,
        vol.Required("name"): str,
        vol.Optional("brand", default=""): str,
        vol.Optional("quantity", default=""): str,
        # Renaming changes the key; the old one goes away.
        vol.Optional("previous_ean"): str,
    }
)
@callback
def ws_set(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Create or edit a product."""
    if (ean := _ean_or_error(connection, msg)) is None:
        return
    if not (name := clean_name(msg["name"])):
        connection.send_error(msg["id"], "invalid_name", "Name darf nicht leer sein")
        return
    store = get_data(hass).store
    previous = msg.get("previous_ean")
    if previous and previous != ean:
        store.async_remove(previous)
    product = store.async_set(ean, name, brand=msg["brand"], quantity=msg["quantity"])
    async_named(hass, ean)
    connection.send_result(msg["id"], {"ean": ean, "product": product})


@websocket_api.websocket_command(
    {vol.Required("type"): "espeep/delete", vol.Required("ean"): str}
)
@websocket_api.require_admin
@callback
def ws_delete(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Forget a product."""
    connection.send_result(
        msg["id"], {"removed": get_data(hass).store.async_remove(msg["ean"])}
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "espeep/dismiss", vol.Required("ean"): str}
)
@callback
def ws_dismiss(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Drop a barcode from the unknown list."""
    connection.send_result(
        msg["id"], {"removed": get_data(hass).store.async_dismiss_unknown(msg["ean"])}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "espeep/import",
        vol.Required("products"): {str: str},
    }
)
@websocket_api.require_admin
@callback
def ws_import(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Bulk import barcode -> name pairs; reports which lines were rejected."""
    valid: dict[str, str] = {}
    rejected: list[str] = []
    for raw_ean, raw_name in msg["products"].items():
        ean = normalize_ean(raw_ean)
        name = clean_name(raw_name)
        if ean is None or not name:
            rejected.append(raw_ean)
        else:
            valid[ean] = name
    imported = get_data(hass).store.async_import(valid)
    connection.send_result(msg["id"], {"imported": imported, "rejected": rejected})


@websocket_api.websocket_command(
    {vol.Required("type"): "espeep/lookup", vol.Required("ean"): str}
)
@websocket_api.async_response
async def ws_lookup(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Ask the online databases, without storing anything."""
    if (ean := _ean_or_error(connection, msg)) is None:
        return
    language = str(hass.config.language or "en").split("-")[0].lower()
    try:
        info = await async_lookup(hass, ean, language)
    except ProductLookupError as err:
        connection.send_error(msg["id"], "lookup_failed", str(err))
        return
    connection.send_result(
        msg["id"], {"ean": ean, "product": asdict(info) if info else None}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "espeep/add_to_list",
        vol.Required("ean"): str,
        vol.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_add_to_list(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Handle a barcode exactly like a scan — the panel's "Scan" button."""
    if (ean := _ean_or_error(connection, msg)) is None:
        return
    scanners = loaded_scanners(hass)
    if entry_id := msg.get("entry_id"):
        scanners = [s for s in scanners if s.entry.entry_id == entry_id]
    if not scanners:
        connection.send_error(msg["id"], "no_scanner", "Kein ESPeep eingerichtet")
        return
    result = await scanners[0].async_handle_scan(ean)
    connection.send_result(msg["id"], asdict(result))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "espeep/learn",
        vol.Required("ean"): str,
        vol.Required("name"): str,
        vol.Optional("entry_id"): str,
    }
)
@websocket_api.async_response
async def ws_learn(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Name an unknown barcode and put it on the list, like a phone reply."""
    if (ean := _ean_or_error(connection, msg)) is None:
        return
    if not clean_name(msg["name"]):
        connection.send_error(msg["id"], "invalid_name", "Name darf nicht leer sein")
        return
    scanners = loaded_scanners(hass)
    entry_id = msg.get("entry_id") or get_data(hass).pending.get(ean)
    preferred = [s for s in scanners if s.entry.entry_id == entry_id]
    scanners = preferred or scanners
    if not scanners:
        connection.send_error(msg["id"], "no_scanner", "Kein ESPeep eingerichtet")
        return
    result = await scanners[0].async_learn(ean, msg["name"])
    connection.send_result(msg["id"], asdict(result))
