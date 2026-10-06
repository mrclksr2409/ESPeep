"""End-to-end behaviour of the integration against a real Home Assistant core."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.espeep.const import (
    CONF_DEVICE_ID,
    CONF_NOTIFY_SERVICE,
    CONF_ONLINE_LOOKUP,
    CONF_TODO_ENTITY,
    DOMAIN,
    SCAN_EVENT,
    SCANNED_EVENT,
)

TODO = "todo.einkaufsliste"
OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{}.json"
OPF_URL = "https://world.openproductsfacts.org/api/v2/product/{}.json"
OBF_URL = "https://world.openbeautyfacts.org/api/v2/product/{}.json"

NUTELLA = "3017620422003"
UNKNOWN = "4006381333931"


class FakeEnvironment:
    """The services ESPeep talks to, recorded."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.items: list[str] = []
        self.added: list[dict[str, Any]] = []
        self.display: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []

        async def get_items(call: ServiceCall):
            return {
                TODO: {
                    "items": [
                        {"summary": s, "status": "needs_action", "uid": str(i)}
                        for i, s in enumerate(self.items)
                    ]
                }
            }

        async def add_item(call: ServiceCall) -> None:
            self.added.append(dict(call.data))
            self.items.append(call.data["item"])

        async def show_result(call: ServiceCall) -> None:
            self.display.append(dict(call.data))

        async def notify(call: ServiceCall) -> None:
            self.notifications.append(dict(call.data))

        self._hass = hass
        self._services = (get_items, add_item, show_result, notify)

    def install(self) -> None:
        """Register the fakes. Must run after ESPeep's setup, which loads the
        real todo integration and with it the real todo actions."""
        hass = self._hass
        get_items, add_item, show_result, notify = self._services
        hass.services.async_register(
            "todo", "get_items", get_items, supports_response=SupportsResponse.ONLY
        )
        hass.services.async_register("todo", "add_item", add_item)
        hass.services.async_register("esphome", "espeep_show_result", show_result)
        hass.services.async_register("notify", "mobile_app_phone", notify)
        if hass.states.get(TODO) is None:
            hass.states.async_set(TODO, "0", {"supported_features": 0})


@pytest.fixture
def env(hass: HomeAssistant) -> FakeEnvironment:
    return FakeEnvironment(hass)


@pytest.fixture
def esphome_device(hass: HomeAssistant) -> dr.DeviceEntry:
    """An adopted ESPHome device, as the esphome integration leaves it."""
    esphome_entry = MockConfigEntry(domain="esphome", data={"device_name": "espeep"})
    esphome_entry.add_to_hass(hass)
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=esphome_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")},
        name="ESPeep",
        manufacturer="mrclksr2409",
        model="espeep",
    )


async def _setup(
    hass: HomeAssistant, device: dr.DeviceEntry, env: FakeEnvironment, **options: Any
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DEVICE_ID: device.id},
        options={CONF_TODO_ENTITY: TODO, **options},
        unique_id=device.id,
        title="ESPeep",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    env.install()
    return entry


async def _scan(hass: HomeAssistant, device: dr.DeviceEntry, ean: str) -> None:
    hass.bus.async_fire(
        SCAN_EVENT, {"device_id": device.id, "ean": ean, "device_name": "espeep"}
    )
    await hass.async_block_till_done()


async def test_config_flow(hass: HomeAssistant, esphome_device, env) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_ID: esphome_device.id,
            CONF_TODO_ENTITY: TODO,
            CONF_NOTIFY_SERVICE: "notify.mobile_app_phone",
            CONF_ONLINE_LOOKUP: True,
            "include_brand": True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "ESPeep"
    assert result["data"] == {CONF_DEVICE_ID: esphome_device.id}
    assert result["options"][CONF_NOTIFY_SERVICE] == "notify.mobile_app_phone"
    await hass.async_block_till_done()
    env.install()

    # The same device cannot be set up twice.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_DEVICE_ID: esphome_device.id,
            CONF_TODO_ENTITY: TODO,
            CONF_ONLINE_LOOKUP: True,
            "include_brand": True,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(hass: HomeAssistant, esphome_device, env) -> None:
    entry = await _setup(hass, esphome_device, env)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_TODO_ENTITY: "todo.other",
            CONF_ONLINE_LOOKUP: False,
            "include_brand": False,
            "language": "",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {
        CONF_TODO_ENTITY: "todo.other",
        CONF_ONLINE_LOOKUP: False,
        "include_brand": False,
    }


