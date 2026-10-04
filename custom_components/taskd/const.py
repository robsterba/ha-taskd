"""Constants for the taskd integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "taskd"
DEFAULT_NAME: Final = "taskd"
DEFAULT_PORT: Final = 8000

CONF_API_KEY: Final = "api_key"
CONF_SCAN_INTERVAL: Final = "scan_interval"
DEFAULT_SCAN_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 30

MAX_PAGE_LIMIT: Final = 500
SOURCE_HOMEASSISTANT: Final = "homeassistant"

TASK_STATUS_TODO: Final = "todo"
TASK_STATUS_IN_PROGRESS: Final = "in_progress"
TASK_STATUS_DONE: Final = "done"
TASK_STATUS_ARCHIVED: Final = "archived"

PRIORITY_ORDER: Final = {"urgent": 0, "high": 1, "medium": 2, "low": 3}

PLATFORMS: Final = ["todo"]

REQUEST_TIMEOUT: Final = 10
