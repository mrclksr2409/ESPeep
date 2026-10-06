"""Config and options flow: pick the scanner, the list and the phone."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import (
    BooleanSelector,
    DeviceSelector,
    DeviceSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
import voluptuous as vol

from .const import (
    CONF_DEVICE_ID,
    CONF_INCLUDE_BRAND,
    CONF_LANGUAGE,
    CONF_NOTIFY_SERVICE,
    CONF_ONLINE_LOOKUP,
    CONF_TODO_ENTITY,
    DEFAULT_INCLUDE_BRAND,
    DEFAULT_ONLINE_LOOKUP,
    DOMAIN,
)


def _notify_services(hass: HomeAssistant) -> list[str]:
    """Phones first: only the companion app supports the reply text field."""
    services = sorted(hass.services.async_services().get("notify", {}))
    mobile = [f"notify.{s}" for s in services if s.startswith("mobile_app_")]
    other = [
        f"notify.{s}"
        for s in services
        if not s.startswith("mobile_app_") and s not in ("notify", "send_message")
    ]
    return mobile + other


def _options_schema(hass: HomeAssistant, current: dict[str, Any]) -> vol.Schema:
    notify_default = current.get(CONF_NOTIFY_SERVICE)
    return vol.Schema(
        {
            vol.Required(
                CONF_TODO_ENTITY, default=current.get(CONF_TODO_ENTITY, vol.UNDEFINED)
            ): EntitySelector(EntitySelectorConfig(domain="todo")),
            vol.Optional(
                CONF_NOTIFY_SERVICE,
                description={"suggested_value": notify_default},
            ): SelectSelector(
                SelectSelectorConfig(
                    options=_notify_services(hass),
                    custom_value=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_ONLINE_LOOKUP,
                default=current.get(CONF_ONLINE_LOOKUP, DEFAULT_ONLINE_LOOKUP),
            ): BooleanSelector(),
            vol.Required(
                CONF_INCLUDE_BRAND,
                default=current.get(CONF_INCLUDE_BRAND, DEFAULT_INCLUDE_BRAND),
            ): BooleanSelector(),
            vol.Optional(
                CONF_LANGUAGE,
                description={"suggested_value": current.get(CONF_LANGUAGE)},
            ): TextSelector(),
        }
    )


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    """Drop empty optional values so defaults apply again."""
    return {k: v for k, v in user_input.items() if v not in ("", None)}


class EspeepConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one ESPeep scanner."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]
            device = dr.async_get(self.hass).async_get(device_id)
            if device is None:
                errors[CONF_DEVICE_ID] = "device_not_found"
            else:
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()
                options = _clean(
                    {k: v for k, v in user_input.items() if k != CONF_DEVICE_ID}
                )
                return self.async_create_entry(
                    title=device.name_by_user or device.name or "ESPeep",
                    data={CONF_DEVICE_ID: device_id},
                    options=options,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DeviceSelector(
                    DeviceSelectorConfig(integration="esphome")
                ),
                **_options_schema(self.hass, user_input or {}).schema,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EspeepOptionsFlow()


class EspeepOptionsFlow(OptionsFlow):
    """Change list, phone and lookup behaviour later."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=_clean(user_input))
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(self.hass, dict(self.config_entry.options)),
        )
