"""Agent policies and feature flags."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_FEATURE_FLAGS = {
    "planningAgent": True,
    "executionAgent": True,
    "qaAgent": True,
    "reviewAgent": True,
    "memoryAgent": True,
    "repositoryAgent": True,
}

DEFAULT_POLICIES = [
    "Agents never approve work.",
    "Agents never merge pull requests.",
    "Agents never modify repository contents.",
    "Agents never override approval policies.",
    "Agents prepare artifacts and wait at human approval boundaries.",
]


class AgentPolicy:
    def __init__(self, storage_path: Path | None = None) -> None:
        data_dir = Path(os.getenv("AI_GEN_DATA_DIR", str(Path(__file__).parent.parent.parent / "data")))
        self._path = storage_path or data_dir / "project_intelligence" / "agent_policy.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def feature_flags(self) -> dict[str, bool]:
        stored = self._read()
        flags = stored.get("featureFlags") if isinstance(stored.get("featureFlags"), dict) else {}
        return {key: bool(flags.get(key, default)) for key, default in DEFAULT_FEATURE_FLAGS.items()}

    def update_feature_flags(self, flags: dict[str, Any]) -> dict[str, bool]:
        current = self.feature_flags()
        for key in current:
            if key in flags:
                current[key] = bool(flags[key])
        self._write({"featureFlags": current})
        return current

    def policies(self) -> list[str]:
        stored = self._read()
        items = stored.get("policies") if isinstance(stored.get("policies"), list) else []
        return [str(item).strip() for item in items if str(item).strip()] or list(DEFAULT_POLICIES)

    def policy_decision(self, agent: dict[str, Any]) -> dict[str, Any]:
        flags = self.feature_flags()
        key = str(agent.get("featureFlag") or "").strip()
        enabled = flags.get(key, True) if key else True
        return {
            "allowed": enabled,
            "reason": "Agent enabled by feature flag." if enabled else f"{agent.get('name', 'Agent')} is disabled by feature flag.",
            "featureFlag": key,
            "featureFlags": flags,
            "policies": self.policies(),
            "approvalRequired": True,
        }

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, payload: dict[str, Any]) -> None:
        existing = self._read()
        self._path.write_text(json.dumps({**existing, **payload}, indent=2), encoding="utf-8")
