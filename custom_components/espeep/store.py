"""The product database: barcode -> name, kept in Home Assistant's .storage.

One database is shared by every ESPeep scanner, so a product named in the
kitchen is known to the scanner in the cellar too.

A product is stored under its first barcode and can carry further ones in
`eans`: "Milch" for the whole-milk carton, the low-fat one and the other
brand. Scanning any of them puts the same name on the list.
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
    # Further barcodes that stand for the same product.
    eans: list[str]


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
        # Further barcode -> the barcode its product is stored under.
        self._aliases: dict[str, str] = {}
        self._listeners: list[Callable[[], None]] = []

    async def async_load(self) -> None:
        """Load the table from disk."""
        data = await self._store.async_load() or {}
        self.products = data.get("products", {})
        self.unknown = data.get("unknown", {})
        self.history = data.get("history", [])
        for ean, product in self.products.items():
            # Databases from before multi-barcode products have no `eans`.
            for alias in product.setdefault("eans", []):
                self._aliases[alias] = ean

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
    def resolve(self, ean: str) -> str | None:
        """Return the barcode the product with this barcode is stored under."""
        return ean if ean in self.products else self._aliases.get(ean)

    @callback
    def get(self, ean: str) -> Product | None:
        """Return the product for any of its barcodes."""
        key = self.resolve(ean)
        return self.products[key] if key else None

    @callback
    def find_by_name(self, name: str) -> str | None:
        """Barcode of a product with exactly this name (ignoring case)."""
        wanted = clean_name(name).casefold()
        return next(
            (ean for ean, p in self.products.items() if p["name"].casefold() == wanted),
            None,
        )

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
        # A further barcode names the product it belongs to.
        ean = self.resolve(ean) or ean
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
            "eans": existing["eans"] if existing else [],
        }
        self.products[ean] = product
        self.unknown.pop(ean, None)
        return product

    @callback
    def async_edit(
        self,
        ean: str,
        name: str,
        *,
        brand: str = "",
        quantity: str = "",
        eans: list[str] | None = None,
        previous_ean: str | None = None,
    ) -> Product:
        """Save a product from the panel: optionally under a new barcode and
        with a new set of further barcodes. One change, one save."""
        if previous_ean and previous_ean != ean and previous_ean in self.products:
            self._drop(ean)
            self.products[ean] = self.products.pop(previous_ean)
            for alias in self.products[ean]["eans"]:
                self._aliases[alias] = ean
        product = self._set(ean, name, brand, quantity, SOURCE_USER)
        if eans is not None:
            key = self.resolve(ean) or ean
            for alias in list(product["eans"]):
                if alias not in eans:
                    self._detach(alias)
            for alias in eans:
                self._attach(key, alias)
        self._changed()
        return product

    @callback
    def async_add_ean(self, product_ean: str, ean: str) -> Product | None:
        """Make `ean` a further barcode of a product.

        A product already stored under `ean` is merged in, together with its
        own further barcodes and scan count. None if there is no such product.
        """
        if (key := self.resolve(product_ean)) is None:
            return None
        self._attach(key, ean)
        self._changed()
        return self.products[key]

    def _attach(self, key: str, ean: str) -> None:
        product = self.products[key]
        if ean == key or ean in product["eans"]:
            return
        if ean in self._aliases:
            self._detach(ean)
        elif other := self.products.pop(ean, None):
            product["scans"] += other["scans"]
            if other["last_scan"] and (product["last_scan"] or "") < other["last_scan"]:
                product["last_scan"] = other["last_scan"]
            for alias in other["eans"]:
                product["eans"].append(alias)
                self._aliases[alias] = key
        product["eans"].append(ean)
        product["updated"] = dt_util.utcnow().isoformat()
        self._aliases[ean] = key
        self.unknown.pop(ean, None)

    def _detach(self, alias: str) -> None:
        if (key := self._aliases.pop(alias, None)) is not None:
            self.products[key]["eans"].remove(alias)
            self.products[key]["updated"] = dt_util.utcnow().isoformat()

    def _drop(self, ean: str) -> bool:
        """Forget a barcode: a further one is detached, a product goes entirely."""
        if ean in self._aliases:
            self._detach(ean)
            return True
        if (product := self.products.pop(ean, None)) is None:
            return False
        for alias in product["eans"]:
            self._aliases.pop(alias, None)
        return True

    @callback
    def async_remove(self, ean: str) -> bool:
        """Forget a product, or just one further barcode of it.

        Returns False if the barcode was not known."""
        if not self._drop(ean):
            return False
        self._changed()
        return True

    @callback
    def async_learn(self, ean: str, name: str) -> Product:
        """Name a barcode nobody knew. If a product with that name exists, the
        barcode becomes one more of its barcodes instead of a new product."""
        owner = self.find_by_name(name)
        if owner is not None and owner != self.resolve(ean):
            self._attach(owner, ean)
            self._changed()
            return self.products[owner]
        return self.async_set(ean, name)

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
        if product := self.get(ean):
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
        """Bulk-add user names, e.g. from the old ean_mapping.yaml.

        Barcodes with the name of a product that is already there become
        further barcodes of it, so several lines "…;Milch" give one product.
        """
        for ean, name in entries.items():
            owner = self.find_by_name(name)
            if owner is not None and owner != self.resolve(ean):
                self._attach(owner, ean)
            else:
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
