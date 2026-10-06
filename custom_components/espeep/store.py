"""The product database: barcode -> name, kept in Home Assistant's .storage.

One database is shared by every ESPeep scanner, so a product named in the
kitchen is known to the scanner in the cellar too.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, HISTORY_LENGTH, SOURCE_USER
from .logic import clean_name

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.products"
SAVE_DELAY = 5


class Product(TypedDict):
    """A barcode Home Assistant knows a name for."""

    name: str
    brand: str
    quantity: str
    # "user" when you named it, "online" when it came from a database.
    source: str
    created: str
    updated: str
    scans: int
    last_scan: str | None


class Unknown(TypedDict):
    """A barcode that was scanned but nobody could name yet."""

    first_seen: str
    last_seen: str
    count: int


class HistoryEntry(TypedDict):
    """One handled scan."""

    ean: str
    name: str
    result: str
    device: str
    time: str


class ProductStore:
    """In-memory product table with delayed persistence."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.products: dict[str, Product] = {}
        self.unknown: dict[str, Unknown] = {}
        self.history: list[HistoryEntry] = []
        self._listeners: list[Callable[[], None]] = []

    async def async_load(self) -> None:
        """Load the table from disk."""
        data = await self._store.async_load() or {}
        self.products = data.get("products", {})
        self.unknown = data.get("unknown", {})
        self.history = data.get("history", [])

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Call `listener` after every change."""
        self._listeners.append(listener)

        @callback
        def remove() -> None:
            self._listeners.remove(listener)

        return remove

    @callback
    def _changed(self) -> None:
        self._store.async_delay_save(self._data, SAVE_DELAY)
        for listener in list(self._listeners):
            listener()

    def _data(self) -> dict[str, Any]:
        return {
            "products": self.products,
            "unknown": self.unknown,
            "history": self.history,
        }

    async def async_flush(self) -> None:
        """Write pending changes now."""
        await self._store.async_save(self._data())

    @callback
    def get(self, ean: str) -> Product | None:
        """Return the product for a barcode."""
        return self.products.get(ean)

    @callback
    def async_set(
        self,
        ean: str,
        name: str,
        *,
        brand: str = "",
        quantity: str = "",
        source: str = SOURCE_USER,
    ) -> Product:
        """Create or replace a product."""
        product = self._set(ean, name, brand, quantity, source)
        self._changed()
        return product

    def _set(
        self, ean: str, name: str, brand: str, quantity: str, source: str
    ) -> Product:
        now = dt_util.utcnow().isoformat()
        existing = self.products.get(ean)
        product: Product = {
            "name": clean_name(name),
            "brand": clean_name(brand),
            "quantity": clean_name(quantity),
            "source": source,
            "created": existing["created"] if existing else now,
            "updated": now,
            "scans": existing["scans"] if existing else 0,
            "last_scan": existing["last_scan"] if existing else None,
        }
        self.products[ean] = product
        self.unknown.pop(ean, None)
        return product

    @callback
    def async_remove(self, ean: str) -> bool:
        """Forget a product. Returns False if it was not known."""
        if self.products.pop(ean, None) is None:
            return False
        self._changed()
        return True

    @callback
    def async_mark_unknown(self, ean: str) -> None:
        """Remember a barcode nobody could name, so it can be named later."""
        now = dt_util.utcnow().isoformat()
        entry = self.unknown.get(ean)
        if entry:
            entry["last_seen"] = now
            entry["count"] += 1
        else:
            self.unknown[ean] = {"first_seen": now, "last_seen": now, "count": 1}
        self._changed()

    @callback
    def async_dismiss_unknown(self, ean: str) -> bool:
        """Drop a barcode from the unknown list without naming it."""
        if self.unknown.pop(ean, None) is None:
            return False
        self._changed()
        return True

    @callback
    def async_record_scan(self, ean: str, name: str, result: str, device: str) -> None:
        """Count a scan and keep it in the short history."""
        now = dt_util.utcnow().isoformat()
        if product := self.products.get(ean):
            product["scans"] += 1
            product["last_scan"] = now
        self.history.insert(
            0,
            {"ean": ean, "name": name, "result": result, "device": device, "time": now},
        )
        del self.history[HISTORY_LENGTH:]
        self._changed()

    @callback
    def async_import(self, entries: dict[str, str]) -> int:
        """Bulk-add user names, e.g. from the old ean_mapping.yaml."""
        for ean, name in entries.items():
            self._set(ean, name, "", "", SOURCE_USER)
        if entries:
            self._changed()
        return len(entries)

    @callback
    def as_dict(self) -> dict[str, Any]:
        """Snapshot for the panel and the get_products action."""
        return {
            "products": self.products,
            "unknown": self.unknown,
            "history": self.history,
        }
