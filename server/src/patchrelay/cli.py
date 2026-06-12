import argparse
import json
import os
import shlex
import sys
import time
from typing import Any

import httpx
import uvicorn

from patchrelay.cleanup import CleanupError, cleanup_patchrelay
from patchrelay.config import ConfigError, load_settings
from patchrelay.doctor import config_error_result, run_doctor
from patchrelay.onboarding import (
    OnboardingError,
    apply_openclaw_config,
    build_openclaw_apply_steps,
    generate_openclaw_commands,
    init_config,
    smoke_plan,
)


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

    submit = subcommands.add_parser("submit", help="Submit a coding task to a running PatchRelay server.")
    add_client_args(submit)
    submit.add_argument("instruction", nargs="+", help="Task instruction text.")
    submit.add_argument("--worker", choices=["auto", "fake", "codex", "claude"], default="auto")
    submit.add_argument("--test-profile", default="default")
    submit.add_argument("--wait", action="store_true", help="Wait for completion after submitting.")
    submit.add_argument("--timeout", type=float, default=300)
    submit.add_argument("--interval", type=float, default=1)
    submit.add_argument("--json", action="store_true", help="Print raw JSON.")

    wait = subcommands.add_parser("wait", help="Wait for a task to finish.")
    add_client_args(wait)
    wait.add_argument("task_id")
    wait.add_argument("--timeout", type=float, default=300)
    wait.add_argument("--interval", type=float, default=1)
    wait.add_argument("--json", action="store_true", help="Print raw JSON.")

    cancel = subcommands.add_parser("cancel", help="Cancel a queued or running task.")
    add_client_args(cancel)
    cancel.add_argument("task_id")
    cancel.add_argument("--json", action="store_true", help="Print raw JSON.")

    doctor = subcommands.add_parser("doctor", help="Check local PatchRelay configuration and tools.")
    doctor.add_argument("--config", default="patchrelay.yaml")
    doctor.add_argument("--json", action="store_true", help="Print raw JSON.")

    init = subcommands.add_parser("init", help="Generate a local PatchRelay configuration.")
    init.add_argument("--config", default="patchrelay.yaml")
    init.add_argument("--force", action="store_true", help="Overwrite an existing configuration file.")
    init.add_argument("--yes", action="store_true", help="Run non-interactively. Accepted for script-friendly usage.")
    init.add_argument("--repo-path", help="Target repository path.")
    init.add_argument("--base-branch", help="Base branch for PatchRelay task worktrees.")
    init.add_argument("--worker", choices=["auto", "fake", "codex", "claude"], help="Default worker.")
    init.add_argument("--test-command", help='Default test command, for example "python -m pytest".')
    init.add_argument("--token", help="Bearer token to write into the config. Defaults to a generated token.")

    setup = subcommands.add_parser("setup", help="Interactive yes/no guided local setup.")
    setup.add_argument("--config", default="patchrelay.yaml")
    setup.add_argument("--force", action="store_true", help="Allow replacing an existing configuration after confirmation.")
    setup.add_argument("--worker", choices=["fake", "codex", "claude"], default="fake")
    setup.add_argument("--gateway-url", default=os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:19001"))
    setup.add_argument("--gateway-token", default=os.getenv("OPENCLAW_GATEWAY_TOKEN", "openclaw-local-token"))
    setup.add_argument("--timeout", type=float, default=300)
    setup.add_argument("--interval", type=float, default=1)

    smoke = subcommands.add_parser("smoke", help="Submit a minimal task to a running PatchRelay server.")
    smoke.add_argument("--config", default="patchrelay.yaml")
    smoke.add_argument("--worker", choices=["fake", "codex", "claude"], default="fake")
    smoke.add_argument("--via", choices=["patchrelay", "openclaw"], default="patchrelay")
    smoke.add_argument("--url")
    smoke.add_argument("--token")
    smoke.add_argument("--gateway-url", default=os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:19001"))
    smoke.add_argument("--gateway-token", default=os.getenv("OPENCLAW_GATEWAY_TOKEN", "openclaw-local-token"))
    smoke.add_argument("--timeout", type=float, default=300)
    smoke.add_argument("--interval", type=float, default=1)
    smoke.add_argument("--json", action="store_true", help="Print raw JSON.")

    openclaw = subcommands.add_parser("openclaw", help="Print or apply OpenClaw setup for this PatchRelay config.")
    openclaw.add_argument("action", nargs="?", choices=["apply"])
    openclaw.add_argument("--config", default="patchrelay.yaml")
    openclaw.add_argument("--apply", action="store_true", help="Actually run OpenClaw setup commands.")

    cleanup = subcommands.add_parser("cleanup", help="Clean PatchRelay worktrees, branches, and local state.")
    cleanup.add_argument("--config", default="patchrelay.yaml")
    cleanup.add_argument("--force", action="store_true", help="Remove cleanup targets. Without this, only preview.")
    cleanup.add_argument("--json", action="store_true", help="Print raw JSON.")

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

    if args.command == "submit":
        payload = submit_task(args)
        if args.wait:
            payload = wait_for_task(args, payload["taskId"])
        print_json(payload) if args.json else print_task_summary(payload)
        return

    if args.command == "wait":
        payload = wait_for_task(args, args.task_id)
        print_json(payload) if args.json else print_task_summary(payload)
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
            result = config_error_result(str(exc))
            print_json(result) if args.json else print_doctor(result)
            raise SystemExit(1)
        result = run_doctor(settings)
        print_json(result) if args.json else print_doctor(result)
        raise SystemExit(0 if result["ok"] else 1)

    if args.command == "init":
        try:
            result = init_config(
                args.config,
                force=args.force,
                repo_path=args.repo_path,
                base_branch=args.base_branch,
                worker=args.worker,
                test_command=parse_test_command(args.test_command),
                token=args.token,
            )
        except OnboardingError as exc:
            raise SystemExit(str(exc)) from exc
        print_init_result(result)
        return

    if args.command == "setup":
        run_setup(args)
        return

    if args.command == "smoke":
        try:
            settings = load_settings(args.config)
        except ConfigError as exc:
            raise SystemExit(str(exc)) from exc
        url = args.url or f"http://{settings.server.host}:{settings.server.port}"
        token = args.token or settings.server.token
        plan = smoke_plan(args.worker)
        if args.via == "openclaw":
            gateway_args = argparse.Namespace(
                gateway_url=args.gateway_url,
                gateway_token=args.gateway_token,
                instruction=plan.instruction,
                worker=plan.worker,
                test_profile="default",
                timeout=args.timeout,
                interval=args.interval,
            )
            payload = openclaw_submit_task(gateway_args)
            task_id = extract_task_id(payload)
            payload = wait_for_openclaw_task(gateway_args, task_id)
            print_json(payload) if args.json else print_smoke_summary(payload)
            return
        client_args = argparse.Namespace(
            url=url,
            token=token,
            instruction=[plan.instruction],
            worker=plan.worker,
            test_profile="default",
            timeout=args.timeout,
            interval=args.interval,
        )
        payload = submit_task(client_args)
        payload = wait_for_task(client_args, payload["taskId"])
        print_json(payload) if args.json else print_smoke_summary(payload)
        return

    if args.command == "openclaw":
        try:
            settings = load_settings(args.config)
        except ConfigError as exc:
            raise SystemExit(str(exc)) from exc
        if args.action == "apply":
            steps = build_openclaw_apply_steps(settings)
            if not args.apply:
                print_openclaw_apply_plan(steps)
                return
            results = apply_openclaw_config(settings)
            print_openclaw_apply_results(results)
            raise SystemExit(0 if all(result.ok for result in results) else 1)
        print_openclaw_commands(generate_openclaw_commands(settings))
        return

    if args.command == "cleanup":
        try:
            settings = load_settings(args.config)
            result = cleanup_patchrelay(settings, force=args.force)
        except (ConfigError, CleanupError) as exc:
            payload = {"ok": False, "error": str(exc)}
            print_json(payload) if args.json else print(f"cleanup failed: {exc}")
            raise SystemExit(1)
        payload = result.to_dict()
        print_json(payload) if args.json else print_cleanup(payload)
        raise SystemExit(0 if payload["ok"] else 1)

    parser.print_help()


def add_client_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", default=os.getenv("PATCHRELAY_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--token", default=os.getenv("PATCHRELAY_TOKEN", "change-me"))


def parse_test_command(value: str | None) -> list[str] | None:
    if value is None:
        return None
    command = shlex.split(value)
    if not command:
        raise SystemExit("--test-command must not be empty")
    return command


def ask_yes_no(prompt: str, *, default: bool = True, input_func: Any = input) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        answer = input_func(f"{prompt} [{suffix}] ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please answer yes or no.")


def run_setup(args: argparse.Namespace, input_func: Any = input) -> None:
    print("PatchRelay setup")
    print("This flow only asks yes/no questions and uses detected defaults.")
    print()

    config_exists = os.path.exists(args.config)
    if config_exists and not args.force:
        if not ask_yes_no(f"{args.config} already exists. Overwrite it?", default=False, input_func=input_func):
            print("setup stopped: existing config kept")
            return
    elif config_exists and args.force:
        if not ask_yes_no(f"Overwrite existing {args.config}?", default=True, input_func=input_func):
            print("setup stopped: existing config kept")
            return

    if not ask_yes_no(f"Generate PatchRelay config at {args.config}?", default=True, input_func=input_func):
        print("setup stopped before config generation")
        return

    try:
        init_result = init_config(args.config, force=True)
    except OnboardingError as exc:
        raise SystemExit(str(exc)) from exc
    print_init_result(init_result)

    settings = init_result.settings
    if ask_yes_no("Run doctor checks now?", default=True, input_func=input_func):
        doctor_result = run_doctor(settings)
        print_doctor(doctor_result)
        if not doctor_result["ok"] and not ask_yes_no("Doctor failed. Continue anyway?", default=False, input_func=input_func):
            print("setup stopped after doctor failure")
            return

    if ask_yes_no("Apply OpenClaw plugin setup now?", default=False, input_func=input_func):
        results = apply_openclaw_config(settings)
        print_openclaw_apply_results(results)
        if not all(result.ok for result in results):
            print("setup stopped after OpenClaw setup failure")
            return
    else:
        print("OpenClaw setup skipped. Dry-run plan:")
        print_openclaw_apply_plan(build_openclaw_apply_steps(settings))

    if ask_yes_no("Run smoke test through OpenClaw Gateway now?", default=False, input_func=input_func):
        plan = smoke_plan(args.worker)
        gateway_args = argparse.Namespace(
            gateway_url=args.gateway_url,
            gateway_token=args.gateway_token,
            instruction=plan.instruction,
            worker=plan.worker,
            test_profile="default",
            timeout=args.timeout,
            interval=args.interval,
        )
        payload = openclaw_submit_task(gateway_args)
        task_id = extract_task_id(payload)
        payload = wait_for_openclaw_task(gateway_args, task_id)
        print_smoke_summary(payload)

    print("setup completed")


def request_json(
    args: argparse.Namespace,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{args.url.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {args.token}"}
    try:
        response = httpx.request(method, url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SystemExit(f"PatchRelay request failed: {exc}") from exc
    return response.json()


def request_openclaw_json(args: argparse.Namespace, tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
    url = f"{args.gateway_url.rstrip('/')}/tools/invoke"
    headers = {"Authorization": f"Bearer {args.gateway_token}"}
    payload = {"name": tool_name, "args": tool_args}
    try:
        response = httpx.request("POST", url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SystemExit(f"OpenClaw Gateway request failed: {exc}") from exc
    data = response.json()
    if not isinstance(data, dict):
        raise SystemExit("OpenClaw Gateway response was not a JSON object.")
    return unwrap_openclaw_payload(data)


def unwrap_openclaw_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("result", "content", "data"):
        nested = payload.get(key)
        if isinstance(nested, dict) and ("taskId" in nested or "status" in nested or "artifacts" in nested):
            return nested
    if isinstance(payload.get("value"), dict):
        return payload["value"]
    return payload


def submit_task(args: argparse.Namespace) -> dict[str, Any]:
    instruction = " ".join(args.instruction).strip()
    payload = {
        "message": {
            "role": "ROLE_USER",
            "parts": [{"text": instruction}],
        },
        "metadata": {
            "patchrelay": {
                "worker": args.worker,
                "testProfile": args.test_profile,
            }
        },
    }
    return request_json(args, "POST", "/message:send", payload)


def openclaw_submit_task(args: argparse.Namespace) -> dict[str, Any]:
    return request_openclaw_json(
        args,
        "patchrelay_submit_task",
        {
            "instruction": args.instruction,
            "worker": args.worker,
            "testProfile": args.test_profile,
        },
    )


def extract_task_id(payload: dict[str, Any]) -> str:
    task_id = payload.get("taskId")
    if isinstance(task_id, str) and task_id:
        return task_id
    raise SystemExit("OpenClaw Gateway response did not include taskId.")


def wait_for_task(args: argparse.Namespace, task_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        payload = request_json(args, "GET", f"/tasks/{task_id}")
        if payload["status"] in {"completed", "failed", "canceled"}:
            return payload
        time.sleep(args.interval)
    raise SystemExit(f"Timed out waiting for task {task_id}")


def wait_for_openclaw_task(args: argparse.Namespace, task_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        payload = request_openclaw_json(args, "patchrelay_get_task", {"taskId": task_id})
        if payload["status"] in {"completed", "failed", "canceled"}:
            return payload
        time.sleep(args.interval)
    raise SystemExit(f"Timed out waiting for OpenClaw task {task_id}")


def print_task_summary(payload: dict[str, Any]) -> None:
    print(f"task: {payload['taskId']}")
    print(f"status: {payload['status']}")
    if payload.get("phase"):
        print(f"phase: {payload['phase']}")
    if payload.get("branch"):
        print(f"branch: {payload['branch']}")
    summary = payload.get("artifacts", {}).get("patchrelay.summary", {}).get("content")
    if summary:
        print(f"worker: {summary.get('worker')}")
        changed_files = summary.get("changedFiles") or []
        print(f"changed files: {', '.join(changed_files) or '-'}")
        print(f"test status: {summary.get('testStatus')}")


def print_doctor(result: dict[str, Any]) -> None:
    for check in result["checks"]:
        status = "ok" if check["ok"] else "fail"
        print(f"[{status}] {check['name']}: {check['message']}")
        if check.get("hint"):
            print(f"hint: {check['hint']}")
    print(f"overall: {'ok' if result['ok'] else 'fail'}")


def print_init_result(result: Any) -> None:
    action = "overwrote" if result.overwritten else "created"
    print(f"{action}: {result.config_path}")
    print(f"repo: {result.settings.repo.path}")
    print(f"base branch: {result.settings.repo.base_branch}")
    print(f"default worker: {result.settings.worker.default}")
    print()
    print(f"patchrelay serve --config {result.config_path}")
    print(f"patchrelay doctor --config {result.config_path}")
    print(f"patchrelay smoke --config {result.config_path} --worker fake --token {result.settings.server.token}")


def print_smoke_summary(payload: dict[str, Any]) -> None:
    print(f"task: {payload['taskId']}")
    print(f"status: {payload['status']}")
    print(f"worker: {payload['worker']}")
    summary = payload.get("artifacts", {}).get("patchrelay.summary", {}).get("content", {})
    changed_files = summary.get("changedFiles") or []
    test_status = summary.get("testStatus") or "-"
    print(f"changed files: {', '.join(changed_files) or '-'}")
    print(f"test status: {test_status}")


def print_openclaw_commands(commands: list[str]) -> None:
    for index, command in enumerate(commands, start=1):
        print(f"# {index}")
        print(command)
        print()


def print_openclaw_apply_plan(steps: list[Any]) -> None:
    print("dry-run: OpenClaw setup plan")
    print("add --apply to execute these steps")
    for index, step in enumerate(steps, start=1):
        cwd = f" (cwd: {step.cwd})" if step.cwd else ""
        print(f"{index}. {step.name}{cwd}")
        print(f"   {step.display_command()}")


def print_openclaw_apply_results(results: list[Any]) -> None:
    for result in results:
        status = "ok" if result.ok else "fail"
        print(f"[{status}] {result.step.name}: {result.step.display_command()}")
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.stderr.strip():
            print(result.stderr.strip())


def print_cleanup(result: dict[str, Any]) -> None:
    mode = "removed" if result["force"] else "preview"
    print(f"cleanup mode: {mode}")
    print(f"repo: {result['repoPath']}")
    print(f"state dir: {result['stateDir']}")
    if not result["actions"]:
        print("no PatchRelay cleanup targets found")
        return
    for action in result["actions"]:
        suffix = f" - {action['message']}" if action.get("message") else ""
        print(f"[{action['status']}] {action['kind']}: {action['target']}{suffix}")
    print(f"overall: {'ok' if result['ok'] else 'fail'}")


def print_json(payload: Any) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    print()
