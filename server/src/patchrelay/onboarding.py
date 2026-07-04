from __future__ import annotations

import json
import secrets
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from patchrelay.config import Settings


WorkerChoice = Literal["fake", "claude", "codex"]

PATCHRELAY_OPENCLAW_TOOL_NAMES = [
    "patchrelay_submit_task",
    "patchrelay_get_task",
    "patchrelay_cancel_task",
]


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
class ConfigRepairAction:
    kind: str
    target: str
    message: str
    before: str = ""
    after: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "target": self.target,
            "message": self.message,
            "before": self.before,
            "after": self.after,
        }


@dataclass(frozen=True)
class ConfigRepairPlan:
    config_path: Path
    data: dict[str, Any] | None
    actions: list[ConfigRepairAction]
    errors: list[str]
    applied: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def changed(self) -> bool:
        return bool(self.actions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "configPath": str(self.config_path),
            "changed": self.changed,
            "applied": self.applied,
            "actions": [action.to_dict() for action in self.actions],
            "errors": self.errors,
        }


@dataclass(frozen=True)
class OpenClawApplyStep:
    name: str
    command: list[str]
    cwd: Path | None = None
    stdin: str | None = None
    config_patch: dict[str, Any] | None = None
    direct_config_patch: bool = False
    success_output_markers: tuple[str, ...] = ()

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
    settings = settings_from_preview(preview, selected_token)

    path.parent.mkdir(parents=True, exist_ok=True)
    overwritten = path.exists()
    path.write_text(yaml.safe_dump(settings_to_yaml(settings), sort_keys=False), encoding="utf-8")
    return InitConfigResult(config_path=path, settings=settings, overwritten=overwritten)


