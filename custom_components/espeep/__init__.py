"""ESPeep: barcode scanner for the Home Assistant shopping list.

The firmware only reads and validates barcodes. Everything else lives here:
the product database, the online lookup, the shopping list and the question
for a name when nobody knows a barcode.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    NOTIFY_ACTION_PREFIX,
    PANEL_ELEMENT,
    PANEL_URL_PATH,
    SIGNAL_STORE_UPDATED,
    STATIC_URL,
    VERSION,
)
from .logic import normalize_ean
from .runtime import EspeepData, async_named, get_data, loaded_scanners
from .scanner import EspeepScanner
from .services import async_register_services
from .store import ProductStore
from .websocket import async_register_websocket

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type EspeepConfigEntry = ConfigEntry[EspeepScanner]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the parts that exist once, regardless of how many scanners."""
    store = ProductStore(hass)
    await store.async_load()
    hass.data[DOMAIN] = EspeepData(store=store)

    store.async_add_listener(lambda: async_dispatcher_send(hass, SIGNAL_STORE_UPDATED))

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                STATIC_URL,
                str(Path(__file__).parent / "frontend"),
                cache_headers=False,
            )
        ]
    )
    async_register_websocket(hass)
    async_register_services(hass)

    @callback
    def _notification_reply(event: Event) -> None:
        action = str(event.data.get("action", ""))
        if not action.startswith(NOTIFY_ACTION_PREFIX):
            return
        ean = normalize_ean(action.removeprefix(NOTIFY_ACTION_PREFIX))
        reply = event.data.get("reply_text")
        if ean is None or not reply:
            return
        scanners = loaded_scanners(hass)
        if not scanners:
            store.async_learn(ean, reply)
            async_named(hass, ean)
            return
        entry_id = get_data(hass).pending.pop(ean, None)
        scanner = next(
            (s for s in scanners if s.entry.entry_id == entry_id), scanners[0]
        )
        hass.async_create_task(scanner.async_learn(ean, reply))

    hass.bus.async_listen("mobile_app_notification_action", _notification_reply)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EspeepConfigEntry) -> bool:
    """Set up one scanner."""
    data = get_data(hass)
    scanner = EspeepScanner(hass, entry, data.store, data.pending)
    entry.runtime_data = scanner
    scanner.async_start()

    if not data.panel_registered:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=PANEL_ELEMENT,
            sidebar_title="ESPeep",
            sidebar_icon="mdi:barcode-scan",
            module_url=f"{STATIC_URL}/espeep-panel.js?v={VERSION}",
            require_admin=False,
        )
        data.panel_registered = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: EspeepConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: EspeepConfigEntry) -> bool:
    """Unload one scanner; drop the panel with the last one."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    data = get_data(hass)
    if not loaded_scanners(hass) and data.panel_registered:
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
        data.panel_registered = False
    await data.store.async_flush()
    return True
