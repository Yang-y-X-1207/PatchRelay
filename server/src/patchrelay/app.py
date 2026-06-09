from fastapi import FastAPI

from patchrelay import __version__


def create_app() -> FastAPI:
    app = FastAPI(
        title="PatchRelay",
        version=__version__,
        description="Local A2A-compatible coding execution relay.",
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
