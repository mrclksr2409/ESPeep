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
    TextSelectorConfig,
)
import voluptuous as vol

from .const import (
    CONF_DESCRIPTION_TEMPLATE,
    CONF_DEVICE_ID,
    CONF_INCLUDE_BRAND,
    CONF_LANGUAGE,
    CONF_NOTIFY_SERVICE,
    CONF_ONLINE_LOOKUP,
    CONF_TITLE_TEMPLATE,
    CONF_TODO_ENTITY,
    DEFAULT_DESCRIPTION_TEMPLATE,
    DEFAULT_ONLINE_LOOKUP,
    DOMAIN,
)
from .logic import PLACEHOLDERS, title_template, unknown_placeholders

# Curly braces in translations are placeholders themselves, so "{name}" in a
# help text has to be filled with "{name}" to show up as such.
DESCRIPTION_PLACEHOLDERS = {
    **{key: f"{{{key}}}" for key in PLACEHOLDERS},
    "placeholders": ", ".join(f"{{{key}}}" for key in PLACEHOLDERS),
}


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
                CONF_TITLE_TEMPLATE, default=title_template(current)
            ): TextSelector(),
            vol.Optional(
                CONF_DESCRIPTION_TEMPLATE,
                description={
                    "suggested_value": current.get(
                        CONF_DESCRIPTION_TEMPLATE, DEFAULT_DESCRIPTION_TEMPLATE
                    )
                },
            ): TextSelector(TextSelectorConfig(multiline=True)),
            vol.Optional(
                CONF_LANGUAGE,
                description={"suggested_value": current.get(CONF_LANGUAGE)},
            ): TextSelector(),
        }
    )


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    """Drop empty optional values so defaults apply again.

    Except the description: the form leaves out a field you emptied, and an
    empty description means "no description", not "the default one"."""
    options = {k: v for k, v in user_input.items() if v not in ("", None)}
    options[CONF_DESCRIPTION_TEMPLATE] = user_input.get(CONF_DESCRIPTION_TEMPLATE) or ""
    # Replaced by the title template.
    options.pop(CONF_INCLUDE_BRAND, None)
    return options


def _validate(user_input: dict[str, Any]) -> dict[str, str]:
    """Templates may only use placeholders ESPeep can fill."""
    errors: dict[str, str] = {}
    for key in (CONF_TITLE_TEMPLATE, CONF_DESCRIPTION_TEMPLATE):
        if unknown_placeholders(str(user_input.get(key) or "")):
            errors[key] = "unknown_placeholder"
    return errors


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
            errors = _validate(user_input)
            if device is None:
                errors[CONF_DEVICE_ID] = "device_not_found"
            elif not errors:
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
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders=DESCRIPTION_PLACEHOLDERS,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EspeepOptionsFlow()


class EspeepOptionsFlow(OptionsFlow):
    """Change list, phone and lookup behaviour later."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and not (errors := _validate(user_input)):
            return self.async_create_entry(data=_clean(user_input))
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(
                self.hass, user_input or dict(self.config_entry.options)
            ),
            errors=errors,
            description_placeholders=DESCRIPTION_PLACEHOLDERS,
        )
