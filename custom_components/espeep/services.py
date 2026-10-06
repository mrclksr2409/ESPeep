"""Actions for automations and scripts: manage products, simulate scans."""

from __future__ import annotations

from dataclasses import asdict

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import CONF_DEVICE_ID, DOMAIN
from .logic import clean_name, normalize_ean
from .runtime import async_named, get_data, loaded_scanners
from .scanner import EspeepScanner

SERVICE_SET_PRODUCT = "set_product"
SERVICE_REMOVE_PRODUCT = "remove_product"
SERVICE_GET_PRODUCTS = "get_products"
SERVICE_SCAN = "scan"

ATTR_EAN = "ean"
ATTR_NAME = "name"
ATTR_BRAND = "brand"
ATTR_QUANTITY = "quantity"


def _ean(value: object) -> str:
    if (ean := normalize_ean(str(value))) is None:
        raise vol.Invalid("not a valid EAN/UPC barcode (check digit or length)")
    return ean


def _name(value: object) -> str:
    if not (name := clean_name(value)):
        raise vol.Invalid("name must not be empty")
    return name


SET_PRODUCT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_EAN): _ean,
        vol.Required(ATTR_NAME): _name,
        vol.Optional(ATTR_BRAND, default=""): cv.string,
        vol.Optional(ATTR_QUANTITY, default=""): cv.string,
    }
)
REMOVE_PRODUCT_SCHEMA = vol.Schema({vol.Required(ATTR_EAN): _ean})
SCAN_SCHEMA = vol.Schema(
    {
        # Not validated here: an invalid barcode is a legitimate test input.
        vol.Required(ATTR_EAN): cv.string,
        vol.Optional(CONF_DEVICE_ID): cv.string,
    }
)


def _scanner_for(hass: HomeAssistant, device_id: str | None) -> EspeepScanner:
    scanners = loaded_scanners(hass)
    if device_id:
        scanners = [s for s in scanners if s.device_id == device_id]
    if not scanners:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_scanner"
        )
    return scanners[0]


def async_register_services(hass: HomeAssistant) -> None:
    """Register the integration's actions."""
    store = get_data(hass).store

    async def set_product(call: ServiceCall) -> None:
        store.async_set(
            call.data[ATTR_EAN],
            call.data[ATTR_NAME],
            brand=call.data[ATTR_BRAND],
            quantity=call.data[ATTR_QUANTITY],
        )
        async_named(hass, call.data[ATTR_EAN])

    async def remove_product(call: ServiceCall) -> None:
        if not store.async_remove(call.data[ATTR_EAN]):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_product",
                translation_placeholders={"ean": call.data[ATTR_EAN]},
            )

    async def get_products(call: ServiceCall) -> ServiceResponse:
        return store.as_dict()

    async def scan(call: ServiceCall) -> ServiceResponse:
        scanner = _scanner_for(hass, call.data.get(CONF_DEVICE_ID))
        return asdict(await scanner.async_handle_scan(call.data[ATTR_EAN]))

    hass.services.async_register(
        DOMAIN, SERVICE_SET_PRODUCT, set_product, schema=SET_PRODUCT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REMOVE_PRODUCT, remove_product, schema=REMOVE_PRODUCT_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_PRODUCTS,
        get_products,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SCAN,
        scan,
        schema=SCAN_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
