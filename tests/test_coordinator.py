"""Tests for the TaskdCoordinator."""

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

from custom_components.taskd.coordinator import TaskdCoordinator

from .conftest import make_task


def _page(tasks: list[dict[str, Any]], offset: int, total: int) -> dict[str, Any]:
    return {
        "tasks": tasks,
        "total": total,
        "limit": 500,
        "offset": offset,
    }


async def test_full_refresh_filters_and_indexes(hass, client) -> None:
    t1 = make_task("t1", "one")
    t2 = make_task("t2", "two", status="archived")
    t3 = make_task("t3", "three", status="done")
    client.async_list_tasks = AsyncMock(return_value=_page([t1, t2, t3], 0, 3))

    coordinator = TaskdCoordinator(hass, client, 60)
    result = await coordinator._async_update_data()

    assert result == {"t1": t1, "t3": t3}
    assert coordinator.last_synced is not None


async def test_pagination(hass, client) -> None:
    t1 = make_task("t1", "one")
    t2 = make_task("t2", "two")
    t3 = make_task("t3", "three")

    calls: list[dict[str, Any]] = []

    async def list_tasks(params=None):
        calls.append(params)
        offset = params["offset"]
        items = [t1, t2, t3][offset : offset + 2]
        return _page(items, offset, 3)

    client.async_list_tasks = AsyncMock(side_effect=list_tasks)

    coordinator = TaskdCoordinator(hass, client, 60)
    result = await coordinator._async_update_data()

    assert list(result) == ["t1", "t2", "t3"]
    assert [c["offset"] for c in calls] == [0, 2]
    assert all(c["parent"] == "none" for c in calls)
    assert all(c["limit"] == 500 for c in calls)


async def test_scan_interval_applied(hass, client) -> None:
    coordinator = TaskdCoordinator(hass, client, 45)
    assert coordinator.update_interval == timedelta(seconds=45)
