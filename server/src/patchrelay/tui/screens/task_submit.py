from __future__ import annotations

from typing import Any

from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, TextArea

from patchrelay.tui.client import PatchRelayClient


WORKER_OPTIONS = [
    ("Auto", "auto"),
    ("Fake", "fake"),
    ("Codex", "codex"),
    ("Claude", "claude"),
]

TEST_PROFILE_OPTIONS = [
    ("Default", "default"),
]


class TaskSubmitScreen(ModalScreen[dict[str, Any] | None]):
    def __init__(self, client: PatchRelayClient) -> None:
        super().__init__()
        self.client = client

    def compose(self):
        with Vertical(id="submit-modal"):
            yield Label("Submit task", classes="panel-title")
            yield Input(placeholder="Describe the task", id="submit-instruction")
            yield Select(WORKER_OPTIONS, prompt="Worker", value="auto", id="submit-worker")
            yield Select(TEST_PROFILE_OPTIONS, prompt="Test profile", value="default", id="submit-test-profile")
            yield TextArea("", id="submit-preview", read_only=True, show_line_numbers=False, soft_wrap=True)
            yield Label("", id="submit-status")
            with Vertical(id="submit-actions"):
                yield Button("Submit", id="submit-confirm", variant="success")
                yield Button("Cancel", id="submit-cancel", variant="default")

    def on_mount(self) -> None:
        self.query_one("#submit-preview", TextArea).load_text("Type a task description to preview the request.")
        self.query_one("#submit-instruction", Input).focus()

    def on_input_changed(self, event) -> None:  # noqa: ANN001
        if event.input.id != "submit-instruction":
            return
        instruction = event.value.strip()
        preview = "\n".join(
            [
                "A2A-like request",
                f"instruction: {instruction or '-'}",
                f"worker: {self.query_one('#submit-worker', Select).value or 'auto'}",
                f"test profile: {self.query_one('#submit-test-profile', Select).value or 'default'}",
            ]
        )
        self.query_one("#submit-preview", TextArea).load_text(preview)

    def on_button_pressed(self, event) -> None:  # noqa: ANN001
        if event.button.id == "submit-cancel":
            self.dismiss(None)
            return
        if event.button.id != "submit-confirm":
            return
        instruction = self.query_one("#submit-instruction", Input).value.strip()
        if not instruction:
            self.query_one("#submit-status", Label).update("instruction is required")
            return
        worker = str(self.query_one("#submit-worker", Select).value or "auto")
        test_profile = str(self.query_one("#submit-test-profile", Select).value or "default")
        try:
            response = self.client.submit_task(instruction, worker=worker, test_profile=test_profile)
        except Exception as exc:  # noqa: BLE001
            self.query_one("#submit-status", Label).update(f"error: {exc}")
            return
        self.dismiss(response)
