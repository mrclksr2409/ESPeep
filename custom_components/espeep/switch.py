"""Switch: put scanned products on the list, or only catalogue them."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import EspeepConfigEntry
from .entity import EspeepEntity
from .scanner import EspeepScanner


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EspeepConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switch of one scanner."""
    async_add_entities([AddToListSwitch(entry.runtime_data)])


class AddToListSwitch(EspeepEntity, SwitchEntity, RestoreEntity):
    """Off: scans are resolved and learned, but nothing lands on the list.

    Useful for the first evening, when you walk through the pantry naming
    everything without wanting it all on the shopping list.
    """

    _attr_icon = "mdi:cart-plus"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, scanner: EspeepScanner) -> None:
        super().__init__(scanner, "add_to_list")

    async def async_added_to_hass(self) -> None:
        if (last := await self.async_get_last_state()) is not None:
            self.scanner.add_to_list = last.state != STATE_OFF

    @property
    def is_on(self) -> bool:
        return self.scanner.add_to_list

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.scanner.add_to_list = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.scanner.add_to_list = False
        self.async_write_ha_state()
