from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Select, Static

from patchrelay.tui.client import PatchRelayClient
from patchrelay.tui.screens.task_detail import TaskDetailPane
from patchrelay.tui.screens.task_submit import TaskSubmitScreen
from patchrelay.tui.screens.setup_wizard import SetupWizardScreen
from patchrelay.tui.widgets.live_log import LiveLog
from patchrelay.tui.widgets.status_badge import StatusBadge
from patchrelay.tui.widgets.task_table import TaskTable
from patchrelay.tui.widgets.task_artifacts import TaskArtifactsPane


TASK_FILTERS = [
    ("All", "all"),
    ("Active", "active"),
    ("Queued", "queued"),
    ("Working", "working"),
    ("Done", "done"),
    ("Failed", "failed"),
    ("Canceled", "canceled"),
]

VIEW_OPTIONS = [
    ("Overview", "overview"),
    ("Details", "details"),
    ("Artifacts", "artifacts"),
    ("Events", "events"),
    ("Logs", "logs"),
]

CANCELLABLE_STATUSES = {"submitted", "queued", "working"}


def _task_id_from_row(row_key: Any) -> str | None:
    if row_key is None:
        return None
    value = getattr(row_key, "value", None)
    if isinstance(value, str) and value:
        return value
    text = str(row_key).strip()
    return text or None


def _task_status(task: dict[str, Any]) -> str:
    return str(task.get("status") or "unknown").lower()


def _task_phase(task: dict[str, Any]) -> str:
    return str(task.get("phase") or "").lower()


def _task_worktree_path(task: dict[str, Any] | None) -> Path | None:
    if not task:
        return None
    value = task.get("worktreePath")
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value).expanduser()


def _task_action_state(task: dict[str, Any] | None) -> dict[str, bool]:
    if not task:
        return {"has_task": False, "can_cancel": False, "has_worktree": False}
    return {
        "has_task": True,
        "can_cancel": _task_status(task) in CANCELLABLE_STATUSES,
        "has_worktree": _task_worktree_path(task) is not None,
    }


