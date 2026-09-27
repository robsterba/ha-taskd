# taskd Home Assistant Integration — Build Spec

## 1. Goal

A Home Assistant custom integration (`custom_components/taskd`) that exposes taskd tasks as native Home Assistant to-do list entities, so the user can view, create, and complete tasks from HA dashboards (built-in To-Do List card) and HA Assist, without a custom card.

Phase 1 scope: to-do platform only. Custom card is out of scope (possible phase 2).

Source application: https://github.com/robsterba/taskd — FastAPI + SQLite + React, REST API at `/api/v1`, no authentication, LAN-only.

## 2. Non-goals (Phase 1)

- No custom Lovelace card (built-in To-Do card is used).
- No HACS packaging (add later; keep repo layout HACS-friendly anyway).
- No OAuth / auth flow (taskd v1 has none). Config flow asks for host/port/URL only.
- No tag management, recurrence editing, or subtask creation from HA (read-only exposure of these fields as entity attributes).
- No webhooks; use polling (taskd has `GET /api/v1/tasks/changed` for this).

## 3. Architecture

```
[HA to-do card / Assist] ──> [todo entity platform]
        │                          │
        │                   DataUpdateCoordinator
        │                          │
        └── services ──> TaskdClient (aiohttp) ──HTTP──> taskd /api/v1
```

Components:

1. **Config flow** (`config_flow.py`) — user enters base URL, validate against `GET /api/v1/health`. Optionally a per-entity-list filter config (which taskd statuses/tags a given to-do list shows).
2. **API client** (`api.py`) — thin `aiohttp` wrapper around the taskd REST API.
3. **DataUpdateCoordinator** (`coordinator.py`) — polls taskd every 60s (configurable scan interval, default 60, min 30), full refresh via `GET /api/v1/tasks` in phase 1. (The `tasks/changed` endpoint exists, but a full list poll at this scale is simpler; note `changed` as a phase 2 optimization.)
4. **To-do entities** (`todo.py`) — one `TodoListEntity` per configured list; maps taskd tasks to HA to-do items.

## 4. Repository / File Layout

Target repo: `custom_components/taskd/` inside a new repo `robsterba/ha-taskd` (HACS-compatible layout).

```
ha-taskd/
├── custom_components/
│   └── taskd/
│       ├── __init__.py          # async_setup_entry / async_unload_entry
│       ├── manifest.json
│       ├── config_flow.py
│       ├── const.py
│       ├── coordinator.py
│       ├── api.py               # TaskdClient
│       ├── todo.py              # TodoListEntity platform
│       ├── exceptions.py        # TaskdConnectionError, TaskdApiError, TaskdItemNotFoundError
│       └── translations/
│           └── en.json
├── tests/                       # pytest + pytest-asyncio, aiohttp test utils
├── hacs.json                    # added later (phase: HACS)
└── README.md
```

`manifest.json`:

```json
{
  "domain": "taskd",
  "name": "taskd",
  "codeowners": ["@robsterba"],
  "config_flow": true,
  "documentation": "https://github.com/robsterba/ha-taskd",
  "integration_type": "service",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/robsterba/ha-taskd/issues",
  "loggers": ["custom_components.taskd"],
  "requirements": [],
  "version": "0.1.0"
}
```

No external requirements — use `aiohttp` (bundled with HA).

## 5. API Client (`api.py`)

`TaskdClient` — one instance per config entry, held on `hass.data[DOMAIN][entry_id]["client"]`.

Methods (all return parsed JSON, raise typed exceptions):

| Method | HTTP | Path |
|---|---|---|
| `async_get_health()` | GET | `/api/v1/health` |
| `async_list_tasks(params)` | GET | `/api/v1/tasks` |
| `async_get_task(task_id)` | GET | `/api/v1/tasks/{id}` |
| `async_create_task(payload)` | POST | `/api/v1/tasks` |
| `async_update_task(task_id, payload)` | PATCH | `/api/v1/tasks/{id}` |
| `async_complete_task(task_id)` | POST | `/api/v1/tasks/{id}/complete` |
| `async_delete_task(task_id)` | DELETE | `/api/v1/tasks/{id}` |

Behavior:

- Base URL from config entry, normalized (strip trailing slash). Port defaults 8000 if the user enters only a host.
- Timeouts: `aiohttp.ClientTimeout(total=10)`.
- Errors: connection failures → `TaskdConnectionError`; HTTP 4xx/5xx → `TaskdApiError` with status + body detail; 404 → `TaskdItemNotFoundError` where relevant.
- Use a shared `aiohttp.ClientSession` from `async_get_clientsession(hass)`.

## 6. Config Flow

Single user flow:

