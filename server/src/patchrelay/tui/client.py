from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class PatchRelayClient:
    base_url: str
    token: str
    timeout: float = 10.0

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {"Authorization": f"Bearer {self.token}"}
        response = httpx.request(method, url, headers=headers, json=payload, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("PatchRelay response was not a JSON object.")
        return data

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def list_tasks(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/tasks")
        tasks = payload.get("tasks", [])
        return tasks if isinstance(tasks, list) else []

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._request("GET", f"/tasks/{task_id}")

    def get_events(self, task_id: str, after: int | None = None) -> list[dict[str, Any]]:
        suffix = f"?after={after}" if after is not None else ""
        payload = self._request("GET", f"/tasks/{task_id}/events{suffix}")
        events = payload.get("events", [])
        return events if isinstance(events, list) else []

    def submit_task(self, instruction: str, *, worker: str = "auto", test_profile: str = "default") -> dict[str, Any]:
        payload = {
            "message": {
                "role": "ROLE_USER",
                "parts": [{"text": instruction}],
            },
            "metadata": {
                "patchrelay": {
                    "worker": worker,
                    "testProfile": test_profile,
                }
            },
        }
        return self._request("POST", "/message:send", payload)

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        return self._request("POST", f"/tasks/{task_id}:cancel")

