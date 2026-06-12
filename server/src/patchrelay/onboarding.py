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


@dataclass(frozen=True)
class SetupPreview:
    config_path: Path
    repo_path: Path
    base_branch: str
    worker: str
    test_command: list[str]
    server_host: str = "127.0.0.1"
    server_port: int = 8787


@dataclass(frozen=True)
class OpenClawApplyStep:
    name: str
    command: list[str]
    cwd: Path | None = None
    stdin: str | None = None

    def display_command(self) -> str:
        rendered = " ".join(quote_shell_arg(part) for part in self.command)
        if self.stdin is None:
            return rendered
        return f"<config-json> | {rendered}"


@dataclass(frozen=True)
class OpenClawApplyResult:
    step: OpenClawApplyStep
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def init_config(
    config_path: str | Path = "patchrelay.yaml",
    *,
    force: bool = False,
    repo_path: str | Path | None = None,
    base_branch: str | None = None,
    worker: str | None = None,
    test_command: list[str] | None = None,
    token: str | None = None,
) -> InitConfigResult:
    path = Path(config_path)
    if path.exists() and not force:
        raise OnboardingError(f"{path} already exists. Use --force to overwrite it.")

    preview = preview_setup(
        config_path,
        repo_path=repo_path,
        base_branch=base_branch,
        worker=worker,
        test_command=test_command,
    )
    selected_token = token or generate_token()
    settings = Settings.model_validate(
        {
            "server": {
                "host": preview.server_host,
                "port": preview.server_port,
                "token": selected_token,
            },
            "repo": {
                "path": str(preview.repo_path),
                "base_branch": preview.base_branch,
                "state_dir": ".patchrelay",
            },
            "worker": {
                "default": preview.worker,
                "codex_command": "codex",
                "claude_command": "claude",
            },
            "tests": {
                "default": {
                    "command": preview.test_command,
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


def preview_setup(
    config_path: str | Path = "patchrelay.yaml",
    *,
    repo_path: str | Path | None = None,
    base_branch: str | None = None,
    worker: str | None = None,
    test_command: list[str] | None = None,
) -> SetupPreview:
    resolved_repo_path = (
        Path(repo_path).expanduser().resolve()
        if repo_path is not None
        else detect_git_repo(Path.cwd()) or Path.cwd()
    )
    return SetupPreview(
        config_path=Path(config_path),
        repo_path=resolved_repo_path,
        base_branch=base_branch or detect_current_branch(resolved_repo_path) or "main",
        worker=worker or detect_default_worker(),
        test_command=test_command or detect_test_command(resolved_repo_path),
    )


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


def build_openclaw_apply_steps(settings: Settings, plugin_root: Path | None = None) -> list[OpenClawApplyStep]:
    root = plugin_root or default_openclaw_plugin_root()
    base_url = f"http://{settings.server.host}:{settings.server.port}"
    token = settings.server.token
    return [
        OpenClawApplyStep(
            name="validate plugin",
            command=["npm.cmd" if is_windows() else "npm", "run", "plugin:validate"],
            cwd=root,
        ),
        OpenClawApplyStep(
            name="install plugin",
            command=["openclaw", "plugins", "install", str(root), "--link"],
        ),
        OpenClawApplyStep(
            name="configure plugin",
            command=["openclaw", "config", "patch", "--stdin"],
            stdin=openclaw_config_json(base_url, token),
        ),
    ]


def apply_openclaw_config(settings: Settings, plugin_root: Path | None = None) -> list[OpenClawApplyResult]:
    results: list[OpenClawApplyResult] = []
    for step in build_openclaw_apply_steps(settings, plugin_root):
        try:
            result = subprocess.run(
                step.command,
                cwd=str(step.cwd) if step.cwd else None,
                input=step.stdin,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            results.append(OpenClawApplyResult(step=step, exit_code=127, stdout="", stderr=str(exc)))
            break
        apply_result = OpenClawApplyResult(
            step=step,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
        results.append(apply_result)
        if not apply_result.ok:
            break
    return results


def default_openclaw_plugin_root() -> Path:
    return Path(__file__).resolve().parents[3] / "plugins" / "openclaw"


def quote_powershell_path(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def quote_shell_arg(value: str) -> str:
    if not value or any(char.isspace() for char in value):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def is_windows() -> bool:
    return shutil.which("cmd.exe") is not None


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


def openclaw_config_json(base_url: str, token: str) -> str:
    return (
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
