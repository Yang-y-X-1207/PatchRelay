from __future__ import annotations

from textual.widgets import Static


_STATE_CLASSES = (
    "state-ok",
    "state-warn",
    "state-error",
    "state-idle",
    "state-running",
)


class StatusBadge(Static):
    def set_state(self, state: str, *, detail: str | None = None) -> None:
        normalized = (state or "unknown").strip().lower().replace(" ", "-")
        for class_name in _STATE_CLASSES:
            self.remove_class(class_name)
        self.add_class(f"state-{normalized}")
        label = detail if detail is not None else normalized
        self.update(label.upper() if label else normalized.upper())

