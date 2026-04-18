"""Lightweight environment and provider status checks for ai-gen."""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from typing import Any

from backend.model_router import get_available_targets


def get_status() -> dict[str, Any]:
    """Return deterministic backend, Codex, local, and cloud status."""

    available_targets = get_available_targets()
    local_enabled = os.getenv("AI_GEN_LOCAL_ENABLED") == "1"
    local_provider = _env_or_none("AI_GEN_LOCAL_PROVIDER")
    local_model = _env_or_none("AI_GEN_LOCAL_MODEL")
    local_base_url = _env_or_none("AI_GEN_LOCAL_BASE_URL")
    cloud_enabled = os.getenv("AI_GEN_CLOUD_ENABLED") == "1"
    warnings: list[str] = []

    if local_enabled and not local_provider:
        warnings.append("Local model is enabled but provider is missing")
    if local_enabled and not local_model:
        warnings.append("Local model name is not configured")

    local_available = False
    if local_enabled and local_provider == "ollama":
        base_url = local_base_url or "http://localhost:11434"
        local_base_url = base_url
        local_available = is_ollama_reachable(base_url)
        if not local_available:
            warnings.append("Ollama is enabled but not reachable")
    elif local_enabled and local_provider:
        warnings.append(f"Local provider '{local_provider}' is not supported yet")

    if not available_targets["codex"]:
        warnings.append("Codex is not available on PATH")

    return {
        "backend_up": True,
        "codex_available": available_targets["codex"],
        "local_enabled": local_enabled,
        "local_provider": local_provider,
        "local_model": local_model,
        "local_available": local_available,
        "local_base_url": local_base_url,
        "cloud_enabled": cloud_enabled,
        "warnings": warnings,
        "available_targets": available_targets,
        "supported_targets": ["local", "cloud", "codex", "preview_only"],
        "env": {
            "AI_GEN_LOCAL_ENABLED": os.getenv("AI_GEN_LOCAL_ENABLED"),
            "AI_GEN_LOCAL_PROVIDER": local_provider,
            "AI_GEN_LOCAL_MODEL": local_model,
            "AI_GEN_LOCAL_BASE_URL": local_base_url,
            "AI_GEN_CLOUD_ENABLED": os.getenv("AI_GEN_CLOUD_ENABLED"),
            "AI_GEN_CODEX_ENABLED": os.getenv("AI_GEN_CODEX_ENABLED"),
        },
    }


def is_ollama_reachable(base_url: str) -> bool:
    """Check Ollama reachability without requiring any external dependency."""

    url = f"{base_url.rstrip('/')}/api/tags"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=1) as response:
            return 200 <= getattr(response, "status", 200) < 300
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def _env_or_none(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip()
