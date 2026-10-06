"""Pure helpers without Home Assistant imports, so they are trivially testable."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .const import MAX_NAME_LENGTH

VALID_LENGTHS = (8, 12, 13, 14)

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")


def normalize_ean(raw: str) -> str | None:
    """Return the barcode as digits if it is a valid GS1 code, else None.

    Mirrors the check the firmware does in scanner.yaml. Repeated here because
    barcodes also arrive from the panel, services and phone replies.
    """
    code = "".join(c for c in str(raw) if c.isdigit() and c.isascii())
    if len(code) not in VALID_LENGTHS:
        return None
    total = 0
    for i, char in enumerate(reversed(code[:-1])):
        digit = int(char)
        total += digit * 3 if i % 2 == 0 else digit
    if (10 - total % 10) % 10 != int(code[-1]):
        return None
    return code


def clean_name(raw: Any) -> str:
    """Make free text safe to store and to show on a 128x64 display."""
    if raw is None:
        return ""
    text = _CONTROL_CHARS.sub(" ", str(raw))
    text = _WHITESPACE.sub(" ", text).strip()
    return text[:MAX_NAME_LENGTH].strip()


@dataclass(slots=True)
class ProductInfo:
    """What an online database knows about a barcode."""

    name: str
    brand: str = ""
    quantity: str = ""
    database: str = ""


def first_brand(brands: str) -> str:
    """Open Food Facts lists brands comma separated; the first one is enough."""
    return clean_name(brands.split(",")[0]) if brands else ""


def compose_label(name: str, brand: str, include_brand: bool) -> str:
    """Build the text that goes on the shopping list."""
    name = clean_name(name)
    brand = clean_name(brand)
    if include_brand and brand and brand.casefold() not in name.casefold():
        return clean_name(f"{brand} {name}")
    return name


def parse_off_product(
    payload: dict[str, Any], language: str, database: str = ""
) -> ProductInfo | None:
    """Pick name, brand and quantity out of an Open *Facts v2 API response."""
    if not isinstance(payload, dict):
        return None
    product = payload.get("product")
    if not isinstance(product, dict):
        return None

    name = ""
    for key in (f"product_name_{language}", "product_name", "generic_name"):
        name = clean_name(product.get(key))
        if name:
            break
    if not name:
        return None

    return ProductInfo(
        name=name,
        brand=first_brand(str(product.get("brands") or "")),
        quantity=clean_name(product.get("quantity")),
        database=database,
    )


def node_action_name(node_name: str, action: str) -> str:
    """Name under which ESPHome registers a device's API action."""
    return f"{node_name.replace('-', '_')}_{action}"