async def test_scan_online_product(
    hass: HomeAssistant, esphome_device, env, aioclient_mock
) -> None:
    aioclient_mock.get(
        OFF_URL.format(NUTELLA),
        json={
            "product": {
                "product_name_de": "Nutella",
                "brands": "Ferrero",
                "quantity": "450 g",
            }
        },
    )
    await _setup(hass, esphome_device, env, language="de")
    events = []
    hass.bus.async_listen(SCANNED_EVENT, events.append)

    await _scan(hass, esphome_device, NUTELLA)

    assert env.items == ["Ferrero Nutella"]
    # The plain Shopping List cannot store descriptions; asking would fail.
    assert "description" not in env.added[0]
    assert env.display[-1] == {
        "status": "ok",
        "title": "Ferrero Nutella",
        "detail": "Auf der Liste",
    }
    assert events[0].data["result"] == "added"
    assert hass.states.get("sensor.espeep_last_scan").state == "Ferrero Nutella"
    assert hass.states.get("sensor.espeep_known_products").state == "1"

    # Second scan: served from the cache, not added twice.
    calls = aioclient_mock.call_count
    await _scan(hass, esphome_device, NUTELLA)
    assert aioclient_mock.call_count == calls
    assert env.items == ["Ferrero Nutella"]
    assert env.display[-1]["detail"] == "Schon drauf"


async def test_own_name_wins(
    hass: HomeAssistant, esphome_device, env, aioclient_mock
) -> None:
    await _setup(hass, esphome_device, env)
    await hass.services.async_call(
        DOMAIN, "set_product", {"ean": NUTELLA, "name": "Nutella"}, blocking=True
    )
    await _scan(hass, esphome_device, NUTELLA)
    assert aioclient_mock.call_count == 0
    assert env.items == ["Nutella"]


async def test_description_when_supported(
    hass: HomeAssistant, esphome_device, env
) -> None:
    hass.states.async_set(TODO, "0", {"supported_features": 64})
    await _setup(hass, esphome_device, env, **{CONF_ONLINE_LOOKUP: False})
    await hass.services.async_call(
        DOMAIN, "set_product", {"ean": NUTELLA, "name": "Nutella"}, blocking=True
    )
    await _scan(hass, esphome_device, NUTELLA)
    assert env.added[0]["description"] == f"EAN {NUTELLA}"


async def test_unknown_asks_phone_and_learns(
    hass: HomeAssistant, esphome_device, env, aioclient_mock
) -> None:
    for url in (OFF_URL, OPF_URL, OBF_URL):
        aioclient_mock.get(url.format(UNKNOWN), status=404)
    await _setup(
        hass, esphome_device, env, **{CONF_NOTIFY_SERVICE: "notify.mobile_app_phone"}
    )

    await _scan(hass, esphome_device, UNKNOWN)

    assert env.items == []
    assert env.display[-1]["status"] == "unknown"
    action = env.notifications[0]["data"]["actions"][0]
    assert action["action"] == f"ESPEEP_NAME_{UNKNOWN}"
    assert action["behavior"] == "textInput"
    assert hass.states.get("sensor.espeep_unknown_barcodes").state == "1"

    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": f"ESPEEP_NAME_{UNKNOWN}", "reply_text": "  Bleistift\n"},
    )
    await hass.async_block_till_done()

    assert env.items == ["Bleistift"]
    assert hass.states.get("sensor.espeep_unknown_barcodes").state == "0"

    # Known from now on, without asking anyone.
    await _scan(hass, esphome_device, UNKNOWN)
    assert len(env.notifications) == 1


async def test_unknown_without_phone_creates_notification(
    hass: HomeAssistant, esphome_device, env
) -> None:
    await _setup(hass, esphome_device, env, **{CONF_ONLINE_LOOKUP: False})
    await _scan(hass, esphome_device, UNKNOWN)
    assert (
        f"espeep_{UNKNOWN}"
        in persistent_notification._async_get_or_create_notifications(hass)
    )

    await hass.services.async_call(
        DOMAIN, "set_product", {"ean": UNKNOWN, "name": "Stift"}, blocking=True
    )
    assert (
        f"espeep_{UNKNOWN}"
        not in persistent_notification._async_get_or_create_notifications(hass)
    )


