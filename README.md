# ha-taskd

A [Home Assistant](https://www.home-assistant.io/) custom integration for
[taskd](https://github.com/robsterba/taskd) — a self-hosted FastAPI + SQLite
task manager.

It exposes your taskd tasks as a native Home Assistant **to-do list entity**
(`todo.taskd`), so you can view, create, complete, rename, schedule, and
delete tasks directly from HA dashboards (the built-in To-Do List card) and
HA Assist — no custom card required.

## Features

- **Native to-do entity** — works with the built-in To-Do List card and
  Assist voice commands ("add X to my taskd list").
- **Full task lifecycle** — create, complete/uncomplete, rename, update
  description, set due dates, delete.
- **Quick-add syntax** — matches the taskd GUI: `#tag` tokens become tags,
  a `!priority` token (`!urgent`, `!high`, `!medium`, `!low`) sets priority.
- **Recurrence support** — completing a recurring task from HA spawns the
  next occurrence (handled server-side by taskd).
- **Polling sync** — configurable scan interval (default 60s, min 30s).
  Changes made in the taskd GUI or via n8n appear in HA automatically.
- **`taskd.create_task` service** — for scripts and automations.
- **Source tagging** — tasks created in HA get `source: homeassistant`, so
  the taskd GUI can filter them.

### Scope notes

- Subtasks are not shown; the list contains top-level tasks only
  (`parent=none`), since HA's to-do card has no hierarchy.
- Archived tasks are excluded.
- Clearing a due date is not possible (taskd's PATCH skips null fields).

## Installation

1. Copy `custom_components/taskd/` into your Home Assistant configuration
   directory under `custom_components/taskd/`.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration**, search for
   **taskd**, and enter the base URL of your instance
   (e.g. `http://192.168.1.140:8000`). A bare `host` or `host:port` also
   works; the scheme defaults to `http` and the port to `8000`.
4. Add the built-in **To-Do List** card to a dashboard and select the
   `todo.taskd` entity.

No authentication is configured — this integration is intended for
LAN-only taskd instances.

## Services

### `taskd.create_task`

```yaml
service: taskd.create_task
data:
  name: "Backup database"
  description: "pg_dump the immich postgres container"
  priority: high        # low | medium | high | urgent
  tags: ["automated"]
  due_date: "2026-09-30T14:00:00+00:00"
```

## Entity attributes

| Attribute | Description |
|---|---|
| `total_tasks` | Number of non-archived top-level tasks |
| `overdue_count` | Incomplete tasks with a past due date |
| `last_synced` | Timestamp of the last successful poll |

## Development

Run the test suite (Home Assistant test tooling requires Linux/macOS or WSL):

```bash
./scripts/setup_wsl_testenv.sh   # one-time: Python 3.13 + pytest env in WSL
wsl bash -lc "cd /mnt/d/ai_projects/ha-taskd && ~/ha-taskd-testenv/bin/python -m pytest tests/ -q"
```

## License

MIT
