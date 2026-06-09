from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from patchrelay.config import Settings
from patchrelay.git_workspace import resolve_state_dir


CleanupStatus = Literal["planned", "removed", "skipped", "failed"]


class CleanupError(RuntimeError):
    pass


@dataclass(frozen=True)
class CleanupAction:
    kind: str
    target: str
    status: CleanupStatus
    message: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "target": self.target,
            "status": self.status,
            "message": self.message,
        }


@dataclass(frozen=True)
class CleanupResult:
    force: bool
    repo_path: Path
    state_dir: Path
    actions: list[CleanupAction]

    @property
    def ok(self) -> bool:
        return not any(action.status == "failed" for action in self.actions)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "force": self.force,
            "repoPath": str(self.repo_path),
            "stateDir": str(self.state_dir),
            "actions": [action.to_dict() for action in self.actions],
        }


@dataclass(frozen=True)
class WorktreeEntry:
    path: Path
    branch: str | None


class CleanupManager:
    def __init__(self, settings: Settings) -> None:
        self.repo_path = settings.repo.path.resolve()
        self.state_dir = resolve_state_dir(self.repo_path, settings.repo.state_dir).resolve()

    def run(self, *, force: bool = False) -> CleanupResult:
        self._ensure_repo()
        actions: list[CleanupAction] = []

        for worktree in self._patchrelay_worktrees():
            actions.append(self._remove_worktree(worktree, force))

        for branch in self._list_patchrelay_branches():
            actions.append(self._delete_branch(branch, force))

        if self.state_dir.exists():
            actions.append(self._remove_state_dir(force))

        if actions:
            actions.append(self._prune_worktrees(force))

        return CleanupResult(
            force=force,
            repo_path=self.repo_path,
            state_dir=self.state_dir,
            actions=actions,
        )

    def _patchrelay_worktrees(self) -> list[WorktreeEntry]:
        state_worktrees = self.state_dir / "worktrees"
        state_dir_is_patchrelay = self._state_dir_is_patchrelay_named()
        patchrelay_entries: list[WorktreeEntry] = []
        for entry in self._list_worktrees():
            if entry.path.resolve() == self.repo_path:
                continue
            branch = entry.branch or ""
            if branch.startswith("patchrelay/") or (
                state_dir_is_patchrelay and is_relative_to(entry.path.resolve(), state_worktrees)
            ):
                patchrelay_entries.append(entry)
        return patchrelay_entries

    def _remove_worktree(self, worktree: WorktreeEntry, force: bool) -> CleanupAction:
        target = str(worktree.path)
        if not force:
            return CleanupAction("worktree", target, "planned", worktree.branch or "detached")
        try:
            self._git(["worktree", "remove", "--force", target])
        except CleanupError as exc:
            return CleanupAction("worktree", target, "failed", str(exc))
        return CleanupAction("worktree", target, "removed", worktree.branch or "detached")

    def _delete_branch(self, branch: str, force: bool) -> CleanupAction:
        current_branch = self._current_branch()
        if branch == current_branch:
            return CleanupAction("branch", branch, "skipped", "cannot delete the current branch")
        if not force:
            return CleanupAction("branch", branch, "planned")
        try:
            self._git(["branch", "-D", branch])
        except CleanupError as exc:
            return CleanupAction("branch", branch, "failed", str(exc))
        return CleanupAction("branch", branch, "removed")

    def _remove_state_dir(self, force: bool) -> CleanupAction:
        target = str(self.state_dir)
        if not self._state_dir_is_safe_to_remove():
            return CleanupAction("state_dir", target, "skipped", "state_dir is not safe to remove")
        if not force:
            return CleanupAction("state_dir", target, "planned")
        try:
            if self.state_dir.is_dir():
                shutil.rmtree(self.state_dir)
            else:
                self.state_dir.unlink()
        except OSError as exc:
            return CleanupAction("state_dir", target, "failed", str(exc))
        return CleanupAction("state_dir", target, "removed")

    def _prune_worktrees(self, force: bool) -> CleanupAction:
        if not force:
            return CleanupAction("worktree_prune", "git worktree prune", "planned")
        try:
            self._git(["worktree", "prune"])
        except CleanupError as exc:
            return CleanupAction("worktree_prune", "git worktree prune", "failed", str(exc))
        return CleanupAction("worktree_prune", "git worktree prune", "removed")

    def _state_dir_is_safe_to_remove(self) -> bool:
        if not self._state_dir_is_patchrelay_named():
            return False
        if self.state_dir == self.repo_path:
            return False
        if self.state_dir in self.repo_path.parents:
            return False
        if self.state_dir.anchor and self.state_dir == Path(self.state_dir.anchor):
            return False
        try:
            if self.state_dir == Path.home().resolve():
                return False
        except RuntimeError:
            pass
        return True

    def _state_dir_is_patchrelay_named(self) -> bool:
        return "patchrelay" in self.state_dir.name.lower()

    def _ensure_repo(self) -> None:
        self._git(["rev-parse", "--is-inside-work-tree"])

    def _list_patchrelay_branches(self) -> list[str]:
        result = self._git(["branch", "--list", "patchrelay/*", "--format=%(refname:short)"])
        return [line.strip() for line in result.stdout.splitlines() if line.strip().startswith("patchrelay/")]

    def _current_branch(self) -> str | None:
        result = self._git(["branch", "--show-current"])
        branch = result.stdout.strip()
        return branch or None

    def _list_worktrees(self) -> list[WorktreeEntry]:
        result = self._git(["worktree", "list", "--porcelain"])
        entries: list[WorktreeEntry] = []
        current_path: Path | None = None
        current_branch: str | None = None
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                if current_path is not None:
                    entries.append(WorktreeEntry(current_path, current_branch))
                current_path = Path(line.removeprefix("worktree ").strip()).resolve()
                current_branch = None
            elif line.startswith("branch "):
                raw_branch = line.removeprefix("branch ").strip()
                current_branch = raw_branch.removeprefix("refs/heads/")
        if current_path is not None:
            entries.append(WorktreeEntry(current_path, current_branch))
        return entries

    def _git(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repo_path,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise CleanupError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result


def cleanup_patchrelay(settings: Settings, *, force: bool = False) -> CleanupResult:
    return CleanupManager(settings).run(force=force)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent.resolve())
    except ValueError:
        return False
    return True
