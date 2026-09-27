"""Tests for TaskdClient against a local aiohttp test server."""

import asyncio

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from custom_components.taskd.api import TaskdClient, normalize_base_url
from custom_components.taskd.exceptions import (
    TaskdApiError,
    TaskdConnectionError,
    TaskdItemNotFoundError,
)


def test_normalize_base_url() -> None:
    assert normalize_base_url("taskd.local") == "http://taskd.local:8000"
    assert normalize_base_url("taskd.local:9000") == "http://taskd.local:9000"
    assert normalize_base_url("http://taskd.local:8000/") == "http://taskd.local:8000"
    assert (
        normalize_base_url("  http://192.168.1.140:8000  ")
        == "http://192.168.1.140:8000"
    )
    assert (
        normalize_base_url("https://taskd.example.com") == "https://taskd.example.com"
    )


@pytest.mark.parametrize("bad", ["", "http://", "://x", "ftp://"])
def test_normalize_base_url_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        normalize_base_url(bad)


@pytest.fixture
async def taskd_server(socket_enabled):
    """A minimal in-memory taskd API mock served over HTTP."""

    tasks: dict[str, dict] = {}
    next_id = [0]

    async def health(_request: web.Request) -> web.Response:
        return web.json_response(
            {"status": "ok", "version": "1.3.3", "timestamp": "2026-09-27T00:00:00Z"}
        )

    async def slow(_request: web.Request) -> web.Response:
        await asyncio.sleep(1.0)
        return web.json_response({"status": "ok"})

    async def list_tasks(request: web.Request) -> web.Response:
        limit = int(request.query.get("limit", 100))
        offset = int(request.query.get("offset", 0))
        if request.query.get("parent") == "none":
            items = [t for t in tasks.values() if t["parent_task_id"] is None]
        else:
            items = list(tasks.values())
        total = len(items)
        return web.json_response(
            {
                "tasks": items[offset : offset + limit],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

    async def get_task(request: web.Request) -> web.Response:
        task = tasks.get(request.match_info["task_id"])
        if task is None:
            return web.json_response({"detail": "not found"}, status=404)
        return web.json_response(task)

    async def create_task(request: web.Request) -> web.Response:
        payload = await request.json()
        next_id[0] += 1
        task = {
            "id": f"created-{next_id[0]}",
            "parent_task_id": None,
            "recurrence": None,
            "created_at": "2026-09-27T00:00:00Z",
            "updated_at": "2026-09-27T00:00:00Z",
            "tags": [],
            **payload,
        }
        tasks[task["id"]] = task
        return web.json_response(task, status=201)

    async def update_task(request: web.Request) -> web.Response:
        task = tasks.get(request.match_info["task_id"])
        if task is None:
            return web.json_response({"detail": "not found"}, status=404)
        payload = await request.json()
        for key, value in payload.items():
            if value is not None:
                task[key] = value
        return web.json_response(task)

    async def complete_task(request: web.Request) -> web.Response:
        task = tasks.get(request.match_info["task_id"])
        if task is None:
            return web.json_response({"detail": "not found"}, status=404)
        task["status"] = "done"
        return web.json_response(task)

    async def delete_task(request: web.Request) -> web.Response:
        if request.match_info["task_id"] not in tasks:
            return web.json_response({"detail": "not found"}, status=404)
        del tasks[request.match_info["task_id"]]
        return web.Response(status=204)

    async def bad_request(_request: web.Request) -> web.Response:
        return web.json_response({"detail": "priority is not a valid enum"}, status=422)

    async def boom(_request: web.Request) -> web.Response:
        return web.json_response({"detail": "internal error"}, status=500)

    app = web.Application()
    app.router.add_get("/api/v1/health", health)
    app.router.add_get("/api/v1/slow", slow)
    app.router.add_get("/api/v1/tasks", list_tasks)
    app.router.add_post("/api/v1/tasks", create_task)
    app.router.add_get("/api/v1/bad", bad_request)
    app.router.add_get("/api/v1/boom", boom)
    app.router.add_get("/api/v1/tasks/{task_id}", get_task)
    app.router.add_patch("/api/v1/tasks/{task_id}", update_task)
    app.router.add_post("/api/v1/tasks/{task_id}/complete", complete_task)
    app.router.add_delete("/api/v1/tasks/{task_id}", delete_task)

    server = TestServer(app)
    await server.start_server(loop=asyncio.get_running_loop())
    yield server, tasks
    await server.close()


@pytest.fixture
async def client(taskd_server):
    """TaskdClient wired to the local test server."""
    server, _ = taskd_server
    session = aiohttp.ClientSession()
    yield TaskdClient(session, str(server.make_url("")))
    await session.close()


async def test_health(client: TaskdClient) -> None:
    health = await client.async_get_health()
    assert health["status"] == "ok"


async def test_create_and_list(client: TaskdClient) -> None:
    created = await client.async_create_task(
        {"name": "Test", "source": "homeassistant"}
    )
    assert created["id"] == "created-1"
    data = await client.async_list_tasks()
    assert data["total"] == 1
    assert data["tasks"][0]["name"] == "Test"


async def test_pagination(client: TaskdClient) -> None:
    for i in range(3):
        await client.async_create_task({"name": f"task-{i}"})
    page1 = await client.async_list_tasks({"limit": 2, "offset": 0})
    assert page1["total"] == 3
    assert len(page1["tasks"]) == 2
    page2 = await client.async_list_tasks({"limit": 2, "offset": 2})
    assert len(page2["tasks"]) == 1


async def test_get_update_complete_delete(client: TaskdClient) -> None:
    created = await client.async_create_task({"name": "t"})
    task_id = created["id"]

    updated = await client.async_update_task(task_id, {"name": "renamed"})
    assert updated["name"] == "renamed"

    done = await client.async_complete_task(task_id)
    assert done["status"] == "done"

    got = await client.async_get_task(task_id)
    assert got["status"] == "done"

    await client.async_delete_task(task_id)
    with pytest.raises(TaskdItemNotFoundError):
        await client.async_get_task(task_id)


async def test_404_on_unknown(client: TaskdClient) -> None:
    with pytest.raises(TaskdItemNotFoundError):
        await client.async_get_task("missing")


async def test_api_error(client: TaskdClient) -> None:
    with pytest.raises(TaskdApiError) as excinfo:
        await client._request("GET", "/api/v1/bad")
    assert excinfo.value.status == 422
    assert "priority" in excinfo.value.detail

    with pytest.raises(TaskdApiError) as excinfo:
        await client._request("GET", "/api/v1/boom")
    assert excinfo.value.status == 500


async def test_timeout(client: TaskdClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "custom_components.taskd.api.API_TIMEOUT",
        aiohttp.ClientTimeout(total=0.1),
    )
    with pytest.raises(TaskdConnectionError):
        await client._request("GET", "/api/v1/slow")


async def test_connection_error(hass, socket_enabled) -> None:
    session = aiohttp.ClientSession()
    try:
        bad = TaskdClient(session, "http://127.0.0.1:1")
        with pytest.raises(TaskdConnectionError):
            await bad.async_get_health()
    finally:
        await session.close()
