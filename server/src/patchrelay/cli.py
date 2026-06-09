import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any

import httpx
import uvicorn

from patchrelay.config import ConfigError, Settings, command_to_display, load_settings
from patchrelay.git_workspace import GitWorkspaceError, GitWorkspaceManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="patchrelay")
    subcommands = parser.add_subparsers(dest="command")

    serve = subcommands.add_parser("serve", help="Run the PatchRelay server.")
    serve.add_argument("--config", default="patchrelay.yaml")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)

    tasks = subcommands.add_parser("tasks", help="List tasks from a running PatchRelay server.")
    add_client_args(tasks)
    tasks.add_argument("--json", action="store_true", help="Print raw JSON.")

    cancel = subcommands.add_parser("cancel", help="Cancel a queued or running task.")
    add_client_args(cancel)
    cancel.add_argument("task_id")
    cancel.add_argument("--json", action="store_true", help="Print raw JSON.")

    doctor = subcommands.add_parser("doctor", help="Check local PatchRelay configuration and tools.")
    doctor.add_argument("--config", default="patchrelay.yaml")
    doctor.add_argument("--json", action="store_true", help="Print raw JSON.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "serve":
        try:
            settings = load_settings(args.config)
        except ConfigError as exc:
            parser.error(str(exc))
        host = args.host or settings.server.host
        port = args.port or settings.server.port
        os.environ["PATCHRELAY_CONFIG"] = args.config
        uvicorn.run("patchrelay.app:create_app", host=host, port=port, factory=True)
        return

    if args.command == "tasks":
        payload = request_json(args, "GET", "/tasks")
        if args.json:
            print_json(payload)
        else:
            for task in payload.get("tasks", []):
                print(
                    f"{task['taskId']}  {task['status']:<10}  {task['worker']:<6}  "
                    f"{task.get('phase') or '-'}"
                )
        return

    if args.command == "cancel":
        payload = request_json(args, "POST", f"/tasks/{args.task_id}:cancel")
        if args.json:
            print_json(payload)
        else:
            print(f"{payload['taskId']} canceled: {payload['status']}")
        return

    if args.command == "doctor":
        try:
            settings = load_settings(args.config)
        except ConfigError as exc:
            result = {"ok": False, "checks": [{"name": "config", "ok": False, "message": str(exc)}]}
            print_json(result) if args.json else print_doctor(result)
            raise SystemExit(1)
        result = run_doctor(settings)
        print_json(result) if args.json else print_doctor(result)
        raise SystemExit(0 if result["ok"] else 1)

    parser.print_help()


def add_client_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", default=os.getenv("PATCHRELAY_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--token", default=os.getenv("PATCHRELAY_TOKEN", "change-me"))


def request_json(args: argparse.Namespace, method: str, path: str) -> dict[str, Any]:
    url = f"{args.url.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {args.token}"}
    try:
        response = httpx.request(method, url, headers=headers, timeout=10)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SystemExit(f"PatchRelay request failed: {exc}") from exc
    return response.json()


def run_doctor(settings: Settings) -> dict[str, Any]:
    checks = [
        check_repo(settings),
        check_command("git", ["git", "--version"]),
        check_worker_command("codex", settings.worker.codex_command),
        check_worker_command("claude", settings.worker.claude_command),
        check_tests(settings),
    ]
    return {"ok": all(check["ok"] for check in checks), "checks": checks}


def check_repo(settings: Settings) -> dict[str, Any]:
    manager = GitWorkspaceManager(settings.repo.path, settings.repo.state_dir, settings.repo.base_branch)
    try:
        manager.validate()
    except GitWorkspaceError as exc:
        return {"name": "repo", "ok": False, "message": str(exc)}
    return {
        "name": "repo",
        "ok": True,
        "message": f"{settings.repo.path} on base branch {settings.repo.base_branch}",
    }


def check_command(name: str, command: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"name": name, "ok": False, "message": str(exc)}
    output = (result.stdout or result.stderr).strip()
    return {"name": name, "ok": result.returncode == 0, "message": output}


def check_worker_command(name: str, command: str | list[str]) -> dict[str, Any]:
    executable = command[0] if isinstance(command, list) else command
    found = shutil.which(executable)
    return {
        "name": f"worker:{name}",
        "ok": found is not None,
        "message": found or f"{command_to_display(command)} not found on PATH",
    }


def check_tests(settings: Settings) -> dict[str, Any]:
    profile_names = sorted(settings.tests.keys())
    return {
        "name": "tests",
        "ok": "default" in settings.tests,
        "message": f"configured profiles: {', '.join(profile_names)}",
    }


def print_doctor(result: dict[str, Any]) -> None:
    for check in result["checks"]:
        status = "ok" if check["ok"] else "fail"
        print(f"[{status}] {check['name']}: {check['message']}")
    print(f"overall: {'ok' if result['ok'] else 'fail'}")


def print_json(payload: Any) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    print()
