from __future__ import annotations

from patchrelay.tui.screens.dashboard import _task_action_state, _task_worktree_path
from patchrelay.tui.widgets.task_artifacts import ARTIFACT_VIEWS, TaskArtifactsPane


def test_task_action_state_tracks_cancellable_tasks() -> None:
    queued_task = {"taskId": "task-1", "status": "queued"}
    done_task = {"taskId": "task-2", "status": "completed"}

    assert _task_action_state(queued_task) == {
        "has_task": True,
        "can_cancel": True,
        "has_worktree": False,
    }
    assert _task_action_state(done_task)["can_cancel"] is False


def test_task_worktree_path_returns_none_without_value() -> None:
    assert _task_worktree_path(None) is None
    assert _task_worktree_path({"taskId": "task-1"}) is None


def test_task_artifacts_set_view_normalizes_invalid_view() -> None:
    pane = TaskArtifactsPane()
    assert ("Diff", "diff") in ARTIFACT_VIEWS
    assert pane.current_view() == "summary"
