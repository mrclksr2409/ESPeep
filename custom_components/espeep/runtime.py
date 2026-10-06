"""Shared state of the ESPeep integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .store import ProductStore

if TYPE_CHECKING:
    from .scanner import EspeepScanner


@dataclass
class EspeepData:
    """State shared by all ESPeep entries."""

    store: ProductStore
    panel_registered: bool = False
    # Which scanner asked for a name, so the reply lands on its list and display.
    pending: dict[str, str] = field(default_factory=dict)


def get_data(hass: HomeAssistant) -> EspeepData:
    """Return the shared ESPeep state."""
    return hass.data[DOMAIN]


def loaded_scanners(hass: HomeAssistant) -> list[EspeepScanner]:
    """All scanners of loaded config entries."""
    return [
        entry.runtime_data
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]


def notification_id(ean: str) -> str:
    """ID of the "unknown barcode" notification in Home Assistant."""
    return f"{DOMAIN}_{ean}"


@callback
def async_named(hass: HomeAssistant, ean: str) -> None:
    """A barcode got a name: the question for it is answered."""
    get_data(hass).pending.pop(ean, None)
    persistent_notification.async_dismiss(hass, notification_id(ean))
