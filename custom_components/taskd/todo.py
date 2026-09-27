"""To-do list platform for the taskd integration."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    PRIORITY_ORDER,
    SOURCE_HOMEASSISTANT,
    TASK_STATUS_DONE,
)
from .coordinator import TaskdCoordinator
from .exceptions import TaskdItemNotFoundError
from .quick_add import parse_quick_add

_LOGGER = logging.getLogger(__name__)

# HA 2026.x replaced the per-field to-do methods (async_set_todo_item_status,
# async_set_todo_item_due_date, ...) with a single async_update_todo_item
# carrying the full merged item, where None extended fields mean "clear".
_NEW_TODO_API = hasattr(TodoListEntityFeature, "SET_DUE_DATE_ON_ITEM")


def _build_supported_features() -> TodoListEntityFeature:
    """Feature-detect to-do features so older HA versions still load."""
    features = TodoListEntityFeature(0)
    for feature_name in (
        "CREATE_TODO_ITEM",
        "DELETE_TODO_ITEM",
        "UPDATE_TODO_ITEM",
        # HA <= 2025.x
        "SET_TODO_ITEM_STATUS",
        "SET_DUE_DATE",
        "SET_DESCRIPTION",
        # HA >= 2026.x
        "SET_DUE_DATE_ON_ITEM",
        "SET_DUE_DATETIME_ON_ITEM",
        "SET_DESCRIPTION_ON_ITEM",
    ):
        feature = getattr(TodoListEntityFeature, feature_name, None)
        if feature is not None:
            features |= feature
    return features


def _parse_due(value: str | None) -> datetime | None:
    """Parse a taskd ISO due date; naive values are treated as UTC."""
    if not value:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            _LOGGER.debug("Could not parse due date: %s", value)
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return parsed


def _format_due(due: datetime | date) -> str:
    """Convert a HA due date to an ISO 8601 UTC string for taskd."""
    if isinstance(due, datetime):
        return dt_util.as_utc(due).isoformat()
    return datetime(due.year, due.month, due.day, tzinfo=dt_util.UTC).isoformat()


def _task_sort_key(task: dict[str, Any]) -> tuple:
    """Sort: not-done first, due date ascending (None last), priority, created."""
    not_done = 0 if task.get("status") != TASK_STATUS_DONE else 1
    due = _parse_due(task.get("due_date"))
    # datetime.max sorts after any real due date, so tasks without a due
    # date come last within each status group.
    due_key: datetime = (
        due if due is not None else datetime.max.replace(tzinfo=dt_util.UTC)
    )
    priority = PRIORITY_ORDER.get(task.get("priority", "medium"), 2)
    created = task.get("created_at") or ""
    return (not_done, due_key, priority, created)


def _task_to_todo_item(task: dict[str, Any]) -> TodoItem:
    """Map a taskd task dict to a HA to-do item."""
    status = (
        TodoItemStatus.COMPLETED
        if task.get("status") == TASK_STATUS_DONE
        else TodoItemStatus.NEEDS_ACTION
    )
    return TodoItem(
        uid=task["id"],
        summary=task["name"],
        status=status,
        due=_parse_due(task.get("due_date")),
        description=task.get("description"),
    )


class TaskdTodoListEntity(CoordinatorEntity[TaskdCoordinator], TodoListEntity):
    """A taskd instance exposed as a HA to-do list."""

    _attr_should_poll = False
    _attr_icon = "mdi:checkbox-marked-circle-outline"

    def __init__(self, coordinator: TaskdCoordinator, entry: ConfigEntry) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_name = "taskd"
        self._attr_unique_id = entry.entry_id
        self._attr_supported_features = _build_supported_features()

    @property
    def todo_items(self) -> list[TodoItem] | None:
        """Return the taskd tasks as to-do items."""
        if self.coordinator.data is None:
            return None
        tasks = sorted(self.coordinator.data.values(), key=_task_sort_key)
        return [_task_to_todo_item(task) for task in tasks]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose cheap read-only stats for template sensors."""
        data = self.coordinator.data or {}
        now = dt_util.utcnow()
        overdue = sum(
            1
            for task in data.values()
            if task.get("status") != TASK_STATUS_DONE
            and (due := _parse_due(task.get("due_date"))) is not None
            and due < now
        )
        return {
            "total_tasks": len(data),
            "overdue_count": overdue,
            "last_synced": self.coordinator.last_synced,
        }

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add a new task (quick-add syntax is parsed from the summary)."""
        parsed = parse_quick_add(item.summary or "")
        payload: dict[str, Any] = {
            "name": parsed["name"],
            "source": SOURCE_HOMEASSISTANT,
        }
        if parsed["priority"] is not None:
            payload["priority"] = parsed["priority"]
        if parsed["tags"] is not None:
            payload["tags"] = parsed["tags"]
        if item.description is not None:
            payload["description"] = item.description
        if item.due is not None:
            payload["due_date"] = _format_due(item.due)

        await self.coordinator.client.async_create_task(payload)
        await self.coordinator.async_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update fields and/or status of an existing task.

        The incoming item is a full snapshot (new HA merges the stored
        item with the changed fields), so we diff it against the
        coordinator's copy and only PATCH what changed. taskd cannot
        clear due dates (PATCH skips nulls), so clear attempts are
        logged and ignored.
        """
        if item.uid is None:
            return
        task = self.coordinator.data.get(item.uid)
        payload: dict[str, Any] = {}
        if task is None:
            # Unknown item (deleted elsewhere): apply blindly.
            if item.summary is not None:
                payload["name"] = item.summary
            if item.description is not None:
                payload["description"] = item.description
            if item.due is not None:
                payload["due_date"] = _format_due(item.due)
            if payload:
                await self._patch_task(item.uid, payload)
            if item.status is not None:
                await self._set_task_status(item.uid, item.status)
            return

        if item.summary is not None and item.summary != task.get("name"):
            payload["name"] = item.summary

        if item.description is not None:
            if item.description != task.get("description"):
                payload["description"] = item.description
        elif _NEW_TODO_API and task.get("description"):
            # Explicit clear (new HA semantics); taskd stores "" as empty.
            payload["description"] = ""

        if item.due is not None:
            if _format_due(item.due) != task.get("due_date"):
                payload["due_date"] = _format_due(item.due)
        elif _NEW_TODO_API and task.get("due_date"):
            _LOGGER.warning(
                "Cannot clear the due date of task %s: taskd has no "
                "unset-due-date endpoint",
                item.uid,
            )

        if payload:
            await self._patch_task(item.uid, payload)

        if item.status is not None:
            is_done = task.get("status") == TASK_STATUS_DONE
            wants_done = item.status == TodoItemStatus.COMPLETED
            if wants_done != is_done:
                await self._set_task_status(item.uid, item.status)

        await self.coordinator.async_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete tasks."""
        for uid in uids:
            try:
                await self.coordinator.client.async_delete_task(uid)
            except TaskdItemNotFoundError:
                _LOGGER.debug("Task %s already deleted", uid)
        await self.coordinator.async_refresh()

    # --- Legacy HA (<= 2025.x) method surface -------------------------

    async def async_set_todo_item_status(
        self, item_id: str, status: TodoItemStatus
    ) -> None:
        """Complete or reopen a task (legacy HA)."""
        await self._set_task_status(item_id, status)
        await self.coordinator.async_refresh()

    async def async_set_todo_item_due_date(
        self, item_id: str, due_date: datetime | None
    ) -> None:
        """Set the due date of a task (legacy HA)."""
        if due_date is None:
            _LOGGER.warning(
                "Cannot clear the due date of task %s: taskd has no "
                "unset-due-date endpoint",
                item_id,
            )
            return
        await self._patch_task(item_id, {"due_date": _format_due(due_date)})

    async def async_set_todo_item_description(
        self, item_id: str, description: str | None
    ) -> None:
        """Set the description of a task (legacy HA)."""
        await self._patch_task(item_id, {"description": description or ""})

    async def async_delete_todo_item(self, item_id: str) -> None:
        """Delete a task (legacy HA)."""
        await self.async_delete_todo_items([item_id])

    # --- Internals -----------------------------------------------------

    async def _set_task_status(self, item_id: str, status: TodoItemStatus) -> None:
        """Complete a task (taskd handles recurrence) or reopen it."""
        try:
            if status == TodoItemStatus.COMPLETED:
                await self.coordinator.client.async_complete_task(item_id)
            else:
                await self.coordinator.client.async_update_task(
                    item_id, {"status": "todo"}
                )
        except TaskdItemNotFoundError:
            _LOGGER.debug("Task %s disappeared before status update", item_id)

    async def _patch_task(self, item_id: str, payload: dict[str, Any]) -> None:
        """PATCH a task, tolerating 404 races."""
        try:
            await self.coordinator.client.async_update_task(item_id, payload)
        except TaskdItemNotFoundError:
            _LOGGER.debug("Task %s disappeared before update", item_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the taskd to-do list entity from a config entry."""
    coordinator: TaskdCoordinator = hass.data["taskd"][entry.entry_id]
    async_add_entities([TaskdTodoListEntity(coordinator, entry)])
