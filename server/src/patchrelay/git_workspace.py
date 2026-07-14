from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class GitWorkspaceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Workspace:
    repo_path: Path
    branch: str
    worktree_path: Path
    base_branch: str


class GitWorkspaceManager:
    def __init__(self, repo_path: Path, state_dir: Path, base_branch: str) -> None:
        self.repo_path = repo_path.resolve()
        self.state_dir = resolve_state_dir(self.repo_path, state_dir)
        self.base_branch = base_branch

    def create(self, task_id: str) -> Workspace:
        self._ensure_repo()
        short_id = task_id[:12]
        day = datetime.now(UTC).strftime("%Y%m%d")
        branch = f"patchrelay/{day}/{short_id}"
        worktree_path = self.state_dir / "worktrees" / short_id
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        if worktree_path.exists():
            raise GitWorkspaceError(f"Worktree path already exists: {worktree_path}")

        self._git(["rev-parse", "--verify", self.base_branch])
        self._git(["worktree", "add", "-b", branch, str(worktree_path), self.base_branch])
        return Workspace(
            repo_path=self.repo_path,
            branch=branch,
            worktree_path=worktree_path,
            base_branch=self.base_branch,
        )

    def attach(self, branch: str, worktree_path: Path) -> Workspace:
        """Reuse an existing worktree/branch instead of creating a new one.

        Used for shared-worktree handoff: a child task continues editing the
        parent's worktree so changes accumulate on the same branch. The final
        diff therefore reflects the whole handoff chain, not just one worker.
        """
        self._ensure_repo()
        if not worktree_path.exists():
            raise GitWorkspaceError(f"Shared worktree path does not exist: {worktree_path}")
        return Workspace(
            repo_path=self.repo_path,
            branch=branch,
            worktree_path=worktree_path,
            base_branch=self.base_branch,
        )

    def validate(self) -> None:
        self._ensure_repo()
        self._git(["rev-parse", "--verify", self.base_branch])

    def collect_changed_files(self, worktree_path: Path) -> list[str]:
        output = self._git(["status", "--porcelain"], cwd=worktree_path).stdout
        files: list[str] = []
        for line in output.splitlines():
            if not line:
                continue
            files.append(line[3:].strip())
        return files

    def collect_diff(self, worktree_path: Path) -> str:
        diff = self._git(["diff", "--binary"], cwd=worktree_path).stdout
        untracked = self._git(["ls-files", "--others", "--exclude-standard"], cwd=worktree_path).stdout
        extra_diffs: list[str] = []
        for relative_path in [line.strip() for line in untracked.splitlines() if line.strip()]:
            extra_diffs.append(self._git(["diff", "--no-index", "--", "NUL", relative_path], cwd=worktree_path, allow_exit_codes={1}).stdout)
        return "\n".join(part for part in [diff, *extra_diffs] if part)

    def _ensure_repo(self) -> None:
        if not self.repo_path.exists():
            raise GitWorkspaceError(f"Repository path does not exist: {self.repo_path}")
        self._git(["rev-parse", "--is-inside-work-tree"])

    def _git(
        self,
        args: list[str],
        cwd: Path | None = None,
        allow_exit_codes: set[int] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = ["git", *args]
        result = subprocess.run(
            command,
            cwd=str(cwd or self.repo_path),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        allowed = allow_exit_codes or {0}
        if result.returncode not in allowed:
            raise GitWorkspaceError(
                f"git {' '.join(args)} failed with exit code {result.returncode}: {result.stderr.strip()}"
            )
        return result


def resolve_state_dir(repo_path: Path, state_dir: Path) -> Path:
    if state_dir.is_absolute():
        return state_dir
    return repo_path / state_dir


def remove_worktree_path(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
