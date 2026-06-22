from __future__ import annotations

from typing import Any

from textual.containers import Vertical
from textual.widgets import Static


def _format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "-"
    if isinstance(value, dict):
        return "\n".join(f"{key}: {value[key]}" for key in sorted(value)) or "-"
    return str(value)


class TaskDetailPane(Static):
    def compose(self):
        with Vertical():
            yield Static("Task details", classes="panel-title")
            yield Static("", id="detail-heading")
            yield Static("", id="detail-meta")
            yield Static("", id="detail-body")

    def show_empty(self, message: str = "Select a task to inspect.") -> None:
        self._set_heading("No task selected")
        self._set_meta("")
        self._set_body(message)

    def show_error(self, message: str) -> None:
        self._set_heading("Connection error")
        self._set_meta("")
        self._set_body(f"error: {message}")

    def show_task(self, task: dict[str, Any], *, display: dict[str, Any] | None = None, view_mode: str = "overview") -> None:
        display = display or {}
        header = display.get("header") if isinstance(display.get("header"), dict) else {}
        details = display.get("details") if isinstance(display.get("details"), dict) else {}
        summary = display.get("summary") if isinstance(display.get("summary"), dict) else {}
        tests = display.get("tests") if isinstance(display.get("tests"), dict) else {}
        latest_event = display.get("latestEvent") if isinstance(display.get("latestEvent"), dict) else {}

        self._set_heading(
            f"{header.get('taskId') or task.get('taskId') or '-'}"
            f"  [{header.get('status') or task.get('status') or '-'}]"
            f"  {header.get('phase') or task.get('phase') or '-'}"
        )

        meta_lines = [
            f"worker: {header.get('worker') or task.get('worker') or '-'}",
            f"test: {header.get('testStatus') or details.get('testStatus') or '-'}",
            f"branch: {header.get('branch') or task.get('branch') or '-'}",
            f"base: {header.get('baseBranch') or task.get('baseBranch') or '-'}",
            f"events: {header.get('eventCount') or task.get('eventCount') or 0}",
        ]
        if header.get("workerExitCode") is not None:
            meta_lines.append(f"worker exit: {header.get('workerExitCode')}")
        self._set_meta("\n".join(meta_lines))

        body_lines = [
            f"instruction: {_format_value(details.get('instruction') or task.get('instruction'))}",
            f"created: {_format_value(details.get('createdAt') or task.get('createdAt'))}",
            f"updated: {_format_value(details.get('updatedAt') or task.get('updatedAt'))}",
            f"started: {_format_value(details.get('startedAt') or task.get('startedAt'))}",
            f"completed: {_format_value(details.get('completedAt') or task.get('completedAt'))}",
            f"worktree: {_format_value(details.get('worktreePath') or task.get('worktreePath'))}",
            f"changed files: {_format_value(details.get('changedFiles') or summary.get('changedFiles'))}",
            f"test exit: {_format_value(details.get('testExitCode') or tests.get('exitCode'))}",
        ]
        if latest_event:
            body_lines.append(f"latest event: {latest_event.get('phase') or '-'}: {latest_event.get('message') or ''}")
        if task.get("error"):
            body_lines.append(f"error: {task.get('error')}")
        if view_mode == "details":
            body_lines.append("")
            body_lines.append("raw:")
            body_lines.append(_format_value(task))
        self._set_body("\n".join(body_lines))

    def _set_heading(self, text: str) -> None:
        self.query_one("#detail-heading", Static).update(text)

    def _set_meta(self, text: str) -> None:
        self.query_one("#detail-meta", Static).update(text)

    def _set_body(self, text: str) -> None:
        self.query_one("#detail-body", Static).update(text)
