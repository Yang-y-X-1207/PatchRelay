import subprocess
from pathlib import Path


def init_git_repo(path: Path) -> Path:
    path.mkdir()
    run_git(["init", "-b", "main"], path)
    run_git(["config", "user.email", "patchrelay@example.test"], path)
    run_git(["config", "user.name", "PatchRelay Test"], path)
    (path / "README.md").write_text("# test repo\n", encoding="utf-8")
    run_git(["add", "README.md"], path)
    run_git(["commit", "-m", "Initial commit"], path)
    return path


def run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
