"""Read-only HEI Model Registry."""

from __future__ import annotations

from copy import deepcopy
from typing import Iterable

from .models import ModelProfile
from .profiles import MODEL_PROFILES


class ModelRegistry:
    def __init__(self, profiles: Iterable[ModelProfile] | None = None) -> None:
        source = tuple(profiles) if profiles is not None else MODEL_PROFILES
        self._profiles = _validate_profiles(source)

    def list(self) -> list[ModelProfile]:
        return deepcopy(list(self._profiles.values()))

    def get(self, model_id: str) -> ModelProfile | None:
        profile = self._profiles.get(str(model_id or "").strip().casefold())
        return deepcopy(profile) if profile else None


def _validate_profiles(profiles: tuple[ModelProfile, ...]) -> dict[str, ModelProfile]:
    required = {
        "id", "name", "provider", "contextWindow", "reasoning", "maxOutput",
        "toolSupport", "vision", "streaming", "temperatureSupport", "jsonSupport",
        "systemPromptSupport", "capabilityTags", "enabled", "registryVersion",
    }
    result: dict[str, ModelProfile] = {}
    for raw in profiles:
        profile = deepcopy(raw)
        missing = required - set(profile)
        if missing:
            raise ValueError(f"Model profile is missing required fields: {', '.join(sorted(missing))}.")
        model_id = str(profile["id"] or "").strip().casefold()
        if not model_id:
            raise ValueError("Model profile id is required.")
        if model_id in result:
            raise ValueError(f"Duplicate model profile id: {model_id}.")
        if int(profile["contextWindow"]) <= 0 or int(profile["maxOutput"]) <= 0:
            raise ValueError(f"Model profile {model_id} must define positive context and output limits.")
        if int(profile["maxOutput"]) > int(profile["contextWindow"]):
            raise ValueError(f"Model profile {model_id} maxOutput cannot exceed contextWindow.")
        profile["id"] = model_id
        profile["capabilityTags"] = list(dict.fromkeys(str(tag).strip() for tag in profile["capabilityTags"] if str(tag).strip()))
        result[model_id] = profile
    return result
