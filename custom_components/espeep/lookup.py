"""Barcode lookup against the Open Food Facts family of databases."""

from __future__ import annotations

import logging

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import VERSION
from .logic import ProductInfo, parse_off_product

_LOGGER = logging.getLogger(__name__)

# Groceries first; household goods and cosmetics end up on shopping lists too.
DATABASES: tuple[tuple[str, str], ...] = (
    ("Open Food Facts", "https://world.openfoodfacts.org"),
    ("Open Products Facts", "https://world.openproductsfacts.org"),
    ("Open Beauty Facts", "https://world.openbeautyfacts.org"),
)

# Open Food Facts asks API clients to identify themselves and throttles
# generic user agents.
USER_AGENT = f"ESPeep/{VERSION} (https://github.com/mrclksr2409/ESPeep)"
TIMEOUT = aiohttp.ClientTimeout(total=10)


class ProductLookupError(Exception):
    """No database could be asked, so "unknown" would be a guess."""


async def async_lookup(
    hass: HomeAssistant, ean: str, language: str
) -> ProductInfo | None:
    """Return the product, None if no database knows it.

    Raises ProductLookupError when not a single database answered — then the barcode
    is not known to be unknown, and asking the user for a name would be wrong.
    """
    session = async_get_clientsession(hass)
    fields = f"product_name,product_name_{language},generic_name,brands,quantity"
    answered = False

    for database, base_url in DATABASES:
        url = f"{base_url}/api/v2/product/{ean}.json"
        try:
            async with session.get(
                url,
                params={"fields": fields},
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            ) as response:
                # 404 is the API's regular answer for "no such product".
                if response.status == 404:
                    answered = True
                    continue
                if response.status != 200:
                    _LOGGER.warning(
                        "%s answered HTTP %s for %s", database, response.status, ean
                    )
                    continue
                payload = await response.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            _LOGGER.warning("Could not ask %s about %s: %s", database, ean, err)
            continue

        answered = True
        if product := parse_off_product(payload, language, database):
            return product

    if not answered:
        raise ProductLookupError(f"No product database reachable for {ean}")
    return None
