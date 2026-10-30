"""Constants for the ESPeep integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "espeep"
VERSION: Final = "2.3.0"

# Fired by the firmware (esphome/packages/scanner.yaml). The ESPHome
# integration adds the Home Assistant `device_id` of the sender to the data.
SCAN_EVENT: Final = "esphome.espeep_scan"

# Fired by this integration after every handled scan, for your own automations.
SCANNED_EVENT: Final = "espeep_scanned"

# Name of the API action the firmware exposes in esphome/packages/base.yaml.
# ESPHome registers it as `esphome.<node name>_show_result`.
DEVICE_ACTION: Final = "show_result"

# Notification action prefix; the barcode travels in the action id because it
# is the only field the companion app reliably sends back with a reply.
NOTIFY_ACTION_PREFIX: Final = "ESPEEP_NAME_"

CONF_DEVICE_ID: Final = "device_id"
CONF_TODO_ENTITY: Final = "todo_entity"
CONF_NOTIFY_SERVICE: Final = "notify_service"
CONF_ONLINE_LOOKUP: Final = "online_lookup"
# Superseded by CONF_TITLE_TEMPLATE, still read for entries set up before.
CONF_INCLUDE_BRAND: Final = "include_brand"
CONF_TITLE_TEMPLATE: Final = "title_template"
CONF_DESCRIPTION_TEMPLATE: Final = "description_template"
CONF_LANGUAGE: Final = "language"

DEFAULT_ONLINE_LOOKUP: Final = True
DEFAULT_INCLUDE_BRAND: Final = True
DEFAULT_TITLE_TEMPLATE: Final = "{brand} {name}"
DEFAULT_DESCRIPTION_TEMPLATE: Final = "EAN {ean}"

SOURCE_USER: Final = "user"
SOURCE_ONLINE: Final = "online"

# Panel
PANEL_URL_PATH: Final = "espeep"
PANEL_ELEMENT: Final = "espeep-panel"
STATIC_URL: Final = "/espeep_static"

# Dispatcher signal sent whenever the product database changes.
SIGNAL_STORE_UPDATED: Final = f"{DOMAIN}_store_updated"
SIGNAL_SCAN_HANDLED: Final = f"{DOMAIN}_scan_handled_{{}}"

MAX_NAME_LENGTH: Final = 100
MAX_DESCRIPTION_LENGTH: Final = 1000
HISTORY_LENGTH: Final = 50
