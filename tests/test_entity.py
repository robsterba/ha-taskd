"""Tests for the taskd to-do entity."""

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

from homeassistant.components.todo import DATA_COMPONENT, TodoItem, TodoItemStatus
from homeassistant.util import dt as dt_util

from custom_components.taskd.const import DOMAIN
from custom_components.taskd.exceptions import TaskdItemNotFoundError

from .conftest import make_task

ENTITY_ID = "todo.taskd"


def get_entity(hass) -> Any:
    """Return the to-do entity object."""
    return hass.data[DATA_COMPONENT].get_entity(ENTITY_ID)


async def test_entity_state(hass, client, setup_integration) -> None:
    tasks = [
        make_task("t1", "Urgent thing", priority="urgent"),
        make_task("t2", "Done thing", status="done"),
    ]
    entry = await setup_integration(tasks)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    # state is the count of incomplete items
    assert state.state == "1"
    attrs = state.attributes
    assert attrs["total_tasks"] == 2
    assert attrs["overdue_count"] == 0
    assert attrs["last_synced"] is not None

    entity = get_entity(hass)
    items = entity.todo_items
    assert [item.uid for item in items] == ["t1", "t2"]
    assert items[0].summary == "Urgent thing"
    assert items[0].status is TodoItemStatus.NEEDS_ACTION
    assert items[1].status is TodoItemStatus.COMPLETED
    assert entry.entry_id in hass.data[DOMAIN]


async def test_sorting(hass, client, setup_integration) -> None:
    now = dt_util.utcnow()
    tasks = [
        make_task("done-old", "Done", status="done", created_at="2026-01-01T00:00:00Z"),
        make_task("no-due", "No due date"),
        make_task(
            "due-soon", "Due soon", due_date=(now + timedelta(days=1)).isoformat()
        ),
        make_task(
            "overdue-urgent",
            "Overdue",
            priority="urgent",
            due_date=(now - timedelta(days=1)).isoformat(),
        ),
        make_task(
            "due-sooner-low",
            "Due sooner low",
            priority="low",
            due_date=(now + timedelta(hours=2)).isoformat(),
        ),
    ]
    await setup_integration(tasks)

    items = get_entity(hass).todo_items
    assert [item.uid for item in items] == [
        "overdue-urgent",
        "due-sooner-low",
        "due-soon",
        "no-due",
        "done-old",
    ]


async def test_archived_excluded_by_coordinator(
    hass, client, setup_integration
) -> None:
    tasks = [
        make_task("t1", "visible"),
        make_task("t2", "hidden", status="archived"),
    ]
    await setup_integration(tasks)
    assert [item.uid for item in get_entity(hass).todo_items] == ["t1"]


async def test_overdue_count(hass, client, setup_integration) -> None:
    now = dt_util.utcnow()
    tasks = [
        make_task("t1", "overdue", due_date=(now - timedelta(days=2)).isoformat()),
        make_task("t2", "upcoming", due_date=(now + timedelta(days=2)).isoformat()),
        make_task("t3", "no due"),
        make_task(
            "t4",
            "done overdue",
            status="done",
            due_date=(now - timedelta(days=2)).isoformat(),
        ),
    ]
    await setup_integration(tasks)
    assert hass.states.get(ENTITY_ID).attributes["overdue_count"] == 1


async def test_create_todo_item(hass, client, setup_integration) -> None:
    await setup_integration([make_task("t1", "existing")])
    entity = get_entity(hass)

    await entity.async_create_todo_item(
        TodoItem(summary="Fix boxy #network !high", status=TodoItemStatus.NEEDS_ACTION)
    )

    client.async_create_task.assert_awaited_once_with(
        {
            "name": "Fix boxy",
            "source": "homeassistant",
            "priority": "high",
            "tags": ["network"],
        }
    )


