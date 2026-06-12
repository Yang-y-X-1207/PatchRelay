from __future__ import annotations

import secrets
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from patchrelay.config import Settings


WorkerChoice = Literal["fake", "claude", "codex"]


class OnboardingError(RuntimeError):
    pass


@dataclass(frozen=True)
class InitConfigResult:
    config_path: Path
    settings: Settings
    overwritten: bool


@dataclass(frozen=True)
class SmokePlan:
    instruction: str
    worker: WorkerChoice


def init_config(config_path: str | Path = "patchrelay.yaml", *, force: bool = False) -> InitConfigResult:
    path = Path(config_path)
    if path.exists() and not force:
        raise OnboardingError(f"{path} already exists. Use --force to overwrite it.")

    repo_path = detect_git_repo(Path.cwd()) or Path.cwd()
    base_branch = detect_current_branch(repo_path) or "main"
    default_worker = detect_default_worker()
    settings = Settings.model_validate(
        {
            "server": {
                "host": "127.0.0.1",
                "port": 8787,
                "token": generate_token(),
            },
            "repo": {
                "path": str(repo_path),
                "base_branch": base_branch,
                "state_dir": ".patchrelay",
            },
            "worker": {
                "default": default_worker,
                "codex_command": "codex",
                "claude_command": "claude",
            },
            "tests": {
                "default": {
                    "command": detect_test_command(repo_path),
                }
            },
            "limits": {
                "max_log_bytes": 1_048_576,
                "max_diff_bytes": 5_242_880,
                "task_timeout_seconds": 3_600,
            },
        }
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    overwritten = path.exists()
    path.write_text(yaml.safe_dump(settings_to_yaml(settings), sort_keys=False), encoding="utf-8")
    return InitConfigResult(config_path=path, settings=settings, overwritten=overwritten)


def detect_git_repo(start: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return Path(output).resolve() if output else None


def detect_current_branch(repo_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_path,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    branch = result.stdout.strip()
    return branch or None


def detect_default_worker() -> str:
    if shutil.which("claude"):
        return "claude"
    if shutil.which("codex"):
        return "codex"
    return "fake"


def detect_test_command(repo_path: Path) -> list[str]:
    if (repo_path / "pyproject.toml").exists():
        return ["python", "-m", "pytest"]
    if (repo_path / "package.json").exists():
        return ["npm", "test"]
    return ["python", "-c", "print('tests ok')"]


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def settings_to_yaml(settings: Settings) -> dict[str, Any]:
    return {
        "server": {
            "host": settings.server.host,
            "port": settings.server.port,
            "token": settings.server.token,
        },
        "repo": {
            "path": str(settings.repo.path),
            "base_branch": settings.repo.base_branch,
            "state_dir": str(settings.repo.state_dir),
        },
        "worker": {
            "default": settings.worker.default,
            "codex_command": settings.worker.codex_command,
            "claude_command": settings.worker.claude_command,
        },
        "tests": {
            name: {"command": profile.command}
            for name, profile in settings.tests.items()
        },
        "limits": {
            "max_log_bytes": settings.limits.max_log_bytes,
            "max_diff_bytes": settings.limits.max_diff_bytes,
            "task_timeout_seconds": settings.limits.task_timeout_seconds,
        },
    }


def smoke_plan(worker: WorkerChoice) -> SmokePlan:
    if worker == "fake":
        return SmokePlan("PatchRelay smoke test: write fake-change.txt", worker)
    return SmokePlan(
        "PatchRelay smoke test: add a short Smoke Test section to README.md.",
        worker,
    )


def generate_openclaw_commands(settings: Settings, plugin_root: Path | None = None) -> list[str]:
    root = plugin_root or default_openclaw_plugin_root()
    base_url = f"http://{settings.server.host}:{settings.server.port}"
    token = settings.server.token
    return [
        f"cd {quote_powershell_path(root)}",
        "npm run plugin:validate",
        f"openclaw plugins install {quote_powershell_path(root)} --link",
        openclaw_config_patch_command(base_url, token),
        "openclaw plugins inspect patchrelay --runtime --json",
        openclaw_gateway_smoke_command(),
    ]


def default_openclaw_plugin_root() -> Path:
    return Path(__file__).resolve().parents[3] / "plugins" / "openclaw"


def quote_powershell_path(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def openclaw_config_patch_command(base_url: str, token: str) -> str:
    return (
        "@'\n"
        "{\n"
        "  plugins: {\n"
        "    entries: {\n"
        "      patchrelay: {\n"
        "        enabled: true,\n"
        "        config: {\n"
        f'          baseUrl: "{base_url}",\n'
        f'          token: "{token}"\n'
        "        }\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
        "'@ | openclaw config patch --stdin"
    )


def openclaw_gateway_smoke_command() -> str:
    return (
        "$body = @{\n"
        '  name = "patchrelay_submit_task"\n'
        "  args = @{\n"
        '    instruction = "PatchRelay smoke test through OpenClaw Gateway"\n'
        '    worker = "fake"\n'
        '    testProfile = "default"\n'
        "  }\n"
        "} | ConvertTo-Json -Depth 8\n\n"
        "Invoke-RestMethod `\n"
        "  -Method Post `\n"
        '  -Uri "http://127.0.0.1:19001/tools/invoke" `\n'
        '  -Headers @{ Authorization = "Bearer openclaw-local-token" } `\n'
        '  -ContentType "application/json" `\n'
        "  -Body $body"
    )
