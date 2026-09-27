"""Data update coordinator for the taskd integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import TaskdClient
from .const import DOMAIN, MAX_PAGE_LIMIT, TASK_STATUS_ARCHIVED

_LOGGER = logging.getLogger(__name__)


class TaskdCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Poll taskd and store a mapping of task_id -> task dict.

    Subtasks are excluded (top-level tasks only, ``parent=none``) and
    archived tasks are filtered out client-side.
    """

    def __init__(
        self, hass: HomeAssistant, client: TaskdClient, scan_interval: int
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.last_synced: str | None = None

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch all top-level, non-archived tasks with pagination."""
        tasks: dict[str, dict[str, Any]] = {}
        offset = 0
        while True:
            data = await self.client.async_list_tasks(
                {"limit": MAX_PAGE_LIMIT, "offset": offset, "parent": "none"}
            )
            page: list[dict[str, Any]] = data.get("tasks", [])
            for task in page:
                if task.get("status") == TASK_STATUS_ARCHIVED:
                    continue
                tasks[task["id"]] = task
            total = data.get("total", len(page))
            offset += len(page)
            if not page or offset >= total:
                break
        self.last_synced = dt_util.utcnow().isoformat()
        return tasks
