from __future__ import annotations

from typing import Any

from textual.containers import Horizontal, Vertical
from textual.widgets import Label, Select, Static, TextArea


ARTIFACT_VIEWS = [
    ("Summary", "summary"),
    ("Tests", "tests"),
    ("Worker", "worker"),
    ("Diff", "diff"),
    ("Log", "log"),
]


def _format_text(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value or "-"
    if isinstance(value, dict):
        return "\n".join(f"{key}: {value[key]}" for key in sorted(value)) or "-"
    if isinstance(value, list):
        return "\n".join(str(item) for item in value) or "-"
    return str(value)


class TaskArtifactsPane(Static):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._current_task: dict[str, Any] | None = None
        self._current_display: dict[str, Any] = {}
        self._view = "summary"

    def compose(self):
        with Vertical():
            yield Static("Artifacts", classes="panel-title")
            with Horizontal(id="artifact-toolbar"):
                yield Select(ARTIFACT_VIEWS, prompt="Artifact", value="summary", id="artifact-view")
                yield Label("", id="artifact-meta")
            yield TextArea("", id="artifact-text", read_only=True, show_line_numbers=False, soft_wrap=False)

    def show_empty(self, message: str = "No task selected.") -> None:
        self._current_task = None
        self._current_display = {}
        self._view = "summary"
        self.query_one("#artifact-meta", Static).update("")
        self.query_one("#artifact-text", TextArea).load_text(message)

    def show_error(self, message: str) -> None:
        self._current_task = None
        self._current_display = {}
        self.query_one("#artifact-meta", Static).update("error")
        self.query_one("#artifact-text", TextArea).load_text(f"error: {message}")

    def show_task(self, task: dict[str, Any], *, display: dict[str, Any] | None = None) -> None:
        self._current_task = task
        self._current_display = display or {}
        self._render()

    def on_select_changed(self, event) -> None:  # noqa: ANN001
        if event.select.id != "artifact-view":
            return
        self._view = str(event.value or "summary")
        self._render()

    def set_view(self, view: str) -> None:
        self._view = view if view in {artifact_view for _, artifact_view in ARTIFACT_VIEWS} else "summary"
        select = self.query_one("#artifact-view", Select)
        if select.value != self._view:
            select.value = self._view
        self._render()

    def current_view(self) -> str:
        return self._view

    def _render(self) -> None:
        if not self._current_task:
            return
        header = (
            self._current_display.get("header")
            if isinstance(self._current_display.get("header"), dict)
            else {}
        )
        summary = (
            self._current_display.get("summary")
            if isinstance(self._current_display.get("summary"), dict)
            else {}
        )
        tests = (
            self._current_display.get("tests")
            if isinstance(self._current_display.get("tests"), dict)
            else {}
        )
        worker = (
            self._current_display.get("worker")
            if isinstance(self._current_display.get("worker"), dict)
            else {}
        )
        diff_text = _format_text(self._current_display.get("diff"))
        log_text = _format_text(self._current_display.get("log"))
        artifact_meta = self.query_one("#artifact-meta", Static)
        artifact_text = self.query_one("#artifact-text", TextArea)

        if self._view == "summary":
            artifact_meta.update(
                f"{header.get('taskId') or self._current_task.get('taskId') or '-'}"
                f" | {header.get('status') or self._current_task.get('status') or '-'}"
                f" | {header.get('changedFiles') or summary.get('changedFiles') or []}"
            )
            artifact_text.load_text(_format_text(summary))
        elif self._view == "tests":
            artifact_meta.update(f"test status: {tests.get('status') or header.get('testStatus') or '-'}")
            artifact_text.load_text(_format_text(tests))
        elif self._view == "worker":
            artifact_meta.update(f"worker: {worker.get('worker') or header.get('worker') or '-'}")
            artifact_text.load_text(_format_text(worker))
        elif self._view == "diff":
            artifact_meta.update("diff")
            artifact_text.load_text(diff_text)
        else:
            artifact_meta.update("log")
            artifact_text.load_text(log_text)
