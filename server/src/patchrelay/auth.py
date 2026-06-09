from __future__ import annotations

from collections.abc import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


PUBLIC_PATHS = {
    "/health",
    "/.well-known/agent-card.json",
}


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        authorization = request.headers.get("authorization", "")
        expected = f"Bearer {self._token}"
        if authorization != expected:
            return JSONResponse(
                status_code=401,
                content={"error": "unauthorized", "message": "Valid Bearer token required."},
            )

        return await call_next(request)
