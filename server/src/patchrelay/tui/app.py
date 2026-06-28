from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from patchrelay.config import ConfigError, load_settings
from patchrelay.tui.client import PatchRelayClient


@dataclass(frozen=True)
class TUIConfig:
    config: str
    url: str
    token: str
    gateway_url: str
    gateway_token: str
    gateway_bind: str
    timeout: float = 10.0
    refresh_interval: float = 2.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="patchrelay ui", description="Open the PatchRelay TUI dashboard.")
    parser.add_argument("--config", default="patchrelay.yaml")
    parser.add_argument("--url", default="http://127.0.0.1:8787")
    parser.add_argument("--token", default="change-me")
    parser.add_argument("--gateway-url", default=os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:19001"))
    parser.add_argument("--gateway-token", default=os.getenv("OPENCLAW_GATEWAY_TOKEN", "openclaw-local-token"))
    parser.add_argument("--gateway-bind", default="loopback")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--refresh-interval", type=float, default=2.0)
    return parser


def parse_args(argv: list[str] | None = None) -> TUIConfig:
    args = build_parser().parse_args(argv)
    return TUIConfig(
        config=args.config,
        url=args.url,
        token=args.token,
        gateway_url=args.gateway_url,
        gateway_token=args.gateway_token,
        gateway_bind=args.gateway_bind,
        timeout=args.timeout,
        refresh_interval=args.refresh_interval,
    )


def create_tui_app(
    client: PatchRelayClient,
    *,
    refresh_interval: float,
    setup_config: "SetupWizardConfig | None",
):
    try:
        from textual.app import App, ComposeResult
        from textual.binding import Binding
        from textual.widgets import Footer, Header
    except ImportError as exc:  # pragma: no cover - exercised in manual use
        raise SystemExit("PatchRelay TUI requires the optional `textual` dependency. Install with `uv sync --extra tui`.") from exc

    from patchrelay.tui.screens.setup_wizard import SetupWizardConfig
    from patchrelay.tui.screens.dashboard import DashboardView

    class PatchRelayTUIApp(App[None]):
        TITLE = "PatchRelay"
        CSS_PATH = Path(__file__).with_name("styles.css")
        BINDINGS = [
            Binding("r", "refresh", "Refresh", show=True),
            Binding("f", "focus_search", "Search", show=True),
            Binding("s", "submit_task", "Submit", show=True),
            Binding("u", "open_setup", "Setup", show=True),
            Binding("z", "setup_wizard", "Wizard", show=True),
            Binding("x", "cancel_task", "Cancel", show=True),
            Binding("c", "copy_task_id", "Copy ID", show=True),
            Binding("y", "copy_diff", "Copy Diff", show=True),
            Binding("w", "copy_worktree_path", "Copy Worktree", show=True),
            Binding("d", "open_diff", "Diff", show=True),
            Binding("o", "open_worktree", "Open Worktree", show=True),
            Binding("v", "cycle_view", "View", show=True),
            Binding("p", "toggle_refresh", "Pause", show=True),
            Binding("escape", "dismiss_modal", "Dismiss", show=True),
            Binding("q", "quit", "Quit", show=True),
        ]

        def __init__(self, client: PatchRelayClient, refresh_interval: float) -> None:
            super().__init__()
            self.client = client
            self.refresh_interval = refresh_interval
            self.setup_config = setup_config

        def compose(self) -> ComposeResult:
            yield Header()
            yield DashboardView(self.client, refresh_interval=self.refresh_interval, setup_config=self.setup_config)
            yield Footer()

        def action_dismiss_modal(self) -> None:
            if len(self.screen_stack) > 1:
                self.pop_screen()

    return PatchRelayTUIApp(client, refresh_interval)


def run(argv: list[str] | None = None) -> None:
    config = parse_args(argv)
    from patchrelay.onboarding import preview_setup
    from patchrelay.tui.screens.setup_wizard import SetupWizardConfig

    preview = preview_setup(config.config)
    try:
        settings = load_settings(config.config)
        worker = settings.worker.default
    except ConfigError:
        worker = preview.worker
    setup_config = SetupWizardConfig(
        config_path=config.config,
        url=config.url,
        token=config.token,
        gateway_url=config.gateway_url,
        gateway_token=config.gateway_token,
        gateway_bind=config.gateway_bind,
        worker=worker,
        timeout=config.timeout,
        interval=config.refresh_interval,
    )
    client = PatchRelayClient(config.url, config.token, timeout=config.timeout)
    create_tui_app(client, refresh_interval=config.refresh_interval, setup_config=setup_config).run()


def main(argv: list[str] | None = None) -> None:
    run(argv)
