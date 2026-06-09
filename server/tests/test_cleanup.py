import subprocess
from pathlib import Path

from patchrelay.cleanup import cleanup_patchrelay
from patchrelay.config import RepoConfig, Settings
from helpers import init_git_repo


def git_output(args: list[str], cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def add_worktree(repo: Path, path: Path, branch: str) -> None:
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(path), "main"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def test_cleanup_previews_patchrelay_targets_without_deleting(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    worktree_path = repo / ".patchrelay-test" / "worktrees" / "task-1"
    add_worktree(repo, worktree_path, "patchrelay/20260609/task-1")
    (repo / ".patchrelay-test" / "tasks.json").write_text("{}", encoding="utf-8")
    settings = Settings(repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")))

    result = cleanup_patchrelay(settings, force=False)
    actions = result.to_dict()["actions"]

    assert result.ok is True
    assert {action["kind"] for action in actions} == {"worktree", "branch", "state_dir", "worktree_prune"}
    assert all(action["status"] == "planned" for action in actions)
    assert worktree_path.exists()
    assert "patchrelay/20260609/task-1" in git_output(["branch", "--list", "patchrelay/*"], repo)
    assert (repo / ".patchrelay-test").exists()


def test_cleanup_force_removes_patchrelay_targets_and_keeps_unrelated_worktree(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    patchrelay_worktree = repo / ".patchrelay-test" / "worktrees" / "task-1"
    unrelated_worktree = tmp_path / "unrelated-worktree"
    add_worktree(repo, patchrelay_worktree, "patchrelay/20260609/task-1")
    add_worktree(repo, unrelated_worktree, "feature/keep-worktree")
    (repo / ".patchrelay-test" / "tasks.json").write_text("{}", encoding="utf-8")
    settings = Settings(repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")))

    result = cleanup_patchrelay(settings, force=True)

    assert result.ok is True
    assert patchrelay_worktree.exists() is False
    assert unrelated_worktree.exists()
    assert git_output(["branch", "--list", "patchrelay/*"], repo) == ""
    assert "feature/keep-worktree" in git_output(["branch", "--list", "feature/*"], repo)
    assert (repo / ".patchrelay-test").exists() is False


def test_cleanup_skips_state_dir_when_name_is_not_patchrelay(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    state_dir = repo / "state"
    state_dir.mkdir()
    (state_dir / "tasks.json").write_text("{}", encoding="utf-8")
    settings = Settings(repo=RepoConfig(path=repo, base_branch="main", state_dir=Path("state")))

    result = cleanup_patchrelay(settings, force=True)

    assert result.ok is True
    assert state_dir.exists()
    assert result.actions[0].kind == "state_dir"
    assert result.actions[0].status == "skipped"
