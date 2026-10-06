"""Base entity: ESPeep entities live on the ESPHome device they belong to."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .scanner import EspeepScanner


class EspeepEntity(Entity):
    """Shared naming and device linkage."""

    _attr_has_entity_name = True

    def __init__(self, scanner: EspeepScanner, key: str) -> None:
        self.scanner = scanner
        self._attr_translation_key = key
        self._attr_unique_id = f"{scanner.entry.entry_id}_{key}"

        # Linking through the MAC address puts these entities on the same device
        # page as the ESPHome ones, without borrowing ESPHome's identifiers.
        device = dr.async_get(scanner.hass).async_get(scanner.device_id)
        if device and device.connections:
            self._attr_device_info = DeviceInfo(connections=device.connections)
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, scanner.entry.entry_id)},
                name=scanner.entry.title,
                manufacturer="ESPeep",
            )
