from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from patchrelay.artifacts import build_summary_content, clean_diff, clean_log
from patchrelay.config import Settings
from patchrelay.git_workspace import GitWorkspaceManager, Workspace
from patchrelay.task_store import SQLiteTaskStore
from patchrelay.test_runner import TestRunner, TestRunResult
from patchrelay.workers import WorkerName, WorkerRegistry, WorkerResult


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


class TaskEvent(BaseModel):
    sequence: int
    timestamp: datetime
    phase: str
    message: str
    severity: str = "info"
    status: TaskStatus | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp.isoformat(),
            "phase": self.phase,
            "message": self.message,
            "severity": self.severity,
            "status": self.status.value if self.status else None,
        }


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
    branch: str | None = None
    base_branch: str | None = None
    worktree_path: Path | None = None
    artifacts: dict[str, Artifact] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    events: list[TaskEvent] = Field(default_factory=list)
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
            "branch": self.branch,
            "baseBranch": self.base_branch,
            "worktreePath": str(self.worktree_path) if self.worktree_path else None,
            "artifacts": {name: artifact.model_dump() for name, artifact in self.artifacts.items()},
            "logs": self.logs[-20:],
            "eventCount": len(self.events),
            "latestEvent": self.events[-1].public_dict() if self.events else None,
            "events": [event.public_dict() for event in self.events[-50:]],
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
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._workspace_manager = GitWorkspaceManager(
            settings.repo.path,
            settings.repo.state_dir,
            settings.repo.base_branch,
        )
        self._test_runner = TestRunner(settings.limits.task_timeout_seconds)
        self._worker_registry = WorkerRegistry(settings)
        self._store = SQLiteTaskStore(settings.repo.path, settings.repo.state_dir)
        self._loaded = False

    def ensure_started(self) -> None:
        if not self._loaded:
            self._load_persisted_tasks()
            self._loaded = True
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
            append_event(record, "queued", "Task queued.", status=record.status)
            self._tasks[record.id] = record
            self._cancel_events[record.id] = asyncio.Event()
            self._save_task(record)
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

    async def get_events(self, task_id: str, after: int | None = None) -> list[TaskEvent]:
        async with self._lock:
            try:
                record = self._tasks[task_id]
            except KeyError as exc:
                raise TaskNotFound(task_id) from exc
            if after is None:
                return list(record.events)
            return [event for event in record.events if event.sequence > after]

    async def cancel(self, task_id: str) -> TaskRecord:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                raise TaskNotFound(task_id)
            if record.status == TaskStatus.QUEUED:
                self._cancel_events[task_id].set()
                mark_canceled(record, "Canceled before execution.")
                self._save_task(record)
                return record
            if record.status == TaskStatus.WORKING:
                self._cancel_events[task_id].set()
                record.phase = "canceling"
                record.updated_at = utcnow()
                append_event(
                    record,
                    "canceling",
                    "Cancellation requested. Waiting for worker to stop.",
                    severity="warning",
                )
                self._save_task(record)
                return record
            raise TaskCannotCancel(f"Task {task_id} is already {record.status}.")

    def queue_summary(self) -> dict[str, int]:
        running = sum(1 for task in self._tasks.values() if task.status == TaskStatus.WORKING)
        queued = sum(1 for task in self._tasks.values() if task.status == TaskStatus.QUEUED)
        return {"running": running, "queued": queued}

    def _load_persisted_tasks(self) -> None:
        self._store.initialize()
        for payload in self._store.load_tasks():
            record = TaskRecord.model_validate(payload)
            self._tasks[record.id] = record
            self._cancel_events[record.id] = asyncio.Event()
            if record.status in {TaskStatus.SUBMITTED, TaskStatus.QUEUED, TaskStatus.WORKING}:
                if record.phase == "canceling":
                    record.status = TaskStatus.CANCELED
                    record.phase = "canceled"
                    record.error = "Task was interrupted by PatchRelay restart while canceling."
                else:
                    record.status = TaskStatus.FAILED
                    record.phase = "failed"
                    record.error = "Task was interrupted by PatchRelay restart."
                record.completed_at = utcnow()
                record.updated_at = record.completed_at
                severity = "warning" if record.status == TaskStatus.CANCELED else "error"
                append_event(record, record.phase, record.error, severity=severity, status=record.status)
                self._save_task(record)

    def _save_task(self, record: TaskRecord) -> None:
        self._store.save_task(record.model_dump(mode="json"))

    async def _run_queue(self) -> None:
        while True:
            task_id = await self._queue.get()
            try:
                await self._run_one(task_id)
            except Exception as exc:  # pragma: no cover - defensive queue guard
                await self._mark_worker_exception(task_id, exc)
            finally:
                self._queue.task_done()

    async def _run_one(self, task_id: str) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None or record.status == TaskStatus.CANCELED:
                return
            record.status = TaskStatus.WORKING
            record.phase = "workspace"
            record.started_at = utcnow()
            record.updated_at = record.started_at
            append_event(record, "workspace", "Task execution started.", status=record.status)
            self._save_task(record)

        cancel_event = self._cancel_events[task_id]
        workspace = await asyncio.to_thread(self._workspace_manager.create, task_id)
        await self._record_workspace(task_id, workspace)
        if cancel_event.is_set():
            await self._finalize_canceled(
                task_id,
                workspace.worktree_path,
                WorkerResult(
                    worker="none",
                    stdout="",
                    stderr="Task canceled before worker start.",
                    exit_code=130,
                    canceled=True,
                ),
            )
            return
        worker_result = await self._run_worker(task_id, workspace.worktree_path)
        if worker_result.canceled:
            await self._finalize_canceled(task_id, workspace.worktree_path, worker_result)
            return
        if cancel_event.is_set():
            await self._finalize_canceled(task_id, workspace.worktree_path, worker_result)
            return
        if worker_result.failed:
            await self._finalize_failed_after_worker(task_id, workspace.worktree_path, worker_result)
            return
        test_result = await self._run_tests(task_id, workspace.worktree_path)
        changed_files, diff_text = await self._collect_git_results(task_id, workspace.worktree_path)

        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            if record.status == TaskStatus.CANCELED or record.phase == "canceling" or cancel_event.is_set():
                pass
            else:
                record.status = TaskStatus.COMPLETED if test_result.exit_code == 0 else TaskStatus.FAILED
                record.phase = "completed" if record.status == TaskStatus.COMPLETED else "failed"
                if test_result.exit_code != 0:
                    record.error = f"Test profile '{test_result.profile}' failed with exit code {test_result.exit_code}."
                record.completed_at = utcnow()
                record.updated_at = record.completed_at
                severity = "info" if record.status == TaskStatus.COMPLETED else "error"
                message = "Task execution completed." if record.status == TaskStatus.COMPLETED else record.error
                append_event(record, record.phase, message or "Task execution finished.", severity=severity, status=record.status)
                self._attach_artifacts(
                    record,
                    changed_files=changed_files,
                    diff_text=diff_text,
                    test_result=test_result,
                    worker_result=worker_result,
                    exit_code=test_result.exit_code,
                )
                self._save_task(record)
                return

        await self._finalize_canceled(
            task_id,
            workspace.worktree_path,
            worker_result,
            test_result=test_result,
            changed_files=changed_files,
            diff_text=diff_text,
        )

    async def _record_workspace(self, task_id: str, workspace: Workspace) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None or record.status == TaskStatus.CANCELED:
                return
            record.branch = workspace.branch
            record.base_branch = workspace.base_branch
            record.worktree_path = workspace.worktree_path
            record.phase = "worker"
            record.updated_at = utcnow()
            append_event(record, "worker", f"Created worktree at {workspace.worktree_path}.", status=record.status)
            self._save_task(record)

    async def _run_worker(self, task_id: str, worktree_path: Path) -> WorkerResult:
        async with self._lock:
            record = self._tasks.get(task_id)
            cancel_event = self._cancel_events[task_id]
            if record is None or record.status == TaskStatus.CANCELED or cancel_event.is_set():
                return WorkerResult(worker="none", stdout="", stderr="Task was canceled.", exit_code=130, canceled=True)
            adapter = self._worker_registry.select(record.worker)
            append_event(record, record.phase, f"Worker '{adapter.name}' started.", status=record.status)
            record.updated_at = utcnow()
            self._save_task(record)

        result = await adapter.run(record.instruction, worktree_path, cancel_event)

        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return result
            if not result.canceled:
                record.phase = "tests"
            if result.stdout:
                append_event(record, "worker", result.stdout)
            if result.stderr:
                append_event(record, "worker", result.stderr, severity="warning")
            severity = "info" if result.exit_code == 0 else "error"
            append_event(record, record.phase, f"Worker '{result.worker}' exited with code {result.exit_code}.", severity=severity)
            record.updated_at = utcnow()
            self._save_task(record)
        return result

    async def _finalize_canceled(
        self,
        task_id: str,
        worktree_path: Path,
        worker_result: WorkerResult,
        *,
        test_result: TestRunResult | None = None,
        changed_files: list[str] | None = None,
        diff_text: str | None = None,
    ) -> None:
        if changed_files is None:
            changed_files = await asyncio.to_thread(self._workspace_manager.collect_changed_files, worktree_path)
        if diff_text is None:
            diff_text = await asyncio.to_thread(self._workspace_manager.collect_diff, worktree_path)
        final_test_result = test_result or TestRunResult(
            profile="canceled",
            command=[],
            stdout="",
            stderr="Task canceled.",
            exit_code=130,
            duration_seconds=0,
        )
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            mark_canceled(record, "Task canceled.")
            self._attach_artifacts(
                record,
                changed_files=changed_files,
                diff_text=diff_text,
                test_result=final_test_result,
                worker_result=worker_result,
                exit_code=final_test_result.exit_code,
            )
            self._save_task(record)

    async def _finalize_failed_after_worker(
        self,
        task_id: str,
        worktree_path: Path,
        worker_result: WorkerResult,
    ) -> None:
        changed_files = await asyncio.to_thread(self._workspace_manager.collect_changed_files, worktree_path)
        diff_text = await asyncio.to_thread(self._workspace_manager.collect_diff, worktree_path)
        skipped_tests = TestRunResult(
            profile="skipped",
            command=[],
            stdout="",
            stderr="Tests skipped because worker failed.",
            exit_code=1,
            duration_seconds=0,
        )
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None or record.status == TaskStatus.CANCELED:
                return
            record.status = TaskStatus.FAILED
            record.phase = "failed"
            record.error = f"Worker '{worker_result.worker}' failed with exit code {worker_result.exit_code}."
            record.completed_at = utcnow()
            record.updated_at = record.completed_at
            append_event(record, "failed", record.error, severity="error", status=record.status)
            self._attach_artifacts(
                record,
                changed_files=changed_files,
                diff_text=diff_text,
                test_result=skipped_tests,
                worker_result=worker_result,
                exit_code=worker_result.exit_code,
            )
            self._save_task(record)

    async def _run_tests(self, task_id: str, worktree_path: Path) -> TestRunResult:
        async with self._lock:
            record = self._tasks[task_id]
            profile = self._settings.tests[record.test_profile]
            append_event(record, "tests", f"Running test profile '{record.test_profile}'.", status=record.status)
            record.updated_at = utcnow()
            self._save_task(record)
        cancel_event = self._cancel_events[task_id]
        return await asyncio.to_thread(self._test_runner.run, record.test_profile, profile, worktree_path, cancel_event)

    async def _collect_git_results(self, task_id: str, worktree_path: Path) -> tuple[list[str], str]:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is not None:
                record.phase = "artifacts"
                append_event(record, "artifacts", "Collecting Git artifacts.", status=record.status)
                record.updated_at = utcnow()
                self._save_task(record)
        changed_files = await asyncio.to_thread(self._workspace_manager.collect_changed_files, worktree_path)
        diff_text = await asyncio.to_thread(self._workspace_manager.collect_diff, worktree_path)
        return changed_files, diff_text

    def _attach_artifacts(
        self,
        record: TaskRecord,
        *,
        changed_files: list[str],
        diff_text: str,
        test_result: TestRunResult,
        worker_result: WorkerResult,
        exit_code: int,
    ) -> None:
        clean_diff_text, diff_truncated = clean_diff(diff_text, self._settings.limits)
        clean_log_text, log_truncated = clean_log("\n".join(record.logs), self._settings.limits)
        record.artifacts["patchrelay.summary"] = Artifact(
            kind="application/json",
            content=build_summary_content(
                task_id=record.id,
                worker=worker_result.worker,
                status=record.status,
                changed_files=changed_files,
                test_status=test_result.status,
                exit_code=exit_code,
            ),
        )
        record.artifacts["patchrelay.diff"] = Artifact(
            kind="text/x-diff",
            content=clean_diff_text,
            truncated=diff_truncated,
        )
        record.artifacts["patchrelay.tests"] = Artifact(
            kind="application/json",
            content={
                "profile": test_result.profile,
                "command": test_result.command,
                "status": test_result.status,
                "exitCode": test_result.exit_code,
                "durationSeconds": test_result.duration_seconds,
                "timedOut": test_result.timed_out,
                "stdout": test_result.stdout,
                "stderr": test_result.stderr,
            },
        )
        record.artifacts["patchrelay.worker"] = Artifact(
            kind="application/json",
            content={
                "worker": worker_result.worker,
                "stdout": worker_result.stdout,
                "stderr": worker_result.stderr,
                "exitCode": worker_result.exit_code,
            },
        )
        record.artifacts["patchrelay.log"] = Artifact(
            kind="text/plain",
            content=clean_log_text,
            truncated=log_truncated,
        )

    async def _mark_worker_exception(self, task_id: str, exc: Exception) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None or record.status in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELED,
            }:
                return
            record.status = TaskStatus.FAILED
            record.phase = "failed"
            record.error = f"Worker exception: {exc}"
            record.completed_at = utcnow()
            record.updated_at = record.completed_at
            append_event(record, "failed", record.error, severity="error", status=record.status)
            fallback_result = TestRunResult(
                profile=record.test_profile,
                command=[],
                stdout="",
                stderr="",
                exit_code=1,
                duration_seconds=0,
            )
            self._attach_artifacts(
                record,
                changed_files=[],
                diff_text="",
                test_result=fallback_result,
                worker_result=WorkerResult(worker=record.worker, stdout="", stderr=str(exc), exit_code=1),
                exit_code=1,
            )
            self._save_task(record)

    async def shutdown(self) -> None:
        if self._worker_loop is not None:
            for event in self._cancel_events.values():
                event.set()
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
    append_event(record, "canceled", message, severity="warning", status=record.status)


def append_event(
    record: TaskRecord,
    phase: str,
    message: str,
    *,
    severity: str = "info",
    status: TaskStatus | None = None,
) -> None:
    event = TaskEvent(
        sequence=len(record.events) + 1,
        timestamp=utcnow(),
        phase=phase,
        message=message,
        severity=severity,
        status=status or record.status,
    )
    record.events.append(event)
    record.logs.append(f"[{event.phase}] {event.message}")


def format_sse_event(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str, ensure_ascii=False)}\n\n"