async def test_lookup_failure_does_not_ask(
    hass: HomeAssistant, esphome_device, env, aioclient_mock
) -> None:
    for url in (OFF_URL, OPF_URL, OBF_URL):
        aioclient_mock.get(url.format(UNKNOWN), exc=TimeoutError())
    await _setup(
        hass, esphome_device, env, **{CONF_NOTIFY_SERVICE: "notify.mobile_app_phone"}
    )
    await _scan(hass, esphome_device, UNKNOWN)
    assert env.notifications == []
    assert env.display[-1] == {
        "status": "error",
        "title": "Keine Verbindung",
        "detail": UNKNOWN,
    }


async def test_other_device_and_invalid_codes_ignored(
    hass: HomeAssistant, esphome_device, env
) -> None:
    await _setup(hass, esphome_device, env, **{CONF_ONLINE_LOOKUP: False})
    hass.bus.async_fire(SCAN_EVENT, {"device_id": "someone-else", "ean": NUTELLA})
    await hass.async_block_till_done()
    assert env.display == []

    await _scan(hass, esphome_device, "5449000000986")
    assert env.display[-1]["status"] == "error"
    assert env.items == []


async def test_catalogue_mode(hass: HomeAssistant, esphome_device, env) -> None:
    await _setup(hass, esphome_device, env, **{CONF_ONLINE_LOOKUP: False})
    await hass.services.async_call(
        DOMAIN, "set_product", {"ean": NUTELLA, "name": "Nutella"}, blocking=True
    )
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.espeep_add_to_shopping_list"},
        blocking=True,
    )
    await _scan(hass, esphome_device, NUTELLA)
    assert env.items == []
    assert env.display[-1]["detail"] == "Erkannt"


async def test_scan_service_and_products(
    hass: HomeAssistant, esphome_device, env
) -> None:
    await _setup(hass, esphome_device, env, **{CONF_ONLINE_LOOKUP: False})
    await hass.services.async_call(
        DOMAIN, "set_product", {"ean": NUTELLA, "name": "Nutella"}, blocking=True
    )
    result = await hass.services.async_call(
        DOMAIN, "scan", {"ean": NUTELLA}, blocking=True, return_response=True
    )
    assert result["result"] == "added"

    products = await hass.services.async_call(
        DOMAIN, "get_products", {}, blocking=True, return_response=True
    )
    assert products["products"][NUTELLA]["scans"] == 1
    assert products["history"][0]["name"] == "Nutella"

    await hass.services.async_call(
        DOMAIN, "remove_product", {"ean": NUTELLA}, blocking=True
    )
    products = await hass.services.async_call(
        DOMAIN, "get_products", {}, blocking=True, return_response=True
    )
    assert products["products"] == {}


async def test_websocket(
    hass: HomeAssistant, esphome_device, env, hass_ws_client
) -> None:
    await _setup(hass, esphome_device, env, **{CONF_ONLINE_LOOKUP: False})
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "espeep/subscribe"})
    assert (await client.receive_json())["success"]
    snapshot = (await client.receive_json())["event"]
    assert snapshot["products"] == {}
    assert snapshot["scanners"][0]["device_id"] == esphome_device.id

    await client.send_json_auto_id(
        {"type": "espeep/set", "ean": "5449000000986", "name": "Cola"}
    )
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "invalid_ean"

    await client.send_json_auto_id(
        {"type": "espeep/set", "ean": "5449000000996", "name": "Cola"}
    )
    update = await client.receive_json()
    assert update["type"] == "event"
    assert update["event"]["products"]["5449000000996"]["name"] == "Cola"
    assert (await client.receive_json())["success"]

    await client.send_json_auto_id(
        {
            "type": "espeep/import",
            "products": {NUTELLA: "Nutella", "123": "kaputt", "96385074": "  "},
        }
    )
    await client.receive_json()  # update event
    response = await client.receive_json()
    assert response["result"] == {"imported": 1, "rejected": ["123", "96385074"]}

    await client.send_json_auto_id(
        {"type": "espeep/learn", "ean": UNKNOWN, "name": "Stift"}
    )
    while (response := await client.receive_json())["type"] == "event":
        pass
    assert response["result"]["result"] == "added"
    assert env.items == ["Stift"]


async def test_unload(hass: HomeAssistant, esphome_device, env) -> None:
    entry = await _setup(hass, esphome_device, env)
    assert "espeep" in hass.data["frontend_panels"]
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert "espeep" not in hass.data["frontend_panels"]


async def test_panel_script_is_served(
    hass: HomeAssistant, esphome_device, env, hass_client
) -> None:
    await _setup(hass, esphome_device, env)
    client = await hass_client()
    response = await client.get("/espeep_static/espeep-panel.js")
    assert response.status == 200
    assert 'customElements.define("espeep-panel"' in await response.text()
