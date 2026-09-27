"""Live end-to-end tests against a real taskd instance.

Not run by default: set TASKD_LIVE_URL (e.g. http://192.168.1.140:8000)
to enable. Everything these tests create is tagged "ha-taskd-e2e" and
removed before and after the run.
"""

import dataclasses
import logging
import os
from datetime import datetime, timezone

import pytest
from homeassistant.components.todo import (
    DATA_COMPONENT,
    TodoItem,
    TodoItemStatus,
)
from homeassistant.const import CONF_URL
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.taskd.const import DOMAIN, SOURCE_HOMEASSISTANT

LIVE_URL = os.environ.get("TASKD_LIVE_URL", "")

LIVE_URL = os.environ.get("TASKD_LIVE_URL", "")
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not LIVE_URL, reason="set TASKD_LIVE_URL to run"),
]

E2E_TAG = "ha-taskd-e2e"
E2E_SUMMARY = "HA integration e2e probe"
E2E_RECURRING = "HA integration e2e recurring"
_LOGGER = logging.getLogger(__name__)


async def _cleanup(hass, coordinator) -> None:
    """Delete every task tagged ha-taskd-e2e (ours only).

    The server-side tag filter is verified client-side per task before
    deleting: taskd 1.3.3 and earlier return ALL tasks when asked for a
    tag that does not exist, which would make this delete the user's
    entire task list.
    """
    data = await coordinator.client.async_list_tasks({"tag": E2E_TAG, "limit": 500})
    for task in data.get("tasks", []):
        if E2E_TAG not in task.get("tags", []):
            _LOGGER.warning("Skipping unexpected task %s in cleanup", task.get("id"))
            continue
        await coordinator.client.async_delete_task(task["id"])


@pytest.fixture
async def live(hass, enable_custom_integrations, live_socket):
    """Set up the integration against the live instance."""
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, title="taskd", data={CONF_URL: LIVE_URL}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    await _cleanup(hass, coordinator)
    yield coordinator
    await _cleanup(hass, coordinator)


def _find(coordinator, summary: str):
    matches = [t for t in coordinator.data.values() if t.get("name") == summary]
    return matches


async def test_live_entity_renders_and_roundtrips(hass, live) -> None:
    """Entity lists real tasks; full create/update/complete/delete cycle."""
    entity = hass.data[DATA_COMPONENT].get_entity("todo.taskd")
    assert entity is not None
    assert entity.todo_items is not None  # real tasks rendered

    # Create via the entity (quick-add syntax path)
    await entity.async_create_todo_item(
        TodoItem(
            summary=f"{E2E_SUMMARY} #{E2E_TAG} !low",
            status=TodoItemStatus.NEEDS_ACTION,
        )
    )
    tasks = _find(live, E2E_SUMMARY)
    assert len(tasks) == 1
    task = tasks[0]
    assert task["source"] == SOURCE_HOMEASSISTANT
    assert E2E_TAG in task["tags"]
    assert task["priority"] == "low"
    assert task["status"] in ("todo", "in_progress")

    # Rename + description + due date via the update path
    due = datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc)
    await entity.async_update_todo_item(
        dataclasses.replace(
            _todo_item(entity, task["id"]),
            summary=f"{E2E_SUMMARY} renamed",
            description="e2e description",
            due=due,
        )
    )
    refreshed = live.data[task["id"]]
    assert refreshed["name"] == f"{E2E_SUMMARY} renamed"
    assert refreshed["description"] == "e2e description"
    assert refreshed["due_date"].startswith("2026-10-05T09:30")

    # Complete (taskd marks done; nothing else to verify here)
    await entity.async_update_todo_item(
        dataclasses.replace(
            _todo_item(entity, task["id"]), status=TodoItemStatus.COMPLETED
        )
    )
    assert live.data[task["id"]]["status"] == "done"

    # Uncheck -> back to todo
    await entity.async_update_todo_item(
        dataclasses.replace(
            _todo_item(entity, task["id"]), status=TodoItemStatus.NEEDS_ACTION
        )
    )
    assert live.data[task["id"]]["status"] == "todo"

    # Delete
    await entity.async_delete_todo_items([task["id"]])
    assert task["id"] not in live.data


async def test_live_recurring_completion_spawns_next(hass, live) -> None:
    """Completing a recurring task from HA spawns the next occurrence."""
    created = await live.client.async_create_task(
        {
            "name": E2E_RECURRING,
            "tags": [E2E_TAG],
            "source": SOURCE_HOMEASSISTANT,
            "recurrence": {"interval": "daily", "interval_count": 1},
        }
    )
    await live.async_refresh()
    entity = hass.data[DATA_COMPONENT].get_entity("todo.taskd")
    original_id = created["id"]

    await entity.async_update_todo_item(
        dataclasses.replace(
            _todo_item(entity, original_id), status=TodoItemStatus.COMPLETED
        )
    )
    await live.async_refresh()

    assert live.data[original_id]["status"] == "done"
    occurrences = _find(live, E2E_RECURRING)
    assert len(occurrences) == 2
    new_task = next(t for t in occurrences if t["id"] != original_id)
    assert new_task["status"] == "todo"
    # The next occurrence carries the recurrence rule forward
    assert new_task["recurrence"] is not None


def _todo_item(entity, uid: str) -> TodoItem:
    return next(item for item in entity.todo_items if item.uid == uid)
