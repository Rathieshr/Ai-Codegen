"""HEI Agent Orchestrator compatibility facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .engine import AgentEngine


class AgentOrchestrator:
    def __init__(self, storage_path: Path | None = None) -> None:
        policy_path = storage_path.parent / "agent_policy.json" if storage_path else None
        self._engine = AgentEngine(storage_path, policy_path)

    def dashboard(self) -> dict[str, Any]:
        return self._engine.dashboard()

    def trigger(self, event: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._engine.trigger(event, context)

    def resume(self, workflow_id: str, actor: str = "") -> dict[str, Any]:
        return self._engine.resume(workflow_id, actor)

    def retry(self, workflow_id: str) -> dict[str, Any]:
        return self._engine.retry(workflow_id)

    def list_workflows(self, state_filter: str = "") -> dict[str, Any]:
        return self._engine.list_workflows(state_filter)

    def list_events(self, event_type: str = "") -> dict[str, Any]:
        return self._engine.list_events(event_type)

    def update_feature_flags(self, flags: dict[str, Any]) -> dict[str, Any]:
        return self._engine.update_feature_flags(flags)

    def diagnostics_summary(self) -> dict[str, Any]:
        return self._engine.diagnostics_summary()
