"""Thin aiohttp client for the taskd REST API (/api/v1)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from .const import DEFAULT_PORT, REQUEST_TIMEOUT
from .exceptions import (
    TaskdApiError,
    TaskdConnectionError,
    TaskdItemNotFoundError,
)

_LOGGER = logging.getLogger(__name__)

API_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)


def normalize_base_url(value: str) -> str:
    """Normalize a user-entered URL into a base URL.

    - strips whitespace (and trailing slashes at the end)
    - defaults the scheme to ``http://``
    - defaults the port to 8000 when an http host is given without one

    Raises ``ValueError`` for input without a parseable http(s) host.
    """
    value = value.strip()
    if "://" not in value:
        value = f"http://{value}"
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"Invalid http(s) URL: {value!r}")
    if parts.port is None and parts.scheme == "http":
        value = value.replace(parts.netloc, f"{parts.hostname}:{DEFAULT_PORT}", 1)
    return value.rstrip("/")


class TaskdClient:
    """taskd API client. One instance per config entry."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str) -> None:
        """Initialize the client with a shared session and normalized URL."""
        self._session = session
        self._base_url = base_url.rstrip("/")

    @property
    def base_url(self) -> str:
        """Return the normalized base URL."""
        return self._base_url

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Perform a request and map errors to typed exceptions."""
        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(
                method, url, params=params, json=json, timeout=API_TIMEOUT
            ) as resp:
                if resp.status == 404:
                    raise TaskdItemNotFoundError(f"Taskd item not found: {path}")
                if resp.status >= 400:
                    detail = await _extract_detail(resp)
                    raise TaskdApiError(resp.status, detail)
                if resp.status == 204:
                    return None
                return await resp.json()
        except (TimeoutError, aiohttp.ClientError) as err:
            raise TaskdConnectionError(
                f"Cannot connect to taskd at {self._base_url}"
            ) from err

    async def async_get_health(self) -> dict[str, Any]:
        """GET /api/v1/health."""
        return await self._request("GET", "/api/v1/health")

    async def async_list_tasks(
        self, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """GET /api/v1/tasks."""
        return await self._request("GET", "/api/v1/tasks", params=params)

    async def async_get_task(self, task_id: str) -> dict[str, Any]:
        """GET /api/v1/tasks/{task_id}."""
        return await self._request("GET", f"/api/v1/tasks/{task_id}")

    async def async_create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /api/v1/tasks."""
        return await self._request("POST", "/api/v1/tasks", json=payload)

    async def async_update_task(
        self, task_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """PATCH /api/v1/tasks/{task_id}."""
        return await self._request("PATCH", f"/api/v1/tasks/{task_id}", json=payload)

    async def async_complete_task(self, task_id: str) -> dict[str, Any]:
        """POST /api/v1/tasks/{task_id}/complete."""
        return await self._request("POST", f"/api/v1/tasks/{task_id}/complete")

    async def async_delete_task(self, task_id: str) -> None:
        """DELETE /api/v1/tasks/{task_id}."""
        await self._request("DELETE", f"/api/v1/tasks/{task_id}")


async def _extract_detail(resp: aiohttp.ClientResponse) -> str:
    """Best-effort extraction of the error detail from a response body."""
    try:
        body = await resp.json()
        return str(body.get("detail", body))
    except (aiohttp.ContentTypeError, ValueError):
        return await resp.text()
