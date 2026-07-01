"""Engineering Lifecycle Manager.

Coordinates Planning, Execution, QA, and Release state without generating
intelligence artifacts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .audit import LifecycleAudit
from .diagnostics import LifecycleDiagnostics
from .events import normalize_artifact_type, normalize_state
from .history import LifecycleHistory
from .rules import LifecycleRules
from .state_machine import LifecycleStateMachine


class EngineeringLifecycleManager:
    def __init__(self, storage_path: Path | None = None) -> None:
        data_dir = Path(os.getenv("AI_GEN_DATA_DIR", str(Path(__file__).parent.parent.parent / "data")))
        self._path = storage_path or data_dir / "project_intelligence" / "engineering_lifecycle.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.rules = LifecycleRules()
        self.machine = LifecycleStateMachine()
        self.history = LifecycleHistory()
        self.audit = LifecycleAudit()
        self.diagnostics = LifecycleDiagnostics()

    def get_lifecycle(self, artifact: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        artifact = artifact or {}
        context = context or {}
        artifact_id = _artifact_id(artifact)
        artifact_type = normalize_artifact_type(artifact.get("artifact_type") or artifact.get("type") or context.get("artifact_type"))
        stored = self._read().get(artifact_id) if artifact_id else None
        current_state = normalize_state((stored or {}).get("currentState") or _infer_state(artifact, context))
        rule = self.rules.evaluate(artifact_type, current_state, context)
        stage = self.rules.stage_for_state(current_state)
        lifecycle = {
            "artifactId": artifact_id,
            "artifactType": artifact_type,
            "currentState": current_state,
            "currentStage": stage,
            "nextState": _state_for_action(rule.next_action),
            "nextAction": rule.next_action,
            "allowedActions": rule.allowed_actions,
            "blockedActions": rule.blocked_actions,
            "completionPercent": self.rules.progress_for_state(current_state),
            "currentOwner": rule.owner,
            "blockingReason": rule.blocking_reason,
            "timeline": _timeline(current_state),
            "history": (stored or {}).get("history", []),
            "audit": self.audit.summarize((stored or {}).get("history", [])),
        }
        lifecycle["diagnostics"] = self.diagnostics.build(lifecycle, context)
        return lifecycle

    def advance(self, artifact: dict[str, Any], target_state: str = "", actor: str = "", context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        current = self.get_lifecycle(artifact, context)
        target = normalize_state(target_state or current.get("nextState") or current.get("currentState"))
        transition = self.machine.transition(current["currentState"], target, context)
        return self._persist_transition(artifact, current, transition, actor, "advance", context)

    def rollback(self, artifact: dict[str, Any], actor: str = "", context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        current = self.get_lifecycle(artifact, context)
        transition = self.machine.rollback(current["currentState"])
        return self._persist_transition(artifact, current, transition, actor, "rollback", context)

    def history_for(self, artifact_id: str) -> dict[str, Any]:
        stored = self._read().get(str(artifact_id), {})
        history = stored.get("history", []) if isinstance(stored.get("history"), list) else []
        return {"artifactId": artifact_id, "history": history, "audit": self.audit.summarize(history)}

    def diagnostics_for(self, artifact: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        lifecycle = self.get_lifecycle(artifact or {}, context or {})
        return lifecycle.get("diagnostics", {})

    def _persist_transition(
        self,
        artifact: dict[str, Any],
        current: dict[str, Any],
        transition: dict[str, Any],
        actor: str,
        event_type: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        artifact_id = current["artifactId"]
        artifact_type = current["artifactType"]
        store = self._read()
        record = store.get(artifact_id, {"history": []})
        event = self.history.event(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            event_type=event_type,
            from_state=transition["fromState"],
            to_state=transition["toState"],
            actor=actor,
            reason=transition["reason"],
            metadata={"allowed": transition["allowed"], "context": _safe_context(context)},
        )
        record["artifactId"] = artifact_id
        record["artifactType"] = artifact_type
        record["currentState"] = transition["toState"] if transition["allowed"] else transition["fromState"]
        record["history"] = self.history.append(record.get("history", []), event)
        store[artifact_id] = record
        self._write(store)
        lifecycle = self.get_lifecycle({**artifact, "id": artifact_id, "type": artifact_type, "state": record["currentState"]}, context)
        lifecycle["transition"] = transition
        return lifecycle

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            states = payload.get("states") if isinstance(payload, dict) else {}
            return states if isinstance(states, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, states: dict[str, Any]) -> None:
        self._path.write_text(json.dumps({"schemaVersion": "engineering-lifecycle-v1", "states": states}, indent=2), encoding="utf-8")


def _artifact_id(artifact: dict[str, Any]) -> str:
    return str(artifact.get("artifact_id") or artifact.get("artifactId") or artifact.get("id") or artifact.get("work_item_id") or "current")


def _infer_state(artifact: dict[str, Any], context: dict[str, Any]) -> str:
    explicit = artifact.get("lifecycle_state") or artifact.get("state") or context.get("state")
    if explicit:
        return normalize_state(explicit)
    if context.get("release_recommendation") in {"Ready For Release", "Ready With Warnings"}:
        return "Release Ready"
    if context.get("qa_status") in {"Ready", "Needs Review", "Blocked"}:
        return "QA Analysis Complete"
    if context.get("validation_status") in {"Passed", "NeedsReview", "Needs Review"}:
        return "Implementation Validated"
    if context.get("has_execution_plan"):
        return "Execution Plan Generated"
    if context.get("has_execution_package"):
        return "Execution Package Built"
    if str(artifact.get("status") or "").lower() in {"approved", "created"}:
        return "Approved"
    return "Draft"


def _state_for_action(action: str) -> str:
    from .rules import ACTION_TO_STATE

    return ACTION_TO_STATE.get(action, "")


def _timeline(current_state: str) -> list[dict[str, str]]:
    from .events import STATE_SEQUENCE

    current_index = STATE_SEQUENCE.index(current_state) if current_state in STATE_SEQUENCE else 0
    timeline = []
    for index, state in enumerate(STATE_SEQUENCE):
        if index < current_index:
            status = "complete"
        elif index == current_index:
            status = "current"
        else:
            status = "pending"
        timeline.append({"state": state, "stage": LifecycleRules().stage_for_state(state), "status": status})
    return timeline


def _safe_context(context: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "has_tasks",
        "has_execution_package",
        "has_execution_plan",
        "validation_status",
        "qa_status",
        "release_recommendation",
        "artifact_type",
    }
    return {key: context.get(key) for key in allowed if key in context}
