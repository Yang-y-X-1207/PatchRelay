from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from patchrelay.config import Settings


WorkerName = Literal["auto", "codex", "claude", "fake"]


class TaskStatus(StrEnum):
    SUBMITTED = "submitted"
    QUEUED = "queued"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class PatchRelayMetadata(BaseModel):
    worker: WorkerName = "auto"
    testProfile: str = "default"


class A2AMessagePart(BaseModel):
    text: str | None = None


class A2AMessage(BaseModel):
    role: str = "ROLE_USER"
    parts: list[A2AMessagePart]


class SendMessageRequest(BaseModel):
    message: A2AMessage
    metadata: dict[str, Any] = Field(default_factory=dict)


class Artifact(BaseModel):
    kind: str
    content: Any
    truncated: bool = False


class TaskRecord(BaseModel):
    id: str
    instruction: str
    worker: WorkerName
    test_profile: str
    status: TaskStatus
    phase: str = "accepted"
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    artifacts: dict[str, Artifact] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    error: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.id,
            "instruction": self.instruction,
            "worker": self.worker,
            "testProfile": self.test_profile,
            "status": self.status,
            "phase": self.phase,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
            "artifacts": {name: artifact.model_dump() for name, artifact in self.artifacts.items()},
            "logs": self.logs[-20:],
            "error": self.error,
        }


class TaskError(RuntimeError):
    pass


class TaskNotFound(TaskError):
    pass


class TaskCannotCancel(TaskError):
    pass


class TaskService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tasks: dict[str, TaskRecord] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._worker_loop: asyncio.Task[None] | None = None

    def ensure_started(self) -> None:
        if self._worker_loop is None or self._worker_loop.done():
            self._worker_loop = asyncio.create_task(self._run_queue())

    async def submit(self, request: SendMessageRequest) -> TaskRecord:
        instruction = extract_instruction(request)
        metadata = parse_patchrelay_metadata(request.metadata, self._settings)
        now = utcnow()
        record = TaskRecord(
            id=uuid.uuid4().hex,
            instruction=instruction,
            worker=metadata.worker,
            test_profile=metadata.testProfile,
            status=TaskStatus.SUBMITTED,
            created_at=now,
            updated_at=now,
        )

        async with self._lock:
            record.status = TaskStatus.QUEUED
            record.phase = "queued"
            record.updated_at = utcnow()
            self._tasks[record.id] = record
            await self._queue.put(record.id)

        return record

    async def list_tasks(self) -> list[TaskRecord]:
        async with self._lock:
            return sorted(self._tasks.values(), key=lambda task: task.created_at, reverse=True)

    async def get(self, task_id: str) -> TaskRecord:
        async with self._lock:
            try:
                return self._tasks[task_id]
            except KeyError as exc:
                raise TaskNotFound(task_id) from exc

    async def cancel(self, task_id: str) -> TaskRecord:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                raise TaskNotFound(task_id)
            if record.status == TaskStatus.QUEUED:
                mark_canceled(record, "Canceled before execution.")
                return record
            if record.status == TaskStatus.WORKING:
                mark_canceled(record, "Cancellation requested.")
                return record
            raise TaskCannotCancel(f"Task {task_id} is already {record.status}.")

    def queue_summary(self) -> dict[str, int]:
        running = sum(1 for task in self._tasks.values() if task.status == TaskStatus.WORKING)
        queued = sum(1 for task in self._tasks.values() if task.status == TaskStatus.QUEUED)
        return {"running": running, "queued": queued}

    async def _run_queue(self) -> None:
        while True:
            task_id = await self._queue.get()
            try:
                await self._run_one(task_id)
            finally:
                self._queue.task_done()

    async def _run_one(self, task_id: str) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None or record.status == TaskStatus.CANCELED:
                return
            record.status = TaskStatus.WORKING
            record.phase = "fake-worker"
            record.started_at = utcnow()
            record.updated_at = record.started_at
            record.logs.append("Fake worker started.")

        await asyncio.sleep(0.05)

        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None or record.status == TaskStatus.CANCELED:
                return
            if "fail" in record.instruction.lower():
                record.status = TaskStatus.FAILED
                record.phase = "failed"
                record.error = "Fake worker failure requested by instruction."
                record.completed_at = utcnow()
                record.updated_at = record.completed_at
                record.logs.append(record.error)
                return
            record.status = TaskStatus.COMPLETED
            record.phase = "completed"
            record.completed_at = utcnow()
            record.updated_at = record.completed_at
            record.logs.append("Fake worker completed.")
            record.artifacts["patchrelay.summary"] = Artifact(
                kind="application/json",
                content={
                    "taskId": record.id,
                    "worker": record.worker,
                    "status": record.status,
                    "changedFiles": ["fake-change.txt"],
                    "testStatus": "not-run",
                },
            )

    async def shutdown(self) -> None:
        if self._worker_loop is not None:
            self._worker_loop.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_loop


def utcnow() -> datetime:
    return datetime.now(UTC)


def extract_instruction(request: SendMessageRequest) -> str:
    parts = [part.text.strip() for part in request.message.parts if part.text and part.text.strip()]
    instruction = "\n".join(parts).strip()
    if not instruction:
        raise TaskError("message.parts must contain non-empty text")
    return instruction


def parse_patchrelay_metadata(metadata: dict[str, Any], settings: Settings) -> PatchRelayMetadata:
    raw = metadata.get("patchrelay", {})
    parsed = PatchRelayMetadata.model_validate(raw)
    if parsed.testProfile not in settings.tests:
        raise TaskError(f"Unknown testProfile: {parsed.testProfile}")
    return parsed


def mark_canceled(record: TaskRecord, message: str) -> None:
    record.status = TaskStatus.CANCELED
    record.phase = "canceled"
    record.error = message
    record.completed_at = utcnow()
    record.updated_at = record.completed_at
    record.logs.append(message)
