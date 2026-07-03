from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import urlparse

import httpx
import psutil

from patchrelay.config import Settings
from patchrelay.git_workspace import resolve_state_dir
from patchrelay.workers import command_to_argv, terminate_process_tree


@dataclass(frozen=True)
class RuntimeOptions:
    config_path: str
    gateway_url: str
    gateway_token: str
    gateway_bind: str = "loopback"
    timeout_seconds: float = 15
    start_patchrelay: bool = True
    start_openclaw: bool = True
    check_workers: bool = True


def start_runtime(settings: Settings, options: RuntimeOptions) -> dict[str, Any]:
    manager = RuntimeManager(settings, options)
    return manager.start()


def stop_runtime(settings: Settings, options: RuntimeOptions) -> dict[str, Any]:
    manager = RuntimeManager(settings, options)
    return manager.stop()


def runtime_status(settings: Settings, options: RuntimeOptions) -> dict[str, Any]:
    manager = RuntimeManager(settings, options)
    return manager.status()


class RuntimeManager:
    def __init__(self, settings: Settings, options: RuntimeOptions) -> None:
        self.settings = settings
        self.options = options
        self.repo_path = settings.repo.path.resolve()
        self.state_dir = resolve_state_dir(self.repo_path, settings.repo.state_dir).resolve()
        self.runtime_dir = self.state_dir / "runtime"
        self.state_path = self.state_dir / "runtime.json"

    def start(self) -> dict[str, Any]:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        state = self._load_state()
        services: list[dict[str, Any]] = []

        if self.options.start_patchrelay:
            services.append(self._start_patchrelay(state))
        else:
            services.append(skipped_service("patchrelay_server", "disabled by command option"))

        if self.options.start_openclaw:
            services.append(self._start_openclaw_gateway(state))
        else:
            services.append(skipped_service("openclaw_gateway", "disabled by command option"))

        workers = self._worker_statuses() if self.options.check_workers else []
        self._save_state(state)
        return runtime_payload("start", self.state_path, services, workers)

    def stop(self) -> dict[str, Any]:
        state = self._load_state()
        services = [
            self._stop_service("patchrelay_server", state),
            self._stop_service("openclaw_gateway", state),
        ]
        self._save_state(state)
        return runtime_payload("stop", self.state_path, services, [])

    def status(self) -> dict[str, Any]:
        state = self._load_state()
        services = [
            self._patchrelay_status(state),
            self._openclaw_gateway_status(state),
        ]
        workers = self._worker_statuses() if self.options.check_workers else []
        return runtime_payload("status", self.state_path, services, workers)

    def _start_patchrelay(self, state: dict[str, Any]) -> dict[str, Any]:
        current = self._patchrelay_status(state)
        if current["reachable"]:
            current["status"] = "already_running"
            current["ok"] = True
            current["message"] = "PatchRelay server is already reachable."
            return current

        log_path = self.runtime_dir / "patchrelay-server.log"
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "patchrelay.app:create_app",
            "--factory",
            "--host",
            self.settings.server.host,
            "--port",
            str(self.settings.server.port),
        ]
        env = os.environ.copy()
        env["PATCHRELAY_CONFIG"] = self.options.config_path
        process = launch_background_process(command, cwd=Path.cwd(), env=env, log_path=log_path)
        state["patchrelay_server"] = process_state(
            name="patchrelay_server",
            pid=process.pid,
            command=command,
            cwd=Path.cwd(),
            log_path=log_path,
            url=self.patchrelay_url,
        )

        reachable = wait_until(lambda: self._patchrelay_reachable(), self.options.timeout_seconds)
        status = self._patchrelay_status(state)
        status["status"] = "started" if reachable else "failed"
        status["ok"] = reachable
        status["message"] = (
            "PatchRelay server started." if reachable else f"PatchRelay server did not become ready; see {log_path}."
        )
        return status

    def _start_openclaw_gateway(self, state: dict[str, Any]) -> dict[str, Any]:
        current = self._openclaw_gateway_status(state)
        if current["reachable"]:
            current["status"] = "already_running"
            current["ok"] = True
            current["message"] = "OpenClaw Gateway is already reachable."
            return current

        openclaw = shutil.which("openclaw")
        if openclaw is None:
            return {
                "name": "openclaw_gateway",
                "ok": False,
                "status": "unavailable",
                "pid": None,
                "reachable": False,
                "url": self.options.gateway_url,
                "command": [],
                "logPath": "",
                "message": "openclaw command was not found on PATH.",
            }

        gateway = parse_gateway_url(self.options.gateway_url)
        log_path = self.runtime_dir / "openclaw-gateway.log"
        command = [
            openclaw,
            "gateway",
            "run",
            "--port",
            str(gateway["port"]),
            "--auth",
            "token",
            "--token",
            self.options.gateway_token,
            "--bind",
            self.options.gateway_bind,
            "--force",
        ]
        env = with_windows_system_path(os.environ.copy())
        env.setdefault("OPENCLAW_SKIP_STARTUP_MODEL_PREWARM", "1")
        process = launch_background_process(command, cwd=Path.cwd(), env=env, log_path=log_path)
        state["openclaw_gateway"] = process_state(
            name="openclaw_gateway",
            pid=process.pid,
            command=command,
            cwd=Path.cwd(),
            log_path=log_path,
            url=self.options.gateway_url,
        )

        reachable = wait_until(lambda: tcp_reachable(gateway["host"], gateway["port"]), self.options.timeout_seconds)
        status = self._openclaw_gateway_status(state)
        status["status"] = "started" if reachable else "failed"
        status["ok"] = reachable
        status["message"] = (
            "OpenClaw Gateway started." if reachable else f"OpenClaw Gateway did not become ready; see {log_path}."
        )
        return status

    def _stop_service(self, name: str, state: dict[str, Any]) -> dict[str, Any]:
        service = state.get(name)
        if not isinstance(service, dict):
            return {
                "name": name,
                "ok": True,
                "status": "not_started",
                "pid": None,
                "reachable": False,
                "message": "No managed process recorded.",
            }

        pid = service.get("pid")
        if not isinstance(pid, int) or not psutil.pid_exists(pid):
            state.pop(name, None)
            return {
                "name": name,
                "ok": True,
                "status": "not_running",
                "pid": pid,
                "reachable": False,
                "message": "Managed process is not running.",
            }

        if not managed_process_matches(pid, name):
            return {
                "name": name,
                "ok": False,
                "status": "skipped",
                "pid": pid,
                "reachable": False,
                "message": "PID is alive but does not look like a PatchRelay-managed process.",
            }

        terminate_process_tree(pid)
        stopped = wait_until(lambda: not psutil.pid_exists(pid), 5)
        if stopped:
            state.pop(name, None)
        return {
            "name": name,
            "ok": stopped,
            "status": "stopped" if stopped else "failed",
            "pid": pid,
            "reachable": False,
            "message": "Process stopped." if stopped else "Process did not stop within timeout.",
        }

    def _patchrelay_status(self, state: dict[str, Any]) -> dict[str, Any]:
        service = state.get("patchrelay_server", {})
        pid = service.get("pid") if isinstance(service, dict) else None
        alive = isinstance(pid, int) and psutil.pid_exists(pid)
        reachable = self._patchrelay_reachable()
        return {
            "name": "patchrelay_server",
            "ok": bool(reachable),
            "status": "running" if reachable else ("process_alive" if alive else "stopped"),
            "pid": pid if isinstance(pid, int) else None,
            "reachable": reachable,
            "url": self.patchrelay_url,
            "command": service.get("command", []) if isinstance(service, dict) else [],
            "logPath": service.get("logPath", "") if isinstance(service, dict) else "",
            "message": "PatchRelay server is reachable." if reachable else "PatchRelay server is not reachable.",
        }

    def _openclaw_gateway_status(self, state: dict[str, Any]) -> dict[str, Any]:
        service = state.get("openclaw_gateway", {})
        pid = service.get("pid") if isinstance(service, dict) else None
        alive = isinstance(pid, int) and psutil.pid_exists(pid)
        gateway = parse_gateway_url(self.options.gateway_url)
        reachable = tcp_reachable(gateway["host"], gateway["port"])
        return {
            "name": "openclaw_gateway",
            "ok": bool(reachable),
            "status": "running" if reachable else ("process_alive" if alive else "stopped"),
            "pid": pid if isinstance(pid, int) else None,
            "reachable": reachable,
            "url": self.options.gateway_url,
            "command": service.get("command", []) if isinstance(service, dict) else [],
            "logPath": service.get("logPath", "") if isinstance(service, dict) else "",
            "message": "OpenClaw Gateway port is reachable." if reachable else "OpenClaw Gateway is not reachable.",
        }

    def _worker_statuses(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "fake",
                "ok": True,
                "status": "ready",
                "command": [],
                "path": "",
                "version": "",
                "message": "Fake worker is built in.",
            },
            worker_readiness("codex", command_to_argv(self.settings.worker.codex_command)),
            worker_readiness("claude", command_to_argv(self.settings.worker.claude_command)),
        ]

    def _patchrelay_reachable(self) -> bool:
        try:
            response = httpx.get(
                f"{self.patchrelay_url}/health",
                headers={"Authorization": f"Bearer {self.settings.server.token}"},
                timeout=1,
            )
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    @property
    def patchrelay_url(self) -> str:
        return f"http://{self.settings.server.host}:{self.settings.server.port}"


