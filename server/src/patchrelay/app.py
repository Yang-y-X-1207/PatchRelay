from pathlib import Path

from fastapi import FastAPI

from patchrelay import __version__
from patchrelay.auth import BearerAuthMiddleware
from patchrelay.config import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(
        title="PatchRelay",
        version=__version__,
        description="Local A2A-compatible coding execution relay.",
    )
    app.state.settings = settings
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
            "queue": {"running": 0, "queued": 0},
            "workers": {
                "fake": {"available": True},
                "codex": {"configuredCommand": settings.worker.codex_command},
                "claude": {"configuredCommand": settings.worker.claude_command},
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

    return app


app = create_app()