def _open_path(path: Path) -> None:
    resolved = path.expanduser()
    if os.name == "nt":
        os.startfile(str(resolved))  # type: ignore[attr-defined]
        return
    command = ["open"] if sys.platform == "darwin" else ["xdg-open"]
    subprocess.Popen(
        [*command, str(resolved)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


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
    def __init__(self, client: PatchRelayClient, refresh_interval: float = 2.0) -> None:
        super().__init__()
        self.client = client
        self.refresh_interval = refresh_interval
        self._tasks: list[dict[str, Any]] = []
        self._selected_task_id: str | None = None
        self._task_filter = "all"
        self._view_mode = "overview"
        self._refresh_paused = False

    def compose(self):
        with Horizontal(id="dashboard-toolbar"):
            yield Static("Connecting...", id="server-summary")
            yield StatusBadge("unknown", id="server-badge")
        with Horizontal(id="dashboard-controls"):
            yield Input(placeholder="Filter tasks or instruction...", id="task-search")
            yield Select(TASK_FILTERS, prompt="Filter", value="all", id="task-filter")
            yield Select(VIEW_OPTIONS, prompt="View", value="overview", id="view-switcher")
            yield Button("Refresh", id="refresh-button", variant="primary")
            yield Button("Pause", id="pause-button", variant="default")
            yield Button("Submit", id="submit-button", variant="success")
            yield Button("Setup", id="setup-button", variant="default")
        with Horizontal(id="dashboard-body"):
            yield TaskTable(id="task-table")
            with Vertical(id="task-panel"):
                with Horizontal(id="task-actions"):
                    yield Button("Cancel", id="cancel-button", variant="error")
                    yield Button("Copy ID", id="copy-id-button", variant="default")
                    yield Button("Copy Diff", id="copy-diff-button", variant="default")
                    yield Button("Copy Worktree", id="copy-worktree-button", variant="default")
                    yield Button("Open Diff", id="open-diff-button", variant="primary")
                    yield Button("Open Worktree", id="open-worktree-button", variant="primary")
                yield TaskDetailPane(id="task-detail")
                yield TaskArtifactsPane(id="artifact-pane")
                yield LiveLog(id="task-log")

    async def on_mount(self) -> None:
        self.query_one(TaskTable).configure_columns()
        self.query_one(TaskDetailPane).show_empty()
        self.query_one(TaskArtifactsPane).show_empty()
        self.query_one(LiveLog).show_events([])
        self._update_task_actions()
        await self.refresh()
        self.set_interval(self.refresh_interval, self._auto_refresh)

    async def _auto_refresh(self) -> None:
        if not self._refresh_paused:
            await self.refresh()

    async def refresh(self) -> None:
        try:
            health, tasks = await asyncio.to_thread(self._load_snapshot)
        except Exception as exc:  # noqa: BLE001
            self._show_connection_error(str(exc))
            return

        self._tasks = tasks
        filtered = self._filter_tasks(tasks)
        task_ids = {str(task.get("taskId") or "") for task in filtered if task.get("taskId")}
        if filtered and self._selected_task_id not in task_ids:
            self._selected_task_id = str(filtered[0].get("taskId") or "")
        if not filtered:
            self._selected_task_id = None

        self.query_one("#server-summary", Static).update(_render_health_summary(health))
        badge = self.query_one(StatusBadge)
        badge.set_state(health.get("status") or "unknown", detail=f"{len(filtered)} shown / {len(tasks)} total")
        self.query_one(TaskTable).set_tasks(filtered, selected_task_id=self._selected_task_id)
        self._update_task_actions()
        await self._refresh_selected_task()

    def _load_snapshot(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        health = self.client.health()
        tasks = self.client.list_tasks()
        return health, tasks

    def _filter_tasks(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        query = self.query_one("#task-search", Input).value.strip().lower()

        def matches(task: dict[str, Any]) -> bool:
            status = _task_status(task)
            phase = _task_phase(task)
            text = " ".join(
                str(task.get(field) or "")
                for field in ("taskId", "instruction", "worker", "phase", "status", "branch", "baseBranch")
            ).lower()
            if self._task_filter == "active" and status not in {"submitted", "queued", "working"}:
                return False
            if self._task_filter != "all" and self._task_filter != "active" and status != self._task_filter:
                return False
            if query and query not in text:
                return False
            if self._task_filter == "queued" and phase != "queued":
                return False
            return True

        return [task for task in tasks if matches(task)]

    async def on_data_table_row_selected(self, event) -> None:  # noqa: ANN001
        task_id = _task_id_from_row(getattr(event, "row_key", None))
        if task_id:
            self._selected_task_id = task_id
            self._update_task_actions()
            await self._refresh_selected_task()

    async def on_data_table_row_highlighted(self, event) -> None:  # noqa: ANN001
        task_id = _task_id_from_row(getattr(event, "row_key", None))
        if task_id:
            self._selected_task_id = task_id
            self._update_task_actions()
            await self._refresh_selected_task()

    async def on_select_changed(self, event) -> None:  # noqa: ANN001
        if event.select.id == "task-filter":
            self._task_filter = str(event.value or "all")
            await self.refresh()
        elif event.select.id == "view-switcher":
            self._view_mode = str(event.value or "overview")
            await self._refresh_selected_task()

    async def on_input_changed(self, event) -> None:  # noqa: ANN001
        if event.input.id == "task-search":
            await self.refresh()

    async def on_button_pressed(self, event) -> None:  # noqa: ANN001
        button_id = event.button.id
        if button_id == "refresh-button":
            await self.refresh()
        elif button_id == "pause-button":
            self._refresh_paused = not self._refresh_paused
            event.button.label = "Resume" if self._refresh_paused else "Pause"
        elif button_id == "submit-button":
            self.app.push_screen(TaskSubmitScreen(self.client), self._after_submit)
        elif button_id == "setup-button":
            self.app.push_screen(SetupWizardScreen(self.client), self._after_setup)
        elif button_id == "cancel-button":
            await self._cancel_selected_task()
        elif button_id == "copy-id-button":
            self._copy_selected_task_id()
        elif button_id == "copy-diff-button":
            self._copy_selected_diff()
        elif button_id == "copy-worktree-button":
            self._copy_selected_worktree_path()
        elif button_id == "open-diff-button":
            self._open_selected_diff()
        elif button_id == "open-worktree-button":
            self._open_selected_worktree()

    def action_refresh(self) -> None:
        self.call_later(self.refresh)

    def action_toggle_refresh(self) -> None:
        self._refresh_paused = not self._refresh_paused
        pause_button = self.query_one("#pause-button", Button)
        pause_button.label = "Resume" if self._refresh_paused else "Pause"

    def action_focus_search(self) -> None:
        self.query_one("#task-search", Input).focus()

    def action_submit_task(self) -> None:
        self.app.push_screen(TaskSubmitScreen(self.client), self._after_submit)

    def action_open_setup(self) -> None:
        self.app.push_screen(SetupWizardScreen(self.client), self._after_setup)

    def action_cancel_task(self) -> None:
        self.call_later(self._cancel_selected_task)

    def action_copy_task_id(self) -> None:
        self._copy_selected_task_id()

    def action_copy_worktree_path(self) -> None:
        self._copy_selected_worktree_path()

    def action_copy_diff(self) -> None:
        self._copy_selected_diff()

    def action_open_diff(self) -> None:
        self._open_selected_diff()

    def action_open_worktree(self) -> None:
        self._open_selected_worktree()

    def action_cycle_view(self) -> None:
        values = [value for _, value in VIEW_OPTIONS]
        current = values.index(self._view_mode) if self._view_mode in values else 0
        self._view_mode = values[(current + 1) % len(values)]
        self.query_one("#view-switcher", Select).value = self._view_mode
        self.call_later(self._refresh_selected_task)

    def action_clear_filter(self) -> None:
        search = self.query_one("#task-search", Input)
        search.value = ""
        self.call_later(self.refresh)

    def action_next_view(self) -> None:
        self.action_cycle_view()

    def action_previous_view(self) -> None:
        values = [value for _, value in VIEW_OPTIONS]
        current = values.index(self._view_mode) if self._view_mode in values else 0
        self._view_mode = values[(current - 1) % len(values)]
        self.query_one("#view-switcher", Select).value = self._view_mode
        self.call_later(self._refresh_selected_task)

    def _selected_task(self) -> dict[str, Any] | None:
        if not self._selected_task_id:
            return None
        for task in self._tasks:
            if str(task.get("taskId") or "") == self._selected_task_id:
                return task
        return None

    def _update_task_actions(self) -> None:
        state = _task_action_state(self._selected_task())
        cancel_button = self.query_one("#cancel-button", Button)
        copy_id_button = self.query_one("#copy-id-button", Button)
        copy_worktree_button = self.query_one("#copy-worktree-button", Button)
        open_worktree_button = self.query_one("#open-worktree-button", Button)

        cancel_button.disabled = not state["can_cancel"]
        copy_id_button.disabled = not state["has_task"]
        copy_worktree_button.disabled = not state["has_worktree"]
        open_worktree_button.disabled = not state["has_worktree"]

    async def _cancel_selected_task(self) -> None:
        task = self._selected_task()
        if not task:
            self.app.notify("Select a task first.", title="PatchRelay", severity="warning")
            return
        if not _task_action_state(task)["can_cancel"]:
            self.app.notify("Task is already terminal.", title="PatchRelay", severity="warning")
            return
        task_id = str(task.get("taskId") or self._selected_task_id or "")
        try:
            await asyncio.to_thread(self.client.cancel_task, task_id)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Cancel failed: {exc}", title="PatchRelay", severity="error")
            return
        self.app.notify(f"Canceled task {task_id}.", title="PatchRelay", severity="information")
        await self.refresh()

    def _copy_selected_task_id(self) -> None:
        task = self._selected_task()
        if not task:
            self.app.notify("Select a task first.", title="PatchRelay", severity="warning")
            return
        task_id = str(task.get("taskId") or self._selected_task_id or "")
        if not task_id:
            self.app.notify("Task id is unavailable.", title="PatchRelay", severity="error")
            return
        self.app.copy_to_clipboard(task_id)
        self.app.notify(f"Copied task id {task_id}.", title="PatchRelay", severity="information")

    def _copy_selected_worktree_path(self) -> None:
        worktree_path = _task_worktree_path(self._selected_task())
        if worktree_path is None:
            self.app.notify("Worktree path is unavailable.", title="PatchRelay", severity="warning")
            return
        self.app.copy_to_clipboard(str(worktree_path))
        self.app.notify(f"Copied worktree path {worktree_path}.", title="PatchRelay", severity="information")

    def _selected_diff_text(self) -> str | None:
        task = self._selected_task()
        if not task:
            return None
        display = task.get("display") if isinstance(task.get("display"), dict) else {}
        diff_text = display.get("diff")
        if isinstance(diff_text, str) and diff_text.strip():
            return diff_text
        artifacts = task.get("artifacts") if isinstance(task.get("artifacts"), dict) else {}
        artifact = artifacts.get("patchrelay.diff") if isinstance(artifacts, dict) else None
        if isinstance(artifact, dict):
            content = artifact.get("content")
            if isinstance(content, str) and content.strip():
                return content
        return None

    def _copy_selected_diff(self) -> None:
        diff_text = self._selected_diff_text()
        if diff_text is None:
            self.app.notify("Diff is unavailable.", title="PatchRelay", severity="warning")
            return
        self.app.copy_to_clipboard(diff_text)
        self.app.notify("Copied diff text.", title="PatchRelay", severity="information")

    def _open_selected_diff(self) -> None:
        if self._selected_task() is None:
            self.app.notify("Select a task first.", title="PatchRelay", severity="warning")
            return
        diff_text = self._selected_diff_text()
        if diff_text is None:
            self.app.notify("Diff is unavailable.", title="PatchRelay", severity="warning")
            return
        artifact_pane = self.query_one(TaskArtifactsPane)
        artifact_pane.set_view("diff")
        self._view_mode = "artifacts"
        self.query_one("#view-switcher", Select).value = self._view_mode
        self.call_later(self._refresh_selected_task)
        self.app.notify("Focused diff artifact.", title="PatchRelay", severity="information")

    def _open_selected_worktree(self) -> None:
        worktree_path = _task_worktree_path(self._selected_task())
        if worktree_path is None:
            self.app.notify("Worktree path is unavailable.", title="PatchRelay", severity="warning")
            return
        if not worktree_path.exists():
            self.app.notify(f"Worktree not found: {worktree_path}", title="PatchRelay", severity="error")
            return
        try:
            _open_path(worktree_path)
        except Exception as exc:  # noqa: BLE001
            self.app.notify(f"Failed to open worktree: {exc}", title="PatchRelay", severity="error")
            return
        self.app.notify(f"Opened worktree {worktree_path}.", title="PatchRelay", severity="information")

    async def _refresh_selected_task(self) -> None:
        detail = self.query_one(TaskDetailPane)
        artifact = self.query_one(TaskArtifactsPane)
        log = self.query_one(LiveLog)
        if not self._selected_task_id:
            detail.show_empty()
            artifact.show_empty()
            log.show_events([])
            return
        try:
            task = await asyncio.to_thread(self.client.get_task, self._selected_task_id)
            events = await asyncio.to_thread(self.client.get_events, self._selected_task_id)
        except Exception as exc:  # noqa: BLE001
            detail.show_error(str(exc))
            artifact.show_error(str(exc))
            log.show_events([])
            return
        display = task.get("display") if isinstance(task.get("display"), dict) else {}
        detail.show_task(task, display=display, view_mode=self._view_mode)
        artifact.show_task(task, display=display)
        if self._view_mode == "events":
            log.show_events(events, compact=False)
        elif self._view_mode == "logs":
            log.show_events(events, compact=True)
        else:
            log.show_events(events, compact=self._view_mode != "overview")

    def _show_connection_error(self, message: str) -> None:
        self.query_one("#server-summary", Static).update(f"connection error: {message}")
        badge = self.query_one(StatusBadge)
        badge.set_state("error", detail="offline")
        self.query_one(TaskTable).set_tasks([])
        detail = self.query_one(TaskDetailPane)
        detail.show_error(message)
        self.query_one(TaskArtifactsPane).show_error(message)
        self.query_one(LiveLog).show_events([])
        self._selected_task_id = None

    def _after_submit(self, result: Any | None = None) -> None:
        self.call_later(self.refresh)

    def _after_setup(self, result: Any | None = None) -> None:
        self.call_later(self.refresh)
