"""Tests for the taskd.create_task service and diagnostics."""

from homeassistant.core import HomeAssistant

import custom_components.taskd as taskd_init
from custom_components.taskd.const import DOMAIN

from .conftest import make_task


async def test_create_task_service(
    hass: HomeAssistant, client, setup_integration
) -> None:
    await setup_integration()

    await hass.services.async_call(
        DOMAIN,
        "create_task",
        {
            "name": "Backup database",
            "description": "via service",
            "priority": "high",
            "tags": ["automated"],
            "due_date": "2026-09-30T14:00:00+00:00",
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    client.async_create_task.assert_awaited_once_with(
        {
            "name": "Backup database",
            "description": "via service",
            "priority": "high",
            "tags": ["automated"],
            "due_date": "2026-09-30T14:00:00+00:00",
            "source": "homeassistant",
        }
    )
    client.async_list_tasks.assert_awaited()  # refresh happened


async def test_create_task_service_minimal(hass, client, setup_integration) -> None:
    await setup_integration()

    await hass.services.async_call(
        DOMAIN, "create_task", {"name": "Bare"}, blocking=True
    )

    client.async_create_task.assert_awaited_once_with(
        {"name": "Bare", "source": "homeassistant"}
    )


async def test_unload_removes_service(hass, client, setup_integration) -> None:
    entry = await setup_integration()
    assert hass.services.has_service(DOMAIN, "create_task")

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert not hass.services.has_service(DOMAIN, "create_task")


async def test_diagnostics(hass, client, setup_integration) -> None:
    tasks = [make_task("t1", "secret personal task")]
    entry = await setup_integration(tasks)

    diagnostics = await taskd_init.async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["config_entry"]["url"] == "http://192.168.1.140:8000"
    assert diagnostics["task_count"] == 1
    assert diagnostics["last_synced"] is not None
    assert diagnostics["last_update_success"] is True
    # Full task bodies must not leak by default
    assert "tasks" not in diagnostics