def settings_from_preview(preview: SetupPreview, token: str) -> Settings:
    return Settings.model_validate(
        {
            "server": {
                "host": preview.server_host,
                "port": preview.server_port,
                "token": token,
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


def repair_config(config_path: str | Path = "patchrelay.yaml", *, apply: bool = False) -> ConfigRepairPlan:
    plan = build_config_repair_plan(config_path)
    if not apply or not plan.ok or plan.data is None or not plan.changed:
        return plan

    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(yaml.safe_dump(plan.data, sort_keys=False), encoding="utf-8")
    except OSError as exc:
        return ConfigRepairPlan(
            config_path=plan.config_path,
            data=plan.data,
            actions=plan.actions,
            errors=[*plan.errors, f"Could not write {path}: {exc}"],
        )
    return ConfigRepairPlan(
        config_path=plan.config_path,
        data=plan.data,
        actions=plan.actions,
        errors=plan.errors,
        applied=True,
    )


def build_config_repair_plan(config_path: str | Path = "patchrelay.yaml") -> ConfigRepairPlan:
    path = Path(config_path)
    actions: list[ConfigRepairAction] = []
    errors: list[str] = []

    if not path.exists():
        preview = preview_setup(path)
        settings = settings_from_preview(preview, generate_token())
        data = settings_to_yaml(settings)
        actions.append(
            ConfigRepairAction(
                kind="create",
                target=str(path),
                message="Create config with detected local defaults.",
                after=str(path),
            )
        )
        return ConfigRepairPlan(path, data, actions, errors)

    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return ConfigRepairPlan(path, None, actions, [f"Could not read {path}: {exc}"])
    except yaml.YAMLError as exc:
        return ConfigRepairPlan(path, None, actions, [f"Invalid YAML in {path}: {exc}"])

    if loaded is None:
        data: dict[str, Any] = {}
    elif isinstance(loaded, dict):
        data = loaded
    else:
        return ConfigRepairPlan(path, None, actions, [f"{path} must contain a YAML mapping"])

    repair_server(data, actions)
    repo_path = repair_repo(data, actions, errors)
    repair_worker(data, actions)
    repair_tests(data, actions, repo_path)
    repair_limits(data, actions)

    try:
        Settings.model_validate(data)
    except Exception as exc:
        errors.append(f"Config still does not validate after planned repairs: {exc}")

    return ConfigRepairPlan(path, data, actions, errors)


def repair_server(data: dict[str, Any], actions: list[ConfigRepairAction]) -> None:
    server = ensure_mapping(data, "server", actions)
    host = server.get("host")
    if not isinstance(host, str) or not host.strip():
        replace_value(server, "host", "127.0.0.1", "server.host", actions, "Set default loopback host.")
    port = server.get("port")
    if not isinstance(port, int) or port <= 0:
        replace_value(server, "port", 8787, "server.port", actions, "Set default server port.")

    token = server.get("token")
    if not isinstance(token, str) or not token.strip() or token == "change-me":
        replace_value(
            server,
            "token",
            generate_token(),
            "server.token",
            actions,
            "Replace blank/default token with a generated token.",
            redact=True,
        )


def repair_repo(data: dict[str, Any], actions: list[ConfigRepairAction], errors: list[str]) -> Path:
    repo = ensure_mapping(data, "repo", actions)
    detected_repo = detect_git_repo(Path.cwd())
    configured_path = repo.get("path")
    repo_path = path_from_config_value(configured_path)
    if repo_path is None or not repo_path.exists() or detect_git_repo(repo_path) is None:
        if detected_repo is None:
            errors.append("Could not detect a Git repository for repo.path.")
            repo_path = repo_path or Path.cwd()
        else:
            replace_value(
                repo,
                "path",
                str(detected_repo),
                "repo.path",
                actions,
                "Point repo.path at the detected Git repository.",
            )
            repo_path = detected_repo

    state_dir = repo.get("state_dir")
    if not isinstance(state_dir, str) or not state_dir.strip():
        replace_value(repo, "state_dir", ".patchrelay", "repo.state_dir", actions, "Set default PatchRelay state dir.")

    base_branch = repo.get("base_branch")
    if not isinstance(base_branch, str) or not base_branch.strip() or not git_ref_exists(repo_path, base_branch):
        detected_branch = detect_current_branch(repo_path) or "main"
        replace_value(
            repo,
            "base_branch",
            detected_branch,
            "repo.base_branch",
            actions,
            "Use a base branch that exists in the configured repository.",
        )

    return repo_path


def repair_worker(data: dict[str, Any], actions: list[ConfigRepairAction]) -> None:
    worker = ensure_mapping(data, "worker", actions)
    default_worker = worker.get("default")
    if default_worker not in {"auto", "fake", "codex", "claude"}:
        replace_value(
            worker,
            "default",
            detect_default_worker(),
            "worker.default",
            actions,
            "Set default worker to an available local default.",
        )
    ensure_command_value(worker, "codex_command", "codex", "worker.codex_command", actions, "Set default Codex command.")
    ensure_command_value(worker, "claude_command", "claude", "worker.claude_command", actions, "Set default Claude command.")


def repair_tests(data: dict[str, Any], actions: list[ConfigRepairAction], repo_path: Path) -> None:
    tests = ensure_mapping(data, "tests", actions)
    default_profile = tests.get("default")
    command = default_profile.get("command") if isinstance(default_profile, dict) else None
    if isinstance(command, str) and command.strip():
        try:
            repaired_command = shlex.split(command)
        except ValueError:
            repaired_command = detect_test_command(repo_path)
            message = "Replace invalid default test command with detected command."
        else:
            message = "Convert default test command from string to argv list."
        tests["default"] = {"command": repaired_command}
        actions.append(
            ConfigRepairAction(
                kind="update",
                target="tests.default.command",
                message=message,
                before=command,
                after=" ".join(repaired_command),
            )
        )
        return
    if not isinstance(default_profile, dict) or not isinstance(command, list) or not command:
        detected_command = detect_test_command(repo_path)
        tests["default"] = {"command": detected_command}
        actions.append(
            ConfigRepairAction(
                kind="update",
                target="tests.default.command",
                message="Set default test profile command.",
                before=value_to_display(default_profile),
                after=" ".join(detected_command),
            )
        )


def repair_limits(data: dict[str, Any], actions: list[ConfigRepairAction]) -> None:
    limits = ensure_mapping(data, "limits", actions)
    ensure_positive_int(
        limits,
        "max_log_bytes",
        1_048_576,
        "limits.max_log_bytes",
        actions,
        "Set default log capture limit.",
    )
    ensure_positive_int(
        limits,
        "max_diff_bytes",
        5_242_880,
        "limits.max_diff_bytes",
        actions,
        "Set default diff capture limit.",
    )
    ensure_positive_int(
        limits,
        "task_timeout_seconds",
        3_600,
        "limits.task_timeout_seconds",
        actions,
        "Set default task timeout.",
    )


def ensure_mapping(
    data: dict[str, Any],
    key: str,
    actions: list[ConfigRepairAction],
) -> dict[str, Any]:
    current = data.get(key)
    if isinstance(current, dict):
        return current
    data[key] = {}
    actions.append(
        ConfigRepairAction(
            kind="update",
            target=key,
            message=f"Create {key} mapping.",
            before=value_to_display(current),
            after="{}",
        )
    )
    return data[key]


def ensure_value(
    data: dict[str, Any],
    key: str,
    value: Any,
    target: str,
    actions: list[ConfigRepairAction],
    message: str,
) -> None:
    if key not in data:
        replace_value(data, key, value, target, actions, message)


def ensure_command_value(
    data: dict[str, Any],
    key: str,
    value: str,
    target: str,
    actions: list[ConfigRepairAction],
    message: str,
) -> None:
    current = data.get(key)
    if isinstance(current, str) and current.strip():
        return
    if isinstance(current, list) and current and all(isinstance(part, str) and part for part in current):
        return
    replace_value(data, key, value, target, actions, message)


def ensure_positive_int(
    data: dict[str, Any],
    key: str,
    value: int,
    target: str,
    actions: list[ConfigRepairAction],
    message: str,
) -> None:
    current = data.get(key)
    if isinstance(current, int) and current > 0:
        return
    replace_value(data, key, value, target, actions, message)


def replace_value(
    data: dict[str, Any],
    key: str,
    value: Any,
    target: str,
    actions: list[ConfigRepairAction],
    message: str,
    *,
    redact: bool = False,
) -> None:
    before = "<redacted>" if redact and key in data else value_to_display(data.get(key))
    data[key] = value
    after = "<generated>" if redact else value_to_display(value)
    actions.append(
        ConfigRepairAction(
            kind="update",
            target=target,
            message=message,
            before=before,
            after=after,
        )
    )


def path_from_config_value(value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value).expanduser().resolve()


def git_ref_exists(repo_path: Path, ref: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            cwd=repo_path,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def value_to_display(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(part) for part in value)
    return str(value)


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
    skill_root = default_openclaw_skill_root(root)
    base_url = f"http://{settings.server.host}:{settings.server.port}"
    token = settings.server.token
    return [
        f"cd {quote_powershell_path(root)}",
        "npm run plugin:validate",
        f"openclaw plugins install {quote_powershell_path(root)} --link",
        openclaw_config_patch_command(base_url, token),
        f"openclaw skills install {quote_powershell_path(skill_root)} --global",
        openclaw_skill_config_patch_command(),
        openclaw_tool_policy_config_patch_command(),
        "openclaw skills info patchrelay",
        "openclaw skills check",
        "openclaw plugins inspect patchrelay --runtime --json",
        openclaw_gateway_smoke_command(),
    ]


def build_openclaw_apply_steps(settings: Settings, plugin_root: Path | None = None) -> list[OpenClawApplyStep]:
    root = plugin_root or default_openclaw_plugin_root()
    skill_root = default_openclaw_skill_root(root)
    base_url = f"http://{settings.server.host}:{settings.server.port}"
    token = settings.server.token
    openclaw = openclaw_executable()
    return [
        OpenClawApplyStep(
            name="validate plugin",
            command=["npm.cmd" if is_windows() else "npm", "run", "plugin:validate"],
            cwd=root,
        ),
        OpenClawApplyStep(
            name="install plugin",
            command=[openclaw, "plugins", "install", str(root), "--link"],
            config_patch=openclaw_plugin_link_config_patch(root),
            direct_config_patch=True,
        ),
        OpenClawApplyStep(
            name="configure plugin",
            command=[openclaw, "config", "patch", "--stdin"],
            stdin=openclaw_config_json(base_url, token),
            config_patch=openclaw_config_patch(base_url, token),
        ),
        OpenClawApplyStep(
            name="install skill",
            command=[openclaw, "skills", "install", str(skill_root), "--global"],
            success_output_markers=("Skill already exists",),
        ),
        OpenClawApplyStep(
            name="enable skill",
            command=[openclaw, "config", "patch", "--stdin"],
            stdin=openclaw_skill_config_json(),
            config_patch=openclaw_skill_config_patch(),
        ),
        OpenClawApplyStep(
            name="allow plugin tools",
            command=[openclaw, "config", "patch", "--stdin"],
            stdin=openclaw_tool_policy_config_json(),
            config_patch=openclaw_tool_policy_config_patch(),
            direct_config_patch=True,
        ),
    ]


def apply_openclaw_config(settings: Settings, plugin_root: Path | None = None) -> list[OpenClawApplyResult]:
    results: list[OpenClawApplyResult] = []
    for step in build_openclaw_apply_steps(settings, plugin_root):
        if step.direct_config_patch and step.config_patch is not None:
            apply_result = apply_openclaw_config_patch_directly(step, step.config_patch)
            results.append(apply_result)
            if not apply_result.ok:
                break
            continue
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
        if not apply_result.ok and step.success_output_markers:
            output = f"{apply_result.stdout}\n{apply_result.stderr}"
            if any(marker in output for marker in step.success_output_markers):
                apply_result = OpenClawApplyResult(
                    step=step,
                    exit_code=0,
                    stdout=apply_result.stdout,
                    stderr=apply_result.stderr,
                )
        if not apply_result.ok and step.config_patch is not None and openclaw_write_guard_rejected(apply_result):
            apply_result = apply_openclaw_config_patch_directly(step, step.config_patch)
        results.append(apply_result)
        if not apply_result.ok:
            break
    return results


def openclaw_write_guard_rejected(result: OpenClawApplyResult) -> bool:
    output = f"{result.stdout}\n{result.stderr}"
    return "Config write rejected" in output and "size-drop" in output


def apply_openclaw_config_patch_directly(
    step: OpenClawApplyStep,
    patch: dict[str, Any],
) -> OpenClawApplyResult:
    try:
        config_path = openclaw_config_file_path()
        original_bytes = config_path.read_bytes()
        original_text = original_bytes.decode("utf-8-sig")
        current = json.loads(original_text) if original_text.strip() else {}
        if not isinstance(current, dict):
            raise OnboardingError(f"{config_path} must contain a JSON object")
        merge_config_patch(current, patch)
        config_path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = subprocess.run(
            [openclaw_executable(), "config", "validate"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if validation.returncode != 0:
            config_path.write_bytes(original_bytes)
            return OpenClawApplyResult(
                step=step,
                exit_code=validation.returncode,
                stdout=validation.stdout,
                stderr=f"Direct config patch failed validation and was rolled back.\n{validation.stderr}",
            )
        return OpenClawApplyResult(
            step=step,
            exit_code=0,
            stdout="Applied OpenClaw config patch directly.\n" + validation.stdout,
            stderr="",
        )
    except Exception as exc:
        return OpenClawApplyResult(step=step, exit_code=1, stdout="", stderr=str(exc))


def openclaw_config_file_path() -> Path:
    result = subprocess.run(
        [openclaw_executable(), "config", "file"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).expanduser()
    return Path.home() / ".openclaw" / "openclaw.json"


def merge_config_patch(target: dict[str, Any], patch: dict[str, Any], path: tuple[str, ...] = ()) -> None:
    for key, value in patch.items():
        next_path = (*path, key)
        if value is None:
            target.pop(key, None)
            continue
        existing = target.get(key)
        if (
            next_path in {("plugins", "load", "paths"), ("tools", "alsoAllow")}
            and isinstance(existing, list)
            and isinstance(value, list)
        ):
            target[key] = merge_unique_strings(existing, value)
        elif isinstance(existing, dict) and isinstance(value, dict):
            merge_config_patch(existing, value, next_path)
        else:
            target[key] = value


def merge_unique_strings(existing: list[Any], additions: list[Any]) -> list[Any]:
    merged = list(existing)
    seen = {item for item in merged if isinstance(item, str)}
    for item in additions:
        if isinstance(item, str) and item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


def default_openclaw_plugin_root() -> Path:
    return Path(__file__).resolve().parents[3] / "plugins" / "openclaw"


def default_openclaw_skill_root(plugin_root: Path) -> Path:
    return plugin_root / "skills" / "patchrelay"


def quote_powershell_path(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def quote_shell_arg(value: str) -> str:
    if not value or any(char.isspace() for char in value):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def is_windows() -> bool:
    return shutil.which("cmd.exe") is not None


def openclaw_executable() -> str:
    if is_windows():
        for executable in ("openclaw.cmd", "openclaw.exe", "openclaw.bat"):
            resolved = shutil.which(executable)
            if resolved is not None:
                return resolved
    return shutil.which("openclaw") or "openclaw"


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


def openclaw_config_patch(base_url: str, token: str) -> dict[str, Any]:
    return {
        "plugins": {
            "entries": {
                "patchrelay": {
                    "enabled": True,
                    "config": {
                        "baseUrl": base_url,
                        "token": token,
                    },
                }
            }
        }
    }


def openclaw_plugin_link_config_patch(plugin_root: Path) -> dict[str, Any]:
    return {
        "plugins": {
            "load": {
                "paths": [str(plugin_root)],
            },
            "entries": {
                "patchrelay": {
                    "enabled": True,
                }
            },
        }
    }


def openclaw_skill_config_patch_command() -> str:
    return "@'\n" + openclaw_skill_config_json() + "'@ | openclaw config patch --stdin"


def openclaw_tool_policy_config_patch_command() -> str:
    return "@'\n" + openclaw_tool_policy_config_json() + "'@ | openclaw config patch --stdin"


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


def openclaw_skill_config_json() -> str:
    return (
        "{\n"
        "  skills: {\n"
        "    entries: {\n"
        "      patchrelay: { enabled: true }\n"
        "    }\n"
        "  }\n"
        "}\n"
    )


def openclaw_skill_config_patch() -> dict[str, Any]:
    return {
        "skills": {
            "entries": {
                "patchrelay": {
                    "enabled": True,
                }
            }
        }
    }


def openclaw_tool_policy_config_json() -> str:
    rendered_tools = ", ".join(f'"{tool_name}"' for tool_name in PATCHRELAY_OPENCLAW_TOOL_NAMES)
    return (
        "{\n"
        "  tools: {\n"
        f"    alsoAllow: [{rendered_tools}]\n"
        "  }\n"
        "}\n"
    )


def openclaw_tool_policy_config_patch() -> dict[str, Any]:
    return {
        "tools": {
            "alsoAllow": PATCHRELAY_OPENCLAW_TOOL_NAMES,
        }
    }


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
