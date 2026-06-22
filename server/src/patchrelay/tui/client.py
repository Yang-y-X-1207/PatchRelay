from __future__ import annotations

import json
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

    @staticmethod
    def _artifact_content(task: dict[str, Any], name: str) -> dict[str, Any] | str | None:
        artifacts = task.get("artifacts")
        if not isinstance(artifacts, dict):
            return None
        artifact = artifacts.get(name)
        if not isinstance(artifact, dict):
            return None
        content = artifact.get("content")
        if isinstance(content, (dict, str)):
            return content
        return None

    @staticmethod
    def _artifact_dict(task: dict[str, Any], name: str) -> dict[str, Any]:
        content = PatchRelayClient._artifact_content(task, name)
        return content if isinstance(content, dict) else {}

    @staticmethod
    def _coerce_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def list_tasks(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/tasks")
        tasks = payload.get("tasks", [])
        return tasks if isinstance(tasks, list) else []

    def get_task(self, task_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/tasks/{task_id}")
        if isinstance(payload, dict):
            payload["display"] = self.build_task_display(payload)
        return payload

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

    def build_task_display(self, task: dict[str, Any]) -> dict[str, Any]:
        summary = self._artifact_content(task, "patchrelay.summary")
        tests = self._artifact_content(task, "patchrelay.tests")
        worker = self._artifact_content(task, "patchrelay.worker")
        diff_text = self._artifact_content(task, "patchrelay.diff")
        log_text = self._artifact_content(task, "patchrelay.log")
        events = task.get("events") if isinstance(task.get("events"), list) else []
        latest_event = task.get("latestEvent") if isinstance(task.get("latestEvent"), dict) else None
        return {
            "header": self._build_header(task, summary),
            "details": self._build_details(task, summary, tests),
            "summary": summary or {},
            "tests": tests or {},
            "worker": worker or {},
            "diff": self._coerce_text(diff_text),
            "log": self._coerce_text(log_text),
            "events": events,
            "latestEvent": latest_event,
        }

    def _build_header(self, task: dict[str, Any], summary: dict[str, Any] | str | None) -> dict[str, Any]:
        summary_payload = summary if isinstance(summary, dict) else {}
        tests_payload = self._artifact_dict(task, "patchrelay.tests")
        worker_payload = self._artifact_dict(task, "patchrelay.worker")
        return {
            "taskId": task.get("taskId") or "-",
            "status": task.get("status") or "unknown",
            "phase": task.get("phase") or "-",
            "worker": task.get("worker") or "-",
            "testStatus": summary_payload.get("testStatus") or tests_payload.get("status") or "-",
            "changedFiles": summary_payload.get("changedFiles") or [],
            "eventCount": task.get("eventCount") or len(task.get("events") or []),
            "branch": task.get("branch") or "-",
            "baseBranch": task.get("baseBranch") or "-",
            "error": task.get("error"),
            "workerExitCode": worker_payload.get("exitCode"),
        }

    def _build_details(
        self,
        task: dict[str, Any],
        summary: dict[str, Any] | str | None,
        tests: dict[str, Any] | str | None,
    ) -> dict[str, Any]:
        summary_payload = summary if isinstance(summary, dict) else {}
        tests_payload = tests if isinstance(tests, dict) else {}
        worker_payload = self._artifact_dict(task, "patchrelay.worker")
        return {
            "instruction": task.get("instruction") or "",
            "taskId": task.get("taskId") or "",
            "createdAt": task.get("createdAt") or "",
            "updatedAt": task.get("updatedAt") or "",
            "startedAt": task.get("startedAt") or "",
            "completedAt": task.get("completedAt") or "",
            "worktreePath": task.get("worktreePath") or "",
            "changedFiles": summary_payload.get("changedFiles") or [],
            "testStatus": summary_payload.get("testStatus") or tests_payload.get("status") or "-",
            "testExitCode": tests_payload.get("exitCode"),
            "workerExitCode": worker_payload.get("exitCode"),
        }
