from __future__ import annotations

import asyncio
from typing import Any

from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from patchrelay.tui.screens.task_detail import TaskDetailPane
from patchrelay.tui.widgets.live_log import LiveLog
from patchrelay.tui.widgets.status_badge import StatusBadge
from patchrelay.tui.widgets.task_table import TaskTable


def _row_key_to_task_id(row_key: Any) -> str | None:
    if row_key is None:
        return None
    value = getattr(row_key, "value", None)
    if isinstance(value, str) and value:
        return value
    text = str(row_key).strip()
    return text or None


def _render_health_summary(health: dict[str, Any]) -> str:
    config = health.get("config") if isinstance(health.get("config"), dict) else {}
    queue = health.get("queue") if isinstance(health.get("queue"), dict) else {}
    workers = health.get("workers") if isinstance(health.get("workers"), dict) else {}

    worker_bits = []
    for name, info in workers.items():
        available = isinstance(info, dict) and bool(info.get("available"))
        worker_bits.append(f"{name}:{'ok' if available else 'down'}")

    queue_bits = []
    for key in ("active", "queued", "pending", "running"):
        if key in queue:
            queue_bits.append(f"{key}={queue[key]}")

    config_bits = []
    if config.get("repoPath"):
        config_bits.append(f"repo={config['repoPath']}")
    if config.get("baseBranch"):
        config_bits.append(f"base={config['baseBranch']}")
    if config.get("defaultWorker"):
        config_bits.append(f"default={config['defaultWorker']}")

    bits = [
        f"status={health.get('status') or 'unknown'}",
        f"version={health.get('version') or '-'}",
    ]
    if config_bits:
        bits.append("config: " + ", ".join(config_bits))
    if queue_bits:
        bits.append("queue: " + ", ".join(queue_bits))
    if worker_bits:
        bits.append("workers: " + ", ".join(worker_bits))
    return " | ".join(bits)


class DashboardView(Vertical):
    def __init__(self, client: Any, refresh_interval: float = 2.0) -> None:
        super().__init__()
        self.client = client
        self.refresh_interval = refresh_interval
        self._tasks: list[dict[str, Any]] = []
        self._selected_task_id: str | None = None

    def compose(self):
        yield Static("Connecting...", id="server-summary")
        yield StatusBadge("unknown", id="server-badge")
        with Horizontal(id="dashboard-body"):
            yield TaskTable(id="task-table")
            with Vertical(id="task-panel"):
                yield TaskDetailPane(id="task-detail")
                yield LiveLog(id="task-log")

    async def on_mount(self) -> None:
        self.query_one(TaskTable).configure_columns()
        await self.refresh()
        self.set_interval(self.refresh_interval, self.refresh)

    async def refresh(self) -> None:
        try:
            health, tasks = await asyncio.to_thread(self._load_snapshot)
        except Exception as exc:  # noqa: BLE001
            self._show_connection_error(str(exc))
            return

        self._tasks = tasks
        task_ids = {str(task.get("taskId") or "") for task in tasks if task.get("taskId")}
        if tasks and self._selected_task_id not in task_ids:
            self._selected_task_id = str(tasks[0].get("taskId") or "")
        if not tasks:
            self._selected_task_id = None

        self.query_one("#server-summary", Static).update(_render_health_summary(health))
        badge = self.query_one(StatusBadge)
        badge.set_state(health.get("status") or "unknown", detail=f"{len(tasks)} tasks")
        self.query_one(TaskTable).set_tasks(tasks, selected_task_id=self._selected_task_id)
        await self._refresh_selected_task()

    async def on_data_table_row_selected(self, event) -> None:  # noqa: ANN001
        task_id = _row_key_to_task_id(getattr(event, "row_key", None))
        if task_id:
            self._selected_task_id = task_id
            await self._refresh_selected_task()

    async def on_data_table_row_highlighted(self, event) -> None:  # noqa: ANN001
        task_id = _row_key_to_task_id(getattr(event, "row_key", None))
        if task_id:
            self._selected_task_id = task_id
            await self._refresh_selected_task()

    def _load_snapshot(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        health = self.client.health()
        tasks = self.client.list_tasks()
        return health, tasks

    async def _refresh_selected_task(self) -> None:
        detail = self.query_one(TaskDetailPane)
        log = self.query_one(LiveLog)
        if not self._selected_task_id:
            detail.show_empty()
            log.show_events([])
            return
        try:
            task = await asyncio.to_thread(self.client.get_task, self._selected_task_id)
            events = await asyncio.to_thread(self.client.get_events, self._selected_task_id)
        except Exception as exc:  # noqa: BLE001
            detail.show_error(str(exc))
            log.show_events([])
            return
        detail.show_task(task)
        log.show_events(events)

    def _show_connection_error(self, message: str) -> None:
        self.query_one("#server-summary", Static).update(f"connection error: {message}")
        badge = self.query_one(StatusBadge)
        badge.set_state("error", detail="offline")
        self.query_one(TaskTable).set_tasks([])
        detail = self.query_one(TaskDetailPane)
        detail.show_error(message)
        self.query_one(LiveLog).show_events([])