1. User step: URL (or host + port — recommend a single "URL" field, e.g. `http://taskd.local:8000`).
2. Validate with `async_get_health()`. On failure show a recoverable error ("Cannot connect to taskd at {url}").
3. Options flow per entry (initially minimal): scan interval (seconds, default 60).

One config entry per taskd instance. The integration sets up one coordinator and, in phase 1, a single to-do list entity per entry (entity id suggestion: `todo.taskd`).

Phase 2 candidate (do not implement now, but design `async_get_options_flow` so it's extensible): multiple named lists, each a filter set (tags, statuses, priority).

## 7. To-Do Entity Mapping

### 7.1 Entity

- `TodoListEntity`, `TodoListEntityFeature.CREATE_TODO_ITEM | SET_TODO_ITEM_STATUS | DELETE_TODO_ITEM | UPDATE_TODO_ITEM | SET_DUE_DATE` (guard: features vary by HA version; require HA 2023.7+ and use the ones available).
- Name: "taskd". Icon: `mdi:checkbox-marked-circle-outline`.
- Reconstruct full item list from coordinator data.

### 7.2 Task → TodoItem mapping

| taskd field | HA to-do | Notes |
|---|---|---|
| `id` | `TodoItem.uid` | primary mapping key — never regenerate |
| `name` | `TodoItem.summary` | |
| `status: todo, in_progress` | `TodoItemStatus.NEEDS_ACTION` | |
| `status: done` | `TodoItemStatus.COMPLETED` | |
| `status: archived` | excluded by default (or include behind options flag) | |
| `due_date` | `TodoItem.due` | parse ISO 8601; pass through |
| `description` | `TodoItem.description` | markdown accepted as plain text |
| `priority`, `tags`, `source`, `recurrence`, `parent_task_id`, `updated_at` | entity attributes per item where the HA version supports `TodoItem` extra attrs, otherwise only in diagnostics | non-goal to surface in UI |

Items sorted: not-done first, then by due date ascending, then priority (urgent > high > medium > low), then `created_at`.

### 7.3 Supported operations

| HA action | taskd call |
|---|---|
| Add item (summary, optional description/due) | `POST /api/v1/tasks` with `{"name": summary, "source": "homeassistant", "due_date": ..., "description": ...}` |
| Complete item | `POST /api/v1/tasks/{uid}/complete` |
| Uncheck completed item | `PATCH /api/v1/tasks/{uid}` with `{"status": "todo"}` |
| Rename / update description | `PATCH /api/v1/tasks/{uid}` |
| Set due date | `PATCH /api/v1/tasks/{uid}` with `due_date` |
| Delete item | `DELETE /api/v1/tasks/{uid}` |

Rules:

- Always set `"source": "homeassistant"` on creation so taskd's GUI can filter HA-created tasks (matches taskd's n8n convention).
- All mutation methods: call taskd API, then `await self.coordinator.async_refresh()` before returning, so the UI stays consistent.
- Handle `TaskdItemNotFoundError` gracefully (item completed/deleted elsewhere between poll and action): refresh and return without raising.

### 7.4 Quick-add syntax (nice-to-have, small)

The HA to-do card sends a plain summary string. Implement taskd's quick-add parsing in the integration when creating items: extract `#tag` tokens into `tags`, `!priority` into `priority`. Keep it in a pure helper function (`parse_quick_add(text)`) so it's unit-testable and mirrors taskd's GUI behavior.

## 8. Coordinator

- `DataUpdateCoordinator[dict[str, dict]]` storing `{task_id: task_dict}` for non-archived tasks (default `limit=500`; handle pagination via `total` if > 500).
- `update_interval` from options (default 60s).
- Poll: `GET /api/v1/tasks?limit=500` (status filter excludes archived client-side).
- On `TaskdConnectionError`, set `last_update_success=False` (standard coordinator behavior) — entity shows unavailable; retry continues on schedule.

## 9. Services (beyond the to-do platform)

Phase 1: register `taskd.create_task` for power users / scripts / n8n-parity automations:

```yaml
service: taskd.create_task
data:
  name: "Backup database"
  description: "..."
  priority: high          # low|medium|high|urgent
  tags: ["automated"]
  due_date: "2026-09-30T14:00:00Z"
```

Implementation: entity-level or domain-level `async_register` service calling `TaskdClient.async_create_task`, then refresh. Keep to this one service; complete/delete already covered by to-do entity actions.

## 10. Error Handling & Diagnostics