def with_windows_system_path(env: dict[str, str]) -> dict[str, str]:
    if os.name != "nt":
        return env

    updated = env.copy()
    path_key = "Path" if "Path" in updated else next((key for key in updated if key.lower() == "path"), "Path")
    current_entries = [
        entry for entry in updated.get(path_key, "").split(";") if entry
    ]
    existing = {entry.lower() for entry in current_entries}
    system_root = PureWindowsPath(updated.get("SystemRoot") or updated.get("WINDIR") or r"C:\Windows")
    required_entries = [
        str(system_root / "System32"),
        str(system_root / "System32" / "Wbem"),
        str(system_root / "System32" / "WindowsPowerShell" / "v1.0"),
    ]
    prefix = [entry for entry in required_entries if entry.lower() not in existing]

    for key in list(updated):
        if key.lower() == "path" and key != path_key:
            del updated[key]
    updated[path_key] = ";".join([*prefix, *current_entries])
    return updated


def launch_background_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
) -> subprocess.Popen[Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with log_path.open("a", encoding="utf-8") as log_file:
        return subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )


def process_state(
    *,
    name: str,
    pid: int,
    command: list[str],
    cwd: Path,
    log_path: Path,
    url: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "pid": pid,
        "command": command,
        "cwd": str(cwd),
        "logPath": str(log_path),
        "url": url,
        "startedAt": datetime.now(UTC).isoformat(),
    }


