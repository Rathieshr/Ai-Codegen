"""Canonical, adapter-independent HEI model profile contracts."""

from __future__ import annotations

from typing import TypedDict


MODEL_REGISTRY_VERSION = "1.0"


class ModelProfile(TypedDict):
    id: str
    name: str
    provider: str
    contextWindow: int
    reasoning: bool
    maxOutput: int
    toolSupport: bool
    vision: bool
    streaming: bool
    temperatureSupport: bool
    jsonSupport: bool
    systemPromptSupport: bool
    capabilityTags: list[str]
    enabled: bool
    registryVersion: str