- Config flow errors: cannot connect; invalid URL.
- Runtime: log at `debug` for request/response failures; `warning` once per outage via coordinator.
- `async_get_config_entry_diagnostics`: dump client config (no secrets — there are none) and last coordinator payload (task count, last updated timestamp; not full task bodies — they may contain personal text; make full dump opt-in via a constant).
- Entity `extra_state_attributes` on the to-do entity: `total_tasks`, `overdue_count`, `last_synced` (read-only, cheap, useful for template sensors).

## 11. Testing Plan

- `pytest`, `pytest-asyncio`, `pytest-homeassistant-custom-component` (pin to recent HA).
- Unit tests: `TaskdClient` against a mocked/aiohttp test server (fixture covering all 7 endpoints, error codes, timeout); `parse_quick_add`; entity mapping (each taskd status, sorting order, archived exclusion).
- Integration tests via HA `snapshot` helper if convenient; at minimum: config flow success/failure, entity creation, `async_create_todo_item` → assert POST body, `async_set_todo_item_status` complete/uncomplete paths, 404 race path.
- Manual test checklist: against a live taskd container — add from HA card appears in taskd GUI with `source=homeassistant`, complete in taskd GUI shows in HA within scan interval, recurring task completion spawns next occurrence and HA shows it.

## 12. Acceptance Criteria

1. Integration installs via `custom_components/taskd` manual copy and configures through UI with only a URL.
2. One `todo.taskd` entity appears; built-in To-Do List card can view, create, complete, uncomplete, rename, set due dates, and delete tasks.
3. Tasks created in HA appear in the taskd GUI with `source: homeassistant`.
4. Changes made in taskd GUI/n8n appear in HA within one scan interval.
5. Recurring tasks: completing from HA creates the next occurrence in taskd (server-side behavior, verified end to end).
6. `pytest` suite green with HA dev constraints warnings clean (`python -m homeassistant --script check_config` and ruff/mypy per HA dev tooling if adopted).

## 13. Build Milestones

1. Repo scaffold + manifest + `__init__` + config flow (health-validated URL) → integration shows as configured.
2. `TaskdClient` + tests.
3. Coordinator + entity that renders read-only task list in the To-Do card.
4. Mutations: create / complete / uncomplete; `source: homeassistant`.
5. Rename, due date, delete + `taskd.create_task` service.
6. Options flow (scan interval), attributes, diagnostics, polish, README.

## Appendix A — taskd-side enhancements worth adding (prioritized)

These are optional taskd changes; the HA integration works without any of them. Ranked by payoff.

A1. Webhook push (`POST /api/v1/webhooks`) — register a callback URL fired on task create/update/delete. Lets the HA coordinator switch from polling to instant push updates (HA webhook listener + `async_set_updated_data`). Also benefits n8n (removes the 5-minute schedule-poll pattern from the spec). This is the single highest-value addition. Pair with a `secret` field on the webhook record; HA sends it back in the callback body/header.

A2. `since` cursor on `GET /api/v1/tasks` (or lean harder on the existing `changed` endpoint) — even with webhooks, HA needs an initial full sync plus a re-sync-after-outage path. Make `changed` return deletions too (currently only create/update is inferable; a soft-delete or `GET /api/v1/tasks/deleted?since=` is needed for reliable sync).

A3. CORS headers for the API (not just the GUI origin) — only if phase 2 (custom card) happens, since a Lovelace card runs in the browser and calls the API directly. Phase 1 to-do platform does not need this.

A4. Single "lists" concept in taskd — named saved filters (tag+status+priority sets) exposed via `GET /api/v1/lists`. Would let the HA integration create one to-do entity per list instead of one flat entity. Nice-to-have, not blocking; the HA options flow can define its own filter sets meanwhile.

A5. Auth token support (`Authorization: Bearer`) — even a single static token in an env var. Not needed for LAN-only v1 HA usage, but required before exposing taskd beyond the firewall, and the HA config flow would only need one extra field. Do this before HACS/public release of the integration.

A6. Idempotency for task creation — optional `client_ref`/`Idempotency-Key` header on POST, so retries from HA or n8n can't create duplicate tasks. Low priority; HA's to-do card doesn't retry aggressively.

Explicitly not worth adding now: WebSocket streaming (webhooks cover it), OAuth (overkill), batch endpoints (HA sends one mutation at a time).

## 14. Open Questions (decide while building)

- Archived tasks: exclude entirely vs. options toggle. Spec default: exclude.
- Pagination handling if task count exceeds 500 (spec: implement simple loop on `total`).
- Whether to also register the integration for HA Assist shopping-list-style voice flows — comes free with the todo platform; just verify phrasing works.
- HA version floor: target 2023.7 minimum, but develop against current stable and note any newer to-do features used (e.g. `SET_DUE_DATE` arrived later than 2023.7; feature-detect, don't hard-require).