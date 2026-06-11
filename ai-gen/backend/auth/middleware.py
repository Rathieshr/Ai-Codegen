"""API key middleware for ai-gen backend.

Authentication strategy
-----------------------
Shared-secret header auth via ``X-Api-Key``.

Set one or more comma-separated keys in the environment:

    AI_GEN_API_KEYS=key1,key2

If ``AI_GEN_API_KEYS`` is empty or unset the middleware runs in
**open mode** (no auth required). This preserves zero-config local
development while enforcing auth in production.

Upgrade path
------------
For enterprise Azure AD / OAuth, replace ``_load_api_keys`` with a
token-introspection call and update ``verify_request`` to validate
JWT claims instead of raw key comparison.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger("ai_gen.auth")

# ---------------------------------------------------------------------------
# Paths that skip authentication entirely
# ---------------------------------------------------------------------------
_PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/capabilities",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)


def _load_api_keys() -> frozenset[str]:
    raw = os.getenv("AI_GEN_API_KEYS", "")
    return frozenset(k.strip() for k in raw.split(",") if k.strip())


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that validates ``X-Api-Key`` on every request.

    If ``AI_GEN_API_KEYS`` is not configured the middleware passes all
    requests through and logs a warning once at startup.
    """

    def __init__(self, app: ASGIApp, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        self._keys = _load_api_keys()
        self._open_mode = not self._keys
        if self._open_mode:
            logger.warning(
                "ai-gen auth: AI_GEN_API_KEYS is not set — running in open mode. "
                "Set this env var to enable API key authentication."
            )
        else:
            logger.info(
                "ai-gen auth: API key authentication enabled (%d key(s) loaded).",
                len(self._keys),
            )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self._open_mode or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        # OPTIONS pre-flight: always pass through (CORS handles it)
        if request.method == "OPTIONS":
            return await call_next(request)

        key = request.headers.get("X-Api-Key", "").strip()
        if not key:
            logger.warning(
                "ai-gen auth: rejected request — missing X-Api-Key header. "
                "path=%s method=%s",
                request.url.path,
                request.method,
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "detail": "Missing X-Api-Key header.",
                    "hint": "Set AI_GEN_API_KEYS on the server and pass one of those keys as X-Api-Key.",
                },
            )

        if key not in self._keys:
            logger.warning(
                "ai-gen auth: rejected request — invalid API key. path=%s",
                request.url.path,
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "detail": "Invalid API key.",
                },
            )

        return await call_next(request)


def get_api_key_status() -> dict[str, Any]:
    """Return auth configuration status (safe to expose in /capabilities)."""
    keys = _load_api_keys()
    return {
        "auth_enabled": bool(keys),
        "auth_mode": "api_key" if keys else "open",
        "key_count": len(keys),
    }