async def test_create_todo_item_with_details(hass, client, setup_integration) -> None:
    await setup_integration()
    entity = get_entity(hass)
    due = dt_util.now().replace(microsecond=0)

    await entity.async_create_todo_item(
        TodoItem(summary="Plain", description="desc", due=due)
    )

    payload = client.async_create_task.await_args.args[0]
    assert payload["name"] == "Plain"
    assert payload["description"] == "desc"
    assert payload["due_date"] == dt_util.as_utc(due).isoformat()
    assert payload["source"] == "homeassistant"
    assert "priority" not in payload
    assert "tags" not in payload


async def test_update_item_rename_and_description(
    hass, client, setup_integration
) -> None:
    tasks = [make_task("t1", "Old name", description="old desc")]
    await setup_integration(tasks)
    entity = get_entity(hass)

    await entity.async_update_todo_item(
        TodoItem(
            uid="t1",
            summary="New name",
            description="new desc",
            status=TodoItemStatus.NEEDS_ACTION,
        )
    )

    client.async_update_task.assert_awaited_once_with(
        "t1", {"name": "New name", "description": "new desc"}
    )
    client.async_complete_task.assert_not_awaited()


async def test_update_item_complete(hass, client, setup_integration) -> None:
    await setup_integration([make_task("t1", "task")])
    entity = get_entity(hass)

    await entity.async_update_todo_item(
        TodoItem(uid="t1", summary="task", status=TodoItemStatus.COMPLETED)
    )

    client.async_complete_task.assert_awaited_once_with("t1")
    client.async_update_task.assert_not_awaited()


async def test_update_item_uncomplete(hass, client, setup_integration) -> None:
    await setup_integration([make_task("t1", "task", status="done")])
    entity = get_entity(hass)

    await entity.async_update_todo_item(
        TodoItem(uid="t1", summary="task", status=TodoItemStatus.NEEDS_ACTION)
    )

    client.async_update_task.assert_awaited_once_with("t1", {"status": "todo"})
    client.async_complete_task.assert_not_awaited()


async def test_update_item_sets_due_date(hass, client, setup_integration) -> None:
    await setup_integration([make_task("t1", "task")])
    entity = get_entity(hass)
    due = dt_util.now().replace(microsecond=0) + timedelta(days=3)

    await entity.async_update_todo_item(
        TodoItem(uid="t1", summary="task", due=due, status=TodoItemStatus.NEEDS_ACTION)
    )

    client.async_update_task.assert_awaited_once_with(
        "t1", {"due_date": dt_util.as_utc(due).isoformat()}
    )


async def test_update_item_no_changes_sends_nothing(
    hass, client, setup_integration
) -> None:
    await setup_integration([make_task("t1", "task", description="d")])
    entity = get_entity(hass)

    await entity.async_update_todo_item(
        TodoItem(
            uid="t1",
            summary="task",
            description="d",
            status=TodoItemStatus.NEEDS_ACTION,
        )
    )

    client.async_update_task.assert_not_awaited()
    client.async_complete_task.assert_not_awaited()


async def test_update_item_404_race(hass, client, setup_integration) -> None:
    await setup_integration([make_task("t1", "task")])
    entity = get_entity(hass)
    client.async_complete_task = AsyncMock(side_effect=TaskdItemNotFoundError("gone"))

    # Must not raise: item vanished between poll and action.
    await entity.async_update_todo_item(
        TodoItem(uid="t1", summary="task", status=TodoItemStatus.COMPLETED)
    )


async def test_delete_items(hass, client, setup_integration) -> None:
    await setup_integration([make_task("t1", "a"), make_task("t2", "b")])
    entity = get_entity(hass)

    await entity.async_delete_todo_items(["t1", "t2"])

    assert client.async_delete_task.await_count == 2
    assert [c.args[0] for c in client.async_delete_task.await_args_list] == ["t1", "t2"]


async def test_delete_item_404_race(hass, client, setup_integration) -> None:
    await setup_integration([make_task("t1", "a")])
    entity = get_entity(hass)
    client.async_delete_task = AsyncMock(side_effect=TaskdItemNotFoundError("gone"))

    await entity.async_delete_todo_items(["t1"])
