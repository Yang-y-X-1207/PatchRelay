from __future__ import annotations

from typing import Any

from textual.widgets import DataTable


class TaskTable(DataTable):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._configured = False
        self._task_ids: list[str] = []

    def configure_columns(self) -> None:
        if self._configured:
            return
        self.add_column("Task", width=16)
        self.add_column("Status", width=12)
        self.add_column("Phase", width=12)
        self.add_column("Worker", width=10)
        self.add_column("Test", width=10)
        self.add_column("Updated", width=20)
        self._configured = True

    def set_tasks(self, tasks: list[dict[str, Any]], *, selected_task_id: str | None = None) -> None:
        self.configure_columns()
        self.clear()
        self._task_ids = []
        for task in tasks:
            task_id = str(task.get("taskId") or "").strip()
            if not task_id:
                continue
            summary = self._summary(task)
            updated = task.get("updatedAt") or task.get("createdAt") or "-"
            self.add_row(
                task_id[:14],
                summary["status"],
                summary["phase"],
                summary["worker"],
                summary["test"],
                str(updated),
                key=task_id,
            )
            self._task_ids.append(task_id)
        if selected_task_id:
            self.highlight_task(selected_task_id)

    def highlight_task(self, task_id: str) -> None:
        try:
            row_index = self._task_ids.index(task_id)
        except ValueError:
            return
        if hasattr(self, "move_cursor"):
            self.move_cursor(row=row_index)

    def _summary(self, task: dict[str, Any]) -> dict[str, str]:
        artifacts = task.get("artifacts") if isinstance(task.get("artifacts"), dict) else {}
        summary = artifacts.get("patchrelay.summary") if isinstance(artifacts.get("patchrelay.summary"), dict) else {}
        summary_content = summary.get("content") if isinstance(summary.get("content"), dict) else {}
        tests = artifacts.get("patchrelay.tests") if isinstance(artifacts.get("patchrelay.tests"), dict) else {}
        tests_content = tests.get("content") if isinstance(tests.get("content"), dict) else {}
        return {
            "status": str(task.get("status") or "-"),
            "phase": str(task.get("phase") or "-"),
            "worker": str(task.get("worker") or "-"),
            "test": str(summary_content.get("testStatus") or tests_content.get("status") or "-"),
        }
