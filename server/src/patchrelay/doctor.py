from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from patchrelay.config import Settings, command_to_display
from patchrelay.git_workspace import GitWorkspaceError, GitWorkspaceManager


def run_doctor(settings: Settings) -> dict[str, Any]:
    checks = [
        check_repo(settings),
        check_command("git", ["git", "--version"], "Install Git and make sure it is available on PATH."),
        check_worker_command("codex", settings.worker.codex_command),
        check_worker_command("claude", settings.worker.claude_command),
        check_tests(settings),
    ]
    return {"ok": all(check["ok"] for check in checks), "checks": checks}


def config_error_result(message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "checks": [
            {
                "name": "config",
                "ok": False,
                "message": message,
                "hint": "Fix the YAML structure or validation error in the selected patchrelay.yaml file.",
            }
        ],
    }


def check_repo(settings: Settings) -> dict[str, Any]:
    repo_path = settings.repo.path
    if not repo_path.exists():
        return {
            "name": "repo",
            "ok": False,
            "message": f"Repository path does not exist: {repo_path}",
            "hint": "Update repo.path to an existing Git repository path.",
        }

    manager = GitWorkspaceManager(repo_path, settings.repo.state_dir, settings.repo.base_branch)
    try:
        manager.validate()
    except GitWorkspaceError as exc:
        return {
            "name": "repo",
            "ok": False,
            "message": str(exc),
            "hint": repo_hint(repo_path, settings.repo.base_branch, str(exc)),
        }
    return {
        "name": "repo",
        "ok": True,
        "message": f"{repo_path} on base branch {settings.repo.base_branch}",
        "hint": "",
    }


def repo_hint(repo_path: Path, base_branch: str, message: str) -> str:
    if "not a git repository" in message.lower() or "not a git repo" in message.lower():
        return "Update repo.path to a Git repository, or run git init in the selected directory."

    branches = list_branches(repo_path)
    if branches:
        branch_text = ", ".join(branches)
        if base_branch not in branches:
            return (
                f"Base branch '{base_branch}' does not exist. "
                f"Available branches: {branch_text}. Update repo.base_branch."
            )
    return "Check repo.path and repo.base_branch, then rerun patchrelay doctor."


def list_branches(repo_path: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "branch", "--format=%(refname:short)"],
            cwd=repo_path,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def check_command(name: str, command: list[str], failure_hint: str) -> dict[str, Any]:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"name": name, "ok": False, "message": str(exc), "hint": failure_hint}
    output = (result.stdout or result.stderr).strip()
    ok = result.returncode == 0
    return {
        "name": name,
        "ok": ok,
        "message": output,
        "hint": "" if ok else failure_hint,
    }


def check_worker_command(name: str, command: str | list[str]) -> dict[str, Any]:
    executable = command[0] if isinstance(command, list) else command
    found = shutil.which(executable)
    display = command_to_display(command)
    return {
        "name": f"worker:{name}",
        "ok": found is not None,
        "message": found or f"{display} not found on PATH",
        "hint": "" if found else f"Install {name}, add it to PATH, or update worker.{name}_command in patchrelay.yaml.",
    }


def check_tests(settings: Settings) -> dict[str, Any]:
    profile_names = sorted(settings.tests.keys())
    default = settings.tests.get("default")
    if default is None:
        return {
            "name": "tests",
            "ok": False,
            "message": f"configured profiles: {', '.join(profile_names) or '-'}",
            "hint": "Add tests.default.command to patchrelay.yaml.",
        }
    if not default.command:
        return {
            "name": "tests",
            "ok": False,
            "message": "tests.default.command is empty",
            "hint": "Set tests.default.command to a command such as ['python', '-m', 'pytest'].",
        }
    return {
        "name": "tests",
        "ok": True,
        "message": f"configured profiles: {', '.join(profile_names)}",
        "hint": "",
    }
