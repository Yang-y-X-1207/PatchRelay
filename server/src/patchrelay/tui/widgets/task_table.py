from __future__ import annotations

from typing import Any

from textual.widgets import DataTable


class TaskTable(DataTable):
    def __init__(self) -> None:
        super().__init__()
        self._configured = False
        self._task_ids: list[str] = []

    def configure_columns(self) -> None:
        if self._configured:
            return
        self.add_column("ID", width=14)
        self.add_column("Status", width=12)
        self.add_column("Phase", width=12)
        self.add_column("Worker", width=10)
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
            updated = task.get("updatedAt") or task.get("createdAt") or "-"
            self.add_row(
                task_id[:14],
                str(task.get("status") or "-"),
                str(task.get("phase") or "-"),
                str(task.get("worker") or "-"),
                str(updated),
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
            self.move_cursor(row_index)
