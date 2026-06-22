from __future__ import annotations

from typing import Any

from textual.widgets import RichLog


class LiveLog(RichLog):
    def show_events(self, events: list[dict[str, Any]], *, compact: bool = False) -> None:
        self.clear()
        if not events:
            self.write("No events yet.")
            return
        for event in events:
            sequence = event.get("sequence") or "-"
            timestamp = event.get("timestamp") or "-"
            severity = event.get("severity") or "info"
            phase = event.get("phase") or "-"
            message = event.get("message") or ""
            if compact:
                self.write(f"[{severity}] {phase}: {message}")
            else:
                self.write(f"{sequence:>3}  {timestamp}  [{severity}] {phase}: {message}")
