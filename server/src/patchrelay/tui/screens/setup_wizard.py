from __future__ import annotations

import argparse
import io
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import Any

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, TextArea

from patchrelay import cli
from patchrelay.onboarding import preview_setup, repair_config, smoke_plan
from patchrelay.tui.client import PatchRelayClient


SETUP_ACTIONS = [
    ("Status", "status"),
    ("Verify", "verify"),
    ("Repair", "repair"),
    ("Run setup", "setup"),
    ("Start runtime", "runtime_start"),
    ("Stop runtime", "runtime_stop"),
    ("Smoke", "smoke"),
]


@dataclass(frozen=True)
class SetupWizardConfig:
    config_path: str
    url: str
    token: str
    gateway_url: str
    gateway_token: str
    gateway_bind: str
    worker: str
    timeout: float
    interval: float


class SetupWizardScreen(ModalScreen[dict[str, Any] | None]):
    def __init__(self, client: PatchRelayClient, config: SetupWizardConfig) -> None:
        super().__init__()
        self.client = client
        self.config = config

    def compose(self):
        with Vertical(id="setup-modal"):
            yield Label("Setup wizard", classes="panel-title")
            yield Select(SETUP_ACTIONS, prompt="Action", value="status", id="setup-action")
            yield Input(value=self.config.config_path, id="setup-config")
            yield TextArea("", id="setup-output", read_only=True, show_line_numbers=False, soft_wrap=True)
            yield Label("", id="setup-status")
            with Horizontal(id="setup-actions"):
                yield Button("Run", id="setup-run", variant="success")
                yield Button("Close", id="setup-close", variant="default")

    def on_mount(self) -> None:
        preview = preview_setup(self.config.config_path, worker=self.config.worker)
        self.query_one("#setup-output", TextArea).load_text(
            self._format_payload(
                {
                    "message": "Inspect setup, repair config, run runtime, or launch a smoke task.",
                    "configPath": str(preview.config_path),
                    "repoPath": str(preview.repo_path),
                    "baseBranch": preview.base_branch,
                    "worker": preview.worker,
                    "testCommand": " ".join(preview.test_command),
                }
            )
        )

    def on_button_pressed(self, event) -> None:  # noqa: ANN001
        if event.button.id == "setup-close":
            self.dismiss(None)
            return
        if event.button.id != "setup-run":
            return
        action = str(self.query_one("#setup-action", Select).value or "status")
        config_path = self.query_one("#setup-config", Input).value.strip() or self.config.config_path
        try:
            payload = self._run_action(action, config_path)
        except Exception as exc:  # noqa: BLE001
            self.query_one("#setup-status", Label).update(f"error: {exc}")
            return
        self.query_one("#setup-output", TextArea).load_text(self._format_payload(payload))
        self.query_one("#setup-status", Label).update("ok")

    def _run_action(self, action: str, config_path: str) -> dict[str, Any]:
        if action == "status":
            args = self._build_setup_args(config_path)
            return cli.run_setup_status(args)
        if action == "verify":
            args = self._build_setup_args(config_path)
            return cli.run_setup_verify(args)
        if action == "repair":
            return repair_config(config_path, apply=True).to_dict()
        if action == "setup":
            args = self._build_setup_args(config_path, force=False)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                cli.run_setup(args, input_func=lambda _prompt="": "y")
            return {
                "ok": True,
                "action": "setup",
                "configPath": config_path,
                "output": buffer.getvalue().strip(),
            }
        if action == "runtime_start":
            return self._run_runtime("start", config_path)
        if action == "runtime_stop":
            return self._run_runtime("stop", config_path)
        if action == "smoke":
            return self._run_smoke()
        raise ValueError(f"Unsupported action: {action}")

    def _build_setup_args(self, config_path: str, *, force: bool = True) -> argparse.Namespace:
        return argparse.Namespace(
            config=config_path,
            worker=self.config.worker,
            gateway_url=self.config.gateway_url,
            gateway_token=self.config.gateway_token,
            gateway_bind=self.config.gateway_bind,
            timeout=self.config.timeout,
            interval=self.config.interval,
            no_patchrelay=False,
            no_openclaw=False,
            no_workers=False,
            apply=True,
            yes=True,
            force=force,
            json=False,
        )

    def _run_runtime(self, action: str, config_path: str) -> dict[str, Any]:
        args = self._build_setup_args(config_path)
        return cli.run_runtime_action(args, action)

    def _run_smoke(self) -> dict[str, Any]:
        plan = smoke_plan(self.config.worker)
        if plan.worker == "fake":
            args = argparse.Namespace(
                url=self.config.url,
                token=self.config.token,
                instruction=[plan.instruction],
                worker=plan.worker,
                test_profile="default",
                timeout=self.config.timeout,
                interval=self.config.interval,
            )
            submitted = cli.submit_task(args)
            return cli.wait_for_task(args, submitted["taskId"])

        args = argparse.Namespace(
            gateway_url=self.config.gateway_url,
            gateway_token=self.config.gateway_token,
            instruction=plan.instruction,
            worker=plan.worker,
            test_profile="default",
            timeout=self.config.timeout,
            interval=self.config.interval,
        )
        submitted = cli.openclaw_submit_task(args)
        return cli.wait_for_openclaw_task(args, cli.extract_task_id(submitted))

    def _format_payload(self, payload: dict[str, Any]) -> str:
        lines = []
        for key in sorted(payload):
            lines.append(f"{key}: {payload[key]}")
        return "\n".join(lines) or "-"
