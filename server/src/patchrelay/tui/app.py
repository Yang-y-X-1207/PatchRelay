from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from patchrelay.tui.client import PatchRelayClient


@dataclass(frozen=True)
class TUIConfig:
    url: str
    token: str
    timeout: float = 10.0
    refresh_interval: float = 2.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="patchrelay ui", description="Open the PatchRelay TUI dashboard.")
    parser.add_argument("--url", default="http://127.0.0.1:8787")
    parser.add_argument("--token", default="change-me")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--refresh-interval", type=float, default=2.0)
    return parser


def parse_args(argv: list[str] | None = None) -> TUIConfig:
    args = build_parser().parse_args(argv)
    return TUIConfig(
        url=args.url,
        token=args.token,
        timeout=args.timeout,
        refresh_interval=args.refresh_interval,
    )


def run(argv: list[str] | None = None) -> None:
    config = parse_args(argv)
    try:
        from textual.app import App, ComposeResult
        from textual.widgets import Footer, Header
    except ImportError as exc:  # pragma: no cover - exercised in manual use
        raise SystemExit("PatchRelay TUI requires the optional `textual` dependency. Install with `uv sync --extra tui`.") from exc

    from patchrelay.tui.screens.dashboard import DashboardView

    class PatchRelayTUIApp(App[None]):
        TITLE = "PatchRelay"
        CSS_PATH = Path(__file__).with_name("styles.css")

        def __init__(self, client: PatchRelayClient, refresh_interval: float) -> None:
            super().__init__()
            self.client = client
            self.refresh_interval = refresh_interval

        def compose(self) -> ComposeResult:
            yield Header()
            yield DashboardView(self.client, refresh_interval=self.refresh_interval)
            yield Footer()

    client = PatchRelayClient(config.url, config.token, timeout=config.timeout)
    PatchRelayTUIApp(client, config.refresh_interval).run()


def main(argv: list[str] | None = None) -> None:
    run(argv)

