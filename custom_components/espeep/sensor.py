"""Sensors: last scan, and how many barcodes are known or still unnamed."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EspeepConfigEntry
from .const import SIGNAL_SCAN_HANDLED, SIGNAL_STORE_UPDATED
from .entity import EspeepEntity
from .scanner import EspeepScanner, ScanResult


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EspeepConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors of one scanner."""
    scanner = entry.runtime_data
    async_add_entities(
        [
            LastScanSensor(scanner),
            UnknownCountSensor(scanner),
            ProductCountSensor(scanner),
        ]
    )


class LastScanSensor(EspeepEntity, SensorEntity):
    """Name of the last scanned product; details in the attributes."""

    _attr_icon = "mdi:barcode-scan"

    def __init__(self, scanner: EspeepScanner) -> None:
        super().__init__(scanner, "last_scan")
        self._result: ScanResult | None = None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_SCAN_HANDLED.format(self.scanner.entry.entry_id),
                self._handle,
            )
        )

    @callback
    def _handle(self, result: ScanResult) -> None:
        self._result = result
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        if self._result is None:
            return None
        return self._result.name or self._result.ean

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._result is None:
            return None
        return {
            "ean": self._result.ean,
            "result": self._result.result,
            "source": self._result.source,
        }


class _StoreSensor(EspeepEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_STORE_UPDATED, self.async_write_ha_state
            )
        )


class UnknownCountSensor(_StoreSensor):
    """Barcodes waiting for a name — handy for a dashboard badge."""

    _attr_icon = "mdi:help-box-multiple-outline"

    def __init__(self, scanner: EspeepScanner) -> None:
        super().__init__(scanner, "unknown_barcodes")

    @property
    def native_value(self) -> int:
        return len(self.scanner.store.unknown)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"barcodes": sorted(self.scanner.store.unknown)}


class ProductCountSensor(_StoreSensor):
    """Size of the product database."""

    _attr_icon = "mdi:database-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, scanner: EspeepScanner) -> None:
        super().__init__(scanner, "known_products")

    @property
    def native_value(self) -> int:
        return len(self.scanner.store.products)
