"""What happens when one ESPeep device scans a barcode."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import logging
from typing import Any

from homeassistant.components.todo import TodoListEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, ATTR_SUPPORTED_FEATURES
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_DEVICE_ID,
    CONF_INCLUDE_BRAND,
    CONF_LANGUAGE,
    CONF_NOTIFY_SERVICE,
    CONF_ONLINE_LOOKUP,
    CONF_TODO_ENTITY,
    DEFAULT_INCLUDE_BRAND,
    DEFAULT_ONLINE_LOOKUP,
    DEVICE_ACTION,
    DOMAIN,
    NOTIFY_ACTION_PREFIX,
    PANEL_URL_PATH,
    SCAN_EVENT,
    SCANNED_EVENT,
    SIGNAL_SCAN_HANDLED,
    SOURCE_ONLINE,
)
from .logic import clean_name, compose_label, node_action_name, normalize_ean
from .lookup import ProductLookupError, async_lookup
from .runtime import async_named, notification_id
from .store import ProductStore

_LOGGER = logging.getLogger(__name__)

# Outcomes of a scan. Also the values of the `result` field of espeep_scanned.
RESULT_ADDED = "added"
RESULT_ALREADY_LISTED = "already_listed"
RESULT_RECOGNISED = "recognised"
RESULT_UNKNOWN = "unknown"
RESULT_LOOKUP_FAILED = "lookup_failed"
RESULT_LIST_FAILED = "list_failed"
RESULT_INVALID = "invalid"


@dataclass(slots=True)
class ScanResult:
    """Outcome of one scan, as shown on sensors and in the espeep_scanned event."""

    ean: str
    result: str
    name: str = ""
    source: str = ""


class EspeepScanner:
    """Binds one ESPHome device to the shared product database and a to-do list."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: ProductStore,
        pending: dict[str, str],
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.store = store
        # Shared across scanners: barcode -> entry that asked for its name.
        self._pending = pending
        self.device_id: str = entry.data[CONF_DEVICE_ID]
        self.node_name: str | None = None
        # Toggled by the "Add to shopping list" switch. Off turns ESPeep into a
        # pure catalogue tool: scans resolve and get learned, nothing is listed.
        self.add_to_list = True
        self.last_result: ScanResult | None = None
        # Scans are processed one at a time, otherwise two quick scans of the
        # same product both pass the "already on the list" check.
        self._lock = asyncio.Lock()

    @property
    def options(self) -> dict[str, Any]:
        """Settings from the options flow."""
        return {**self.entry.data, **self.entry.options}

    @property
    def device_name(self) -> str:
        """Name of the scanner device, for logs and history."""
        if device := dr.async_get(self.hass).async_get(self.device_id):
            return device.name_by_user or device.name or self.entry.title
        return self.entry.title

    @callback
    def async_start(self) -> None:
        """Start listening for scans of this device."""
        self.node_name = self._node_name_from_esphome()
        self.entry.async_on_unload(
            self.hass.bus.async_listen(SCAN_EVENT, self._async_scan_event)
        )

    def _node_name_from_esphome(self) -> str | None:
        """The ESPHome node name decides the name of the device's API action.

        The firmware sends it along with every scan, but looking it up here
        means the display callback works for the very first scan too.
        """
        device = dr.async_get(self.hass).async_get(self.device_id)
        if device is None:
            return None
        for entry_id in device.config_entries:
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry and entry.domain == "esphome":
                return entry.data.get("device_name")
        return None

    @callback
    def _async_scan_event(self, event: Event) -> None:
        if event.data.get("device_id") != self.device_id:
            return
        if node_name := event.data.get("device_name"):
            self.node_name = str(node_name)
        self.entry.async_create_background_task(
            self.hass,
            self.async_handle_scan(str(event.data.get("ean", ""))),
            f"{DOMAIN} scan",
        )

    async def async_handle_scan(self, raw_ean: str) -> ScanResult:
        """Resolve a barcode, put it on the list and tell the device."""
        async with self._lock:
            result = await self._async_resolve_and_list(raw_ean)
        self._async_publish(result)
        return result

    async def async_learn(self, raw_ean: str, name: str) -> ScanResult:
        """Store a name for a barcode and list it as if it had just been scanned."""
        ean = normalize_ean(raw_ean)
        name = clean_name(name)
        if ean is None or not name:
            return ScanResult(ean=str(raw_ean), result=RESULT_INVALID)
        self.store.async_set(ean, name)
        async_named(self.hass, ean)
        async with self._lock:
            result = await self._async_list(ean, name, "user")
        self._async_publish(result)
        return result

    async def _async_resolve_and_list(self, raw_ean: str) -> ScanResult:
        ean = normalize_ean(raw_ean)
        if ean is None:
            _LOGGER.warning("Ignoring invalid barcode %r", raw_ean)
            await self._async_show("error", "Ungültiger Code", raw_ean)
            return ScanResult(ean=raw_ean, result=RESULT_INVALID)

        options = self.options
        include_brand = options.get(CONF_INCLUDE_BRAND, DEFAULT_INCLUDE_BRAND)

        # 1. Our own table. It holds everything you named and every product an
        #    online database resolved before, so known barcodes never leave HA.
        if product := self.store.get(ean):
            label = (
                product["name"]
                if product["source"] != SOURCE_ONLINE
                else compose_label(product["name"], product["brand"], include_brand)
            )
            return await self._async_list(ean, label, product["source"])

        # 2. Online databases.
        if options.get(CONF_ONLINE_LOOKUP, DEFAULT_ONLINE_LOOKUP):
            try:
                info = await async_lookup(self.hass, ean, self._language)
            except ProductLookupError:
                await self._async_show("error", "Keine Verbindung", ean)
                self.store.async_record_scan(
                    ean, "", RESULT_LOOKUP_FAILED, self.device_name
                )
                return ScanResult(ean=ean, result=RESULT_LOOKUP_FAILED)
            if info is not None:
                self.store.async_set(
                    ean,
                    info.name,
                    brand=info.brand,
                    quantity=info.quantity,
                    source=SOURCE_ONLINE,
                )
                label = compose_label(info.name, info.brand, include_brand)
                return await self._async_list(ean, label, SOURCE_ONLINE)

        # 3. Nobody knows it: remember it and ask.
        self.store.async_mark_unknown(ean)
        self.store.async_record_scan(ean, "", RESULT_UNKNOWN, self.device_name)
        await self._async_ask_for_name(ean)
        await self._async_show("unknown", "In HA benennen", ean)
        return ScanResult(ean=ean, result=RESULT_UNKNOWN)

    async def _async_list(self, ean: str, label: str, source: str) -> ScanResult:
        if not self.add_to_list:
            result = RESULT_RECOGNISED
            detail = "Erkannt"
        else:
            try:
                added = await self._async_add_to_list(label, ean)
            except HomeAssistantError as err:
                _LOGGER.error("Could not add %s to the shopping list: %s", label, err)
                await self._async_show("error", "Liste nicht erreichbar", label)
                self.store.async_record_scan(
                    ean, label, RESULT_LIST_FAILED, self.device_name
                )
                return ScanResult(ean, RESULT_LIST_FAILED, label, source)
            result = RESULT_ADDED if added else RESULT_ALREADY_LISTED
            detail = "Auf der Liste" if added else "Schon drauf"

        self.store.async_record_scan(ean, label, result, self.device_name)
        await self._async_show("ok", label, detail)
        return ScanResult(ean, result, label, source)

    async def _async_add_to_list(self, label: str, ean: str) -> bool:
        """Add unless an open item with the same name exists. True if added."""
        entity_id = self.options.get(CONF_TODO_ENTITY)
        if not entity_id:
            raise HomeAssistantError("No shopping list configured")

        response = await self.hass.services.async_call(
            "todo",
            "get_items",
            {"status": ["needs_action"]},
            target={ATTR_ENTITY_ID: entity_id},
            blocking=True,
            return_response=True,
        )
        items = (response or {}).get(entity_id, {}).get("items", [])
        listed = {str(item.get("summary", "")).strip().casefold() for item in items}
        if label.casefold() in listed:
            return False

        data: dict[str, Any] = {"item": label}
        # Not every list can store a description (the plain Shopping List
        # cannot), and asking for one there fails the whole call.
        state = self.hass.states.get(entity_id)
        features = state.attributes.get(ATTR_SUPPORTED_FEATURES, 0) if state else 0
        if features & TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM:
            data["description"] = f"EAN {ean}"

        await self.hass.services.async_call(
            "todo",
            "add_item",
            data,
            target={ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
        return True

    async def _async_show(self, status: str, title: str, detail: str) -> None:
        """Push the outcome to the OLED. A device that is offline is not an error:
        the item is on the list either way, and that is what matters."""
        if not self.node_name:
            _LOGGER.debug("ESPHome node name unknown, cannot update the display")
            return
        action = node_action_name(self.node_name, DEVICE_ACTION)
        if not self.hass.services.has_service("esphome", action):
            _LOGGER.debug("esphome.%s is not available", action)
            return
        try:
            await self.hass.services.async_call(
                "esphome",
                action,
                {"status": status, "title": title, "detail": detail},
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.debug("Could not update the display: %s", err)

    async def _async_ask_for_name(self, ean: str) -> None:
        """Ask on the phone if one is configured, else in the HA notifications."""
        self._pending[ean] = self.entry.entry_id
        notify_service = self.options.get(CONF_NOTIFY_SERVICE)
        if notify_service:
            domain, _, service = notify_service.partition(".")
            try:
                await self.hass.services.async_call(
                    domain,
                    service,
                    {
                        "title": "ESPeep: unbekannter Artikel",
                        "message": (
                            f"Barcode {ean} steht in keiner Datenbank. "
                            "Wie soll er auf der Einkaufsliste heißen?"
                        ),
                        "data": {
                            "tag": f"espeep_{ean}",
                            "actions": [
                                {
                                    "action": f"{NOTIFY_ACTION_PREFIX}{ean}",
                                    "title": "Namen eingeben",
                                    "behavior": "textInput",
                                    "textInputButtonTitle": "Speichern",
                                    "textInputPlaceholder": "z. B. Milch",
                                }
                            ],
                        },
                    },
                    blocking=True,
                )
                return
            except HomeAssistantError as err:
                _LOGGER.warning("Could not notify %s: %s", notify_service, err)

        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "notification_id": notification_id(ean),
                "title": "ESPeep: unbekannter Artikel",
                "message": (
                    f"Barcode `{ean}` steht in keiner Datenbank. "
                    f"Gib ihm im [ESPeep-Panel](/{PANEL_URL_PATH}) einen Namen."
                ),
            },
            blocking=True,
        )

    @property
    def _language(self) -> str:
        language = self.options.get(CONF_LANGUAGE) or self.hass.config.language
        return str(language or "en").split("-")[0].lower()

    @callback
    def _async_publish(self, result: ScanResult) -> None:
        self.last_result = result
        self.hass.bus.async_fire(
            SCANNED_EVENT,
            {**asdict(result), "device_id": self.device_id},
        )
        async_dispatcher_send(
            self.hass, SIGNAL_SCAN_HANDLED.format(self.entry.entry_id), result
        )
