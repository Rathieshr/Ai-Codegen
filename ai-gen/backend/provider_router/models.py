"""Canonical Provider Router contracts."""

from __future__ import annotations

from typing import Any, TypedDict


PROVIDER_ROUTER_VERSION = "1.0"


class ProviderRoutingResult(TypedDict):
    routingId: str
    routerVersion: str
    executionManifestId: str
    selectedProvider: dict[str, Any]
    routingDecision: dict[str, Any]
    prompt: dict[str, Any]
    reasons: list[str]
    routingRules: list[dict[str, Any]]
    warnings: list[str]
    immutable: bool
    immutableHash: str
    routedAt: str
    diagnostics: dict[str, Any]
