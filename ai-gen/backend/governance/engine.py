"""Engineering Governance facade."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .approval import ApprovalEngine
from .audit import AuditTimeline
from .compliance import ComplianceEngine
from .diagnostics import GovernanceDiagnostics
from .feedback import FeedbackEngine
from .metrics import MetricsEngine
from .observability import ObservabilityEngine
from .policy import PolicyEngine
from .scorecard import EngineeringScorecard
from .types import normalize_policy, now_iso


class GovernanceEngine:
    def __init__(self, storage_path: Path | None = None) -> None:
        data_dir = Path(os.getenv("AI_GEN_DATA_DIR", str(Path(__file__).parent.parent.parent / "data")))
        self._path = storage_path or data_dir / "project_intelligence" / "governance.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.policies = PolicyEngine()
        self.approvals = ApprovalEngine()
        self.compliance = ComplianceEngine()
        self.metrics = MetricsEngine()
        self.feedback = FeedbackEngine()
        self.observability = ObservabilityEngine()
        self.audit = AuditTimeline()
        self.diagnostics = GovernanceDiagnostics()
        self.scorecard = EngineeringScorecard()

    def dashboard(self) -> dict[str, Any]:
        state = self._read()
        policy_result = self.policies.enforce({}, {}, state["policies"])
        compliance = self.compliance.validate({}, {}, policy_result)
        metrics = self.metrics.aggregate(state["metrics"], state["observability"], state["approvals"])
        feedback = self.feedback.summary(state["feedback"])
        observability = self.observability.summary(state["observability"])
        return {
            "policies": state["policies"],
            "approvals": self.approvals.summary(state["approvals"]),
            "compliance": compliance,
            "metrics": metrics,
            "feedback": feedback,
            "observability": observability,
            "auditTimeline": self.audit.timeline(state["audit"]),
            "scorecard": self.scorecard.build(compliance, metrics, feedback, observability),
            "diagnostics": self.diagnostics.summarize(state),
        }

    def list_policies(self) -> dict[str, Any]:
        state = self._read()
        return {"policies": state["policies"], "count": len(state["policies"])}

    def save_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        state = self._read()
        normalized = normalize_policy(policy)
        replaced = False
        for index, existing in enumerate(state["policies"]):
            if existing.get("id") == normalized["id"]:
                state["policies"][index] = normalized
                replaced = True
                break
        if not replaced:
            state["policies"].append(normalized)
        self._write(state)
        return {"policy": normalized, "created": not replaced}

    def enforce_policies(self, artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return self.policies.enforce(artifact, context, self._read()["policies"])

    def request_approval(self, approval: dict[str, Any], actor: str = "") -> dict[str, Any]:
        state = self._read()
        requested = self.approvals.request(state["approvals"], {**approval, "requestedBy": actor or approval.get("requestedBy")})
        self.audit.record(state["audit"], {
            "who": actor or requested.get("requestedBy") or "system",
            "what": f"Approval requested for {requested['artifactType']} {requested['artifactTitle']}",
            "why": requested.get("reason"),
            "artifactType": requested.get("artifactType"),
            "artifactId": requested.get("artifactId"),
            "eventType": "Approval",
        })
        self._write(state)
        return {"approval": requested}

    def update_approval(self, approval_id: str, status: str, actor: str = "", reason: str = "") -> dict[str, Any]:
        state = self._read()
        updated = self.approvals.transition(state["approvals"], approval_id, status, actor, reason)
        self.audit.record(state["audit"], {
            "who": actor or "system",
            "what": f"Approval {status}",
            "why": reason,
            "artifactType": updated.get("artifactType"),
            "artifactId": updated.get("artifactId"),
            "eventType": "Approval",
        })
        self._write(state)
        return {"approval": updated}

    def validate_compliance(self, artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        policy_result = self.enforce_policies(artifact, context)
        return self.compliance.validate(artifact, context, policy_result)

    def record_metric(self, metric: dict[str, Any]) -> dict[str, Any]:
        state = self._read()
        stored = self.metrics.record(state["metrics"], metric)
        self._write(state)
        return {"metric": stored}

    def record_feedback(self, feedback: dict[str, Any]) -> dict[str, Any]:
        state = self._read()
        stored = self.feedback.record(state["feedback"], feedback)
        self._write(state)
        return {"feedback": stored}

    def record_observation(self, observation: dict[str, Any]) -> dict[str, Any]:
        state = self._read()
        stored = self.observability.record(state["observability"], observation)
        self._write(state)
        return {"observation": stored}

    def record_audit(self, event: dict[str, Any]) -> dict[str, Any]:
        state = self._read()
        stored = self.audit.record(state["audit"], event)
        self._write(state)
        return {"event": stored}

    def audit_timeline(self, artifact_id: str = "") -> dict[str, Any]:
        return self.audit.timeline(self._read()["audit"], artifact_id)

    def diagnostics_summary(self) -> dict[str, Any]:
        return self.diagnostics.summarize(self._read())

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return self._default_state()
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._default_state()
        state = self._default_state()
        for key in ["policies", "approvals", "metrics", "feedback", "observability", "audit"]:
            if isinstance(payload.get(key), list):
                state[key] = payload[key]
        return state

    def _write(self, state: dict[str, Any]) -> None:
        payload = {
            "schemaVersion": "engineering-governance-v1",
            "updatedAt": now_iso(),
            **{key: state.get(key, []) for key in ["policies", "approvals", "metrics", "feedback", "observability", "audit"]},
        }
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _default_state(self) -> dict[str, Any]:
        return {
            "policies": self.policies.default_policies(),
            "approvals": [],
            "metrics": [],
            "feedback": [],
            "observability": [],
            "audit": [],
        }
