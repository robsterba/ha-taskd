"""The taskd integration: expose taskd tasks as HA to-do lists."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api import TaskdClient
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SOURCE_HOMEASSISTANT,
)
from .coordinator import TaskdCoordinator
from .exceptions import TaskdApiError, TaskdConnectionError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.TODO]

# Opt-in for including full task bodies in diagnostics downloads. Task
# descriptions may contain personal text, so the default is off.
FULL_PAYLOAD_IN_DIAGNOSTICS = False

CREATE_TASK_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("description"): cv.string,
        vol.Optional("priority"): vol.In(["low", "medium", "high", "urgent"]),
        vol.Optional("tags"): cv.ensure_list,
        vol.Optional("due_date"): cv.datetime,
    }
)

type TaskdConfigEntry = ConfigEntry[TaskdCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: TaskdConfigEntry) -> bool:
    """Set up taskd from a config entry."""
    client = TaskdClient(async_get_clientsession(hass), entry.data[CONF_URL])
    coordinator = TaskdCoordinator(
        hass, client, entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, "create_task"):
        hass.services.async_register(
            DOMAIN, "create_task", _make_create_task_handler(hass), CREATE_TASK_SCHEMA
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: TaskdConfigEntry) -> bool:
    """Unload a taskd config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data[DOMAIN].pop(entry.entry_id)
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, "create_task")
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: TaskdConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _make_create_task_handler(hass: HomeAssistant) -> Callable[[ServiceCall], Any]:
    """Build the service handler for taskd.create_task."""

    async def async_create_task(call: ServiceCall) -> None:
        name: str = call.data["name"]
        payload: dict[str, Any] = {
            "name": name,
            "source": SOURCE_HOMEASSISTANT,
        }
        if (description := call.data.get("description")) is not None:
            payload["description"] = description
        if (priority := call.data.get("priority")) is not None:
            payload["priority"] = priority
        if (tags := call.data.get("tags")) is not None:
            payload["tags"] = [str(tag) for tag in tags]
        if (due_date := call.data.get("due_date")) is not None:
            payload["due_date"] = dt_util.as_utc(due_date).isoformat()

        coordinators = hass.data[DOMAIN]
        if len(coordinators) == 1:
            coordinator = next(iter(coordinators.values()))
        else:
            raise ValueError(
                "Multiple taskd instances configured; use the to-do entity "
                "instead of the taskd.create_task service."
            )

        try:
            await coordinator.client.async_create_task(payload)
        except TaskdConnectionError as err:
            raise HomeAssistantError(f"Cannot connect to taskd: {err}") from err
        except TaskdApiError as err:
            raise HomeAssistantError(f"taskd rejected the task: {err}") from err
        await coordinator.async_request_refresh()

    return async_create_task


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TaskdConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN].get(entry.entry_id)
    data = coordinator.data if coordinator else {}
    diagnostics: dict[str, Any] = {
        "config_entry": {
            "url": entry.data[CONF_URL],
            "scan_interval": entry.options.get(
                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
            ),
        },
        "task_count": len(data),
        "last_synced": coordinator.last_synced if coordinator else None,
        "last_update_success": coordinator.last_update_success if coordinator else None,
    }
    if FULL_PAYLOAD_IN_DIAGNOSTICS:
        diagnostics["tasks"] = data
    return diagnostics
