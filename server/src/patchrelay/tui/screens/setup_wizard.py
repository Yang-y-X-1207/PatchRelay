from __future__ import annotations

from typing import Any

from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select, TextArea

from patchrelay.tui.client import PatchRelayClient


SETUP_ACTIONS = [
    ("Status", "status"),
    ("Refresh", "refresh"),
    ("Submit smoke", "smoke"),
]


class SetupWizardScreen(ModalScreen[dict[str, Any] | None]):
    def __init__(self, client: PatchRelayClient) -> None:
        super().__init__()
        self.client = client

    def compose(self):
        with Vertical(id="setup-modal"):
            yield Label("Setup wizard", classes="panel-title")
            yield Select(SETUP_ACTIONS, prompt="Action", value="status", id="setup-action")
            yield TextArea("", id="setup-output", read_only=True, show_line_numbers=False, soft_wrap=True)
            yield Label("", id="setup-status")
            with Vertical(id="setup-actions"):
                yield Button("Run", id="setup-run", variant="success")
                yield Button("Close", id="setup-close", variant="default")

    def on_mount(self) -> None:
        self.query_one("#setup-output", TextArea).load_text("Use the setup wizard to inspect the current runtime state.")

    def on_button_pressed(self, event) -> None:  # noqa: ANN001
        if event.button.id == "setup-close":
            self.dismiss(None)
            return
        if event.button.id != "setup-run":
            return
        action = str(self.query_one("#setup-action", Select).value or "status")
        try:
            if action == "status":
                payload = self.client.health()
            elif action == "refresh":
                payload = {"message": "Refresh handled by the dashboard."}
            else:
                payload = {"message": "Use the submit modal from the Dashboard to create a smoke task."}
        except Exception as exc:  # noqa: BLE001
            self.query_one("#setup-status", Label).update(f"error: {exc}")
            return
        self.query_one("#setup-output", TextArea).load_text(self._format_payload(payload))
        self.query_one("#setup-status", Label).update("ok")

    def _format_payload(self, payload: dict[str, Any]) -> str:
        lines = []
        for key in sorted(payload):
            lines.append(f"{key}: {payload[key]}")
        return "\n".join(lines) or "-"