def runtime_payload(
    action: str,
    state_path: Path,
    services: list[dict[str, Any]],
    workers: list[dict[str, Any]],
) -> dict[str, Any]:
    ok = all(service.get("ok") for service in services) and all(worker.get("ok") for worker in workers)
    return {
        "ok": ok,
        "action": action,
        "statePath": str(state_path),
        "services": services,
        "workers": workers,
    }


def skipped_service(name: str, message: str) -> dict[str, Any]:
    return {
        "name": name,
        "ok": True,
        "status": "skipped",
        "pid": None,
        "reachable": False,
        "message": message,
    }


def worker_readiness(name: str, command: list[str]) -> dict[str, Any]:
    executable = command[0] if command else name
    resolved = shutil.which(executable)
    if resolved is None:
        return {
            "name": name,
            "ok": False,
            "status": "unavailable",
            "command": command,
            "path": "",
            "version": "",
            "message": f"{executable} was not found on PATH.",
        }

    version_command = [resolved, *command[1:], "--version"]
    try:
        result = subprocess.run(
            version_command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "name": name,
            "ok": False,
            "status": "unavailable",
            "command": command,
            "path": resolved,
            "version": "",
            "message": str(exc),
        }

    version = (result.stdout or result.stderr).strip().splitlines()
    return {
        "name": name,
        "ok": result.returncode == 0,
        "status": "ready" if result.returncode == 0 else "unavailable",
        "command": command,
        "path": resolved,
        "version": version[0] if version else "",
        "message": "Worker CLI is ready and will be launched per task."
        if result.returncode == 0
        else f"Version check failed with exit code {result.returncode}.",
    }


def managed_process_matches(pid: int, name: str) -> bool:
    try:
        command = " ".join(psutil.Process(pid).cmdline()).lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    if name == "patchrelay_server":
        return "patchrelay.app:create_app" in command or "patchrelay serve" in command
    if name == "openclaw_gateway":
        return "openclaw" in command and "gateway" in command
    return False


def parse_gateway_url(gateway_url: str) -> dict[str, Any]:
    parsed = urlparse(gateway_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 19001
    return {"host": host, "port": port}


def tcp_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def wait_until(predicate: Any, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return predicate()
