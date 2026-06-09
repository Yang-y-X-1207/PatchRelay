import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from starlette.responses import StreamingResponse

from patchrelay import __version__
from patchrelay.auth import BearerAuthMiddleware
from patchrelay.config import Settings, load_settings
from patchrelay.tasks import (
    SendMessageRequest,
    TaskCannotCancel,
    TaskError,
    TaskNotFound,
    TaskService,
    format_sse_event,
)
from patchrelay.workers import worker_command_status


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.tasks.ensure_started()
        try:
            yield
        finally:
            await app.state.tasks.shutdown()

    app = FastAPI(
        title="PatchRelay",
        version=__version__,
        description="Local A2A-compatible coding execution relay.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.tasks = TaskService(settings)
    app.add_middleware(BearerAuthMiddleware, token=settings.server.token)

    @app.get("/health")
    async def health() -> dict:
        repo_path = Path(settings.repo.path)
        return {
            "status": "ok",
            "version": __version__,
            "config": {
                "repoPath": str(repo_path),
                "repoExists": repo_path.exists(),
                "baseBranch": settings.repo.base_branch,
                "defaultWorker": settings.worker.default,
                "testProfiles": sorted(settings.tests.keys()),
            },
            "queue": app.state.tasks.queue_summary(),
            "workers": {
                "fake": {"available": True},
                "codex": worker_command_status(settings.worker.codex_command),
                "claude": worker_command_status(settings.worker.claude_command),
            },
        }

    @app.get("/.well-known/agent-card.json")
    async def agent_card() -> dict:
        return {
            "name": "PatchRelay",
            "description": "Local A2A-compatible coding execution relay.",
            "version": __version__,
            "url": f"http://{settings.server.host}:{settings.server.port}",
            "capabilities": {
                "streaming": True,
                "codingExecution": True,
            },
            "securitySchemes": {
                "bearer": {"type": "http", "scheme": "bearer"},
            },
            "skills": [
                {
                    "id": "coding-task-execution",
                    "name": "Coding task execution",
                    "description": "Accepts coding tasks and returns logs, artifacts, and status.",
                }
            ],
        }

    @app.post("/message:send")
    async def send_message(request: SendMessageRequest) -> dict:
        try:
            task = await app.state.tasks.submit(request)
        except TaskError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "taskId": task.id,
            "status": task.status,
            "createdAt": task.created_at.isoformat(),
        }

    @app.post("/message:stream")
    async def stream_message(request: SendMessageRequest) -> StreamingResponse:
        try:
            task = await app.state.tasks.submit(request)
        except TaskError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        async def events() -> AsyncIterator[str]:
            last_status = None
            while True:
                current = await app.state.tasks.get(task.id)
                if current.status != last_status:
                    yield format_sse_event("task", current.public_dict())
                    last_status = current.status
                if current.status in {"completed", "failed", "canceled"}:
                    yield format_sse_event("done", current.public_dict())
                    break
                await asyncio.sleep(0.02)

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/tasks")
    async def list_tasks() -> dict:
        tasks = await app.state.tasks.list_tasks()
        return {"tasks": [task.public_dict() for task in tasks]}

    @app.get("/tasks/{task_id}")
    async def get_task(task_id: str) -> dict:
        try:
            task = await app.state.tasks.get(task_id)
        except TaskNotFound as exc:
            raise HTTPException(status_code=404, detail="Task not found.") from exc
        return task.public_dict()

    @app.post("/tasks/{task_id}:cancel")
    async def cancel_task(task_id: str) -> dict:
        try:
            task = await app.state.tasks.cancel(task_id)
        except TaskNotFound as exc:
            raise HTTPException(status_code=404, detail="Task not found.") from exc
        except TaskCannotCancel as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return task.public_dict()

    return app


app = create_app()
