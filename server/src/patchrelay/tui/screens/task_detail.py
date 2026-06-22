from __future__ import annotations

from typing import Any

from textual.widgets import Static


class TaskDetailPane(Static):
    def show_empty(self, message: str = "Select a task to inspect.") -> None:
        self.update(message)

    def show_error(self, message: str) -> None:
        self.update(f"error: {message}")

    def show_task(self, task: dict[str, Any]) -> None:
        artifacts = task.get("artifacts", {})
        summary = artifacts.get("patchrelay.summary", {}).get("content") or {}
        tests = artifacts.get("patchrelay.tests", {}).get("content") or {}
        changed_files = summary.get("changedFiles") or []
        lines = [
            f"Task: {task.get('taskId') or '-'}",
            f"Status: {task.get('status') or '-'}",
            f"Phase: {task.get('phase') or '-'}",
            f"Worker: {task.get('worker') or '-'}",
            f"Test Profile: {task.get('testProfile') or '-'}",
            f"Branch: {task.get('branch') or '-'}",
            f"Base Branch: {task.get('baseBranch') or '-'}",
            f"Changed Files: {', '.join(changed_files) or '-'}",
            f"Test Status: {summary.get('testStatus') or tests.get('status') or '-'}",
        ]
        error = task.get("error")
        if error:
            lines.append(f"Error: {error}")
        self.update("\n".join(lines))

