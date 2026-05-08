"""Refinement provider abstraction and factory."""

from __future__ import annotations

import os
from typing import Any, Protocol


class RefinementProvider(Protocol):
    """Small JSON-only refinement interface."""

    def is_enabled(self) -> bool:
        """Return whether the provider is configured and enabled."""

    def refine_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 800) -> dict[str, Any]:
        """Return validated-ish JSON or an empty dict on failure."""


def get_refinement_provider() -> RefinementProvider | None:
    """Return the configured provider, or None when refinement is disabled."""

    if os.getenv("AI_GEN_REFINER_ENABLED") != "1":
        return None

    provider_name = (os.getenv("AI_GEN_REFINER_PROVIDER") or "").strip().lower()
    if provider_name != "azure_phi":
        return None

    from .phi_provider import AzurePhiProvider

    return AzurePhiProvider()


def get_refiner_status() -> dict[str, Any]:
    """Return non-secret refinement provider status for capabilities/health."""

    provider_name = (os.getenv("AI_GEN_REFINER_PROVIDER") or "").strip().lower()
    enabled = os.getenv("AI_GEN_REFINER_ENABLED") == "1"
    configured = bool(
        enabled
        and provider_name == "azure_phi"
        and _env("AI_GEN_REFINER_ENDPOINT")
        and _env("AI_GEN_REFINER_API_KEY")
        and _env("AI_GEN_REFINER_MODEL")
    )
    return {
        "enabled": enabled,
        "provider": provider_name or None,
        "model": _env("AI_GEN_REFINER_MODEL"),
        "configured": configured,
    }


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip()
