"""Config flow for Playground Dashboard."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY, CONF_SCAN_INTERVAL, CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import ApiError, AuthError, CannotConnect, PlaygroundDashboardApi, normalize_url
from .const import (
    CONF_CONTAINERS,
    CONF_HOSTNAME,
    CONF_SCOPES,
    CONF_SITES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    TOKEN_RE,
)

_LOGGER = logging.getLogger(__name__)

PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def _validate(
    hass: HomeAssistant, url: str, api_key: str, verify_ssl: bool
) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """Ping the dashboard. Returns (ping response, errors)."""
    errors: dict[str, str] = {}
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None, {CONF_URL: "invalid_url"}
    if not TOKEN_RE.match(api_key):
        return None, {CONF_API_KEY: "invalid_api_key_format"}
    api = PlaygroundDashboardApi(async_get_clientsession(hass, verify_ssl=verify_ssl), url, api_key)
    try:
        ping = await api.ping()
    except AuthError:
        errors["base"] = "invalid_auth"
    except CannotConnect:
        errors["base"] = "cannot_connect"
    except ApiError:
        errors["base"] = "cannot_connect"
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Unexpected error validating the dashboard")
        errors["base"] = "unknown"
    else:
        if not isinstance(ping, dict) or not ping.get("hostname"):
            errors["base"] = "cannot_connect"
        else:
            return ping, errors
    return None, errors


def _scopes(ping: dict[str, Any]) -> list[str]:
    return list((ping.get("key") or {}).get("scopes") or ["read"])


class PlaygroundDashboardConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = normalize_url(user_input[CONF_URL])
            api_key = user_input[CONF_API_KEY].strip()
            verify_ssl = user_input[CONF_VERIFY_SSL]
            ping, errors = await _validate(self.hass, url, api_key, verify_ssl)
            if ping is not None:
                hostname = str(ping["hostname"])
                await self.async_set_unique_id(hostname)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=hostname,
                    data={
                        CONF_URL: url,
                        CONF_API_KEY: api_key,
                        CONF_VERIFY_SSL: verify_ssl,
                        CONF_SCOPES: _scopes(ping),
                        CONF_HOSTNAME: hostname,
                    },
                )
        else:
            user_input = {}

        schema = vol.Schema(
            {
                vol.Required(CONF_URL, default=user_input.get(CONF_URL, vol.UNDEFINED)): str,
                vol.Required(CONF_API_KEY): PASSWORD,
                vol.Required(CONF_VERIFY_SSL, default=user_input.get(CONF_VERIFY_SSL, True)): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauth after a 401."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API key."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            ping, errors = await _validate(
                self.hass, entry.data[CONF_URL], api_key, entry.data.get(CONF_VERIFY_SSL, True)
            )
            if ping is not None:
                if str(ping["hostname"]) != entry.unique_id:
                    return self.async_abort(reason="wrong_server")
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_API_KEY: api_key, CONF_SCOPES: _scopes(ping)},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): PASSWORD}),
            errors=errors,
            description_placeholders={"host": entry.title},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        """Return the options flow."""
        return PlaygroundDashboardOptionsFlow()


class PlaygroundDashboardOptionsFlow(OptionsFlow):
    """Options: scan interval and which entity groups to create."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(CONF_CONTAINERS, default=options.get(CONF_CONTAINERS, True)): bool,
                vol.Required(CONF_SITES, default=options.get(CONF_SITES, True)): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
