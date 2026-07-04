from __future__ import annotations

from typing import Any


def display_task_status(task: dict[str, Any]) -> str:
    status = str(task.get("status") or "unknown").lower()
    phase = str(task.get("phase") or "").lower()
    if status == "working" and phase == "tests":
        return "testing"
    if status == "working" and phase == "artifacts":
        return "finalizing"
    return status
