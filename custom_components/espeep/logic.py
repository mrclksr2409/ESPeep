"""Pure helpers without Home Assistant imports, so they are trivially testable."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .const import (
    CONF_INCLUDE_BRAND,
    CONF_TITLE_TEMPLATE,
    DEFAULT_INCLUDE_BRAND,
    DEFAULT_TITLE_TEMPLATE,
    MAX_DESCRIPTION_LENGTH,
    MAX_NAME_LENGTH,
)

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


# What a list entry can be built from. {brand} and {quantity} are only known
# for products from the online databases, or when you entered them yourself.
PLACEHOLDERS = ("name", "brand", "quantity", "ean", "device")

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_OPTIONAL = re.compile(r"\[([^\[\]]*)\]")


def unknown_placeholders(template: str) -> list[str]:
    """Placeholders in a template that ESPeep cannot fill."""
    return sorted(
        {key for key in _PLACEHOLDER.findall(template) if key not in PLACEHOLDERS}
    )


def render_template(template: str, values: dict[str, str]) -> str:
    """Fill a list entry template.

    - `{name}` and friends are replaced by the product's values.
    - `[ … ]` is left out entirely when a placeholder in it is empty, so
      `{name}[ ({quantity})]` gives "Milch (1 l)" or just "Milch".
    - A line whose placeholders are all empty is left out, so a line
      "Menge: {quantity}" disappears for products without a quantity.
    """

    def fill(text: str) -> str:
        return _PLACEHOLDER.sub(lambda m: values.get(m[1], m[0]), text)

    def optional(match: re.Match[str]) -> str:
        keys = _PLACEHOLDER.findall(match[1])
        if any(key in values and not values[key] for key in keys):
            return ""
        return fill(match[1])

    lines = []
    for line in template.splitlines():
        keys = _PLACEHOLDER.findall(line)
        if keys and all(key in values and not values[key] for key in keys):
            continue
        text = _WHITESPACE.sub(" ", fill(_OPTIONAL.sub(optional, line))).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def title_template(options: dict[str, Any]) -> str:
    """The title template, also for entries from before it was configurable."""
    if template := options.get(CONF_TITLE_TEMPLATE):
        return str(template)
    if not options.get(CONF_INCLUDE_BRAND, DEFAULT_INCLUDE_BRAND):
        return "{name}"
    return DEFAULT_TITLE_TEMPLATE


def compose_entry(
    title: str,
    description: str,
    *,
    name: str,
    brand: str = "",
    quantity: str = "",
    ean: str = "",
    device: str = "",
    own_name: bool = False,
) -> tuple[str, str]:
    """Build title and description of the list entry for a product."""
    name = clean_name(name)
    brand = clean_name(brand)
    values = {
        "name": name,
        "brand": brand,
        "quantity": clean_name(quantity),
        "ean": ean,
        "device": clean_name(device),
    }
    # The title never says the brand twice, and a name you gave a product is
    # what you want to read on the list, not the brand in front of it.
    title_values = values
    if own_name or brand.casefold() in name.casefold():
        title_values = {**values, "brand": ""}
    text = clean_name(render_template(title, title_values)) or name
    details = "\n".join(
        _CONTROL_CHARS.sub("", line)
        for line in render_template(description, values).splitlines()
    )
    return text, details[:MAX_DESCRIPTION_LENGTH].strip()


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
