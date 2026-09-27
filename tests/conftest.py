"""Shared fixtures for the taskd integration tests."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlsplit

import pytest
import pytest_socket
from homeassistant.const import CONF_URL
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.taskd.const import DOMAIN

BASE_URL = "http://192.168.1.140:8000"
LIVE_URL = os.environ.get("TASKD_LIVE_URL", "")


@pytest.fixture
def live_socket(socket_enabled):
    """Allow connections to the live taskd host for this test.

    socket_enabled lifts the socket constructor block; this then
    extends the allow-list, which the HA test harness resets to
    127.0.0.1 during setup.
    """
    if LIVE_URL:
        host = urlsplit(LIVE_URL).hostname
        pytest_socket.socket_allow_hosts(["127.0.0.1", host])
    yield


def make_task(
    task_id: str,
    name: str,
    status: str = "todo",
    priority: str = "medium",
    due_date: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    source: str = "api",
    parent_task_id: str | None = None,
    created_at: str = "2026-09-27T10:00:24.741033Z",
) -> dict[str, Any]:
    """Build a taskd task dict as returned by the live API."""
    return {
        "id": task_id,
        "name": name,
        "description": description,
        "status": status,
        "priority": priority,
        "due_date": due_date,
        "recurrence": None,
        "parent_task_id": parent_task_id,
        "tags": tags or [],
        "source": source,
        "created_at": created_at,
        "updated_at": created_at,
    }


@pytest.fixture
def client() -> MagicMock:
    """Mock TaskdClient used by config flow and setup."""
    client = MagicMock()
    client.base_url = BASE_URL
    client.async_get_health = AsyncMock(
        return_value={"status": "ok", "version": "1.3.3"}
    )
    client.async_list_tasks = AsyncMock(
        return_value={"tasks": [], "total": 0, "limit": 500, "offset": 0}
    )
    client.async_get_task = AsyncMock(
        side_effect=lambda task_id: make_task(task_id, "x")
    )
    client.async_create_task = AsyncMock(
        side_effect=lambda payload: make_task("new-id", payload["name"])
    )
    client.async_update_task = AsyncMock(return_value=make_task("t", "x"))
    client.async_complete_task = AsyncMock(
        return_value=make_task("t", "x", status="done")
    )
    client.async_delete_task = AsyncMock(return_value=None)
    return client


@pytest.fixture
def setup_integration(client: MagicMock, hass, enable_custom_integrations):
    """Patch TaskdClient everywhere and set up a config entry."""

    async def _setup(tasks: list[dict[str, Any]] | None = None) -> MockConfigEntry:
        if tasks is not None:
            client.async_list_tasks = AsyncMock(
                return_value={
                    "tasks": tasks,
                    "total": len(tasks),
                    "limit": 500,
                    "offset": 0,
                }
            )
        entry = MockConfigEntry(
            domain=DOMAIN,
            version=1,
            title="taskd",
            data={CONF_URL: BASE_URL},
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    with (
        patch("custom_components.taskd.config_flow.TaskdClient", return_value=client),
        patch("custom_components.taskd.TaskdClient", return_value=client),
    ):
        yield _setup
