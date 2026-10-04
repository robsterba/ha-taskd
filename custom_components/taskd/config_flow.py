"""Config flow for the taskd integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_URL
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TaskdClient, normalize_base_url
from .const import (
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .exceptions import TaskdApiError, TaskdConnectionError

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {vol.Required(CONF_URL): str, vol.Optional(CONF_API_KEY, default=""): str}
)


class TaskdConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the taskd config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial URL step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                base_url = normalize_base_url(user_input[CONF_URL])
            except ValueError:
                errors[CONF_URL] = "invalid_url"
            else:
                api_key = (user_input.get(CONF_API_KEY) or "").strip()
                client = TaskdClient(
                    async_get_clientsession(self.hass), base_url, api_key
                )
                try:
                    health = await client.async_get_health()
                except TaskdConnectionError:
                    errors[CONF_URL] = "cannot_connect"
                else:
                    if api_key:
                        try:
                            await client.async_list_tasks({"limit": 1})
                        except TaskdApiError as err:
                            if err.status == 401:
                                errors[CONF_API_KEY] = "invalid_api_key"
                            else:
                                errors["base"] = "cannot_connect"
                    if not errors:
                        _LOGGER.debug(
                            "taskd health check OK: %s (version %s)",
                            base_url,
                            health.get("version", "unknown"),
                        )
                        data = {CONF_URL: base_url}
                        if api_key:
                            data[CONF_API_KEY] = api_key
                        return self.async_create_entry(title="taskd", data=data)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TaskdOptionsFlowHandler:
        """Create the options flow."""
        return TaskdOptionsFlowHandler()


class TaskdOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle taskd options (scan interval, API key)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                interval = vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=3600)
                )(user_input[CONF_SCAN_INTERVAL])
            except vol.Invalid:
                errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_SCAN_INTERVAL: interval,
                        CONF_API_KEY: (user_input.get(CONF_API_KEY) or "").strip(),
                    },
                )

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        current_key = self.config_entry.options.get(
            CONF_API_KEY, self.config_entry.data.get(CONF_API_KEY, "")
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=current_interval,
                    ): int,
                    vol.Optional(CONF_API_KEY, default=current_key): str,
                }
            ),
            errors=errors,
        )
