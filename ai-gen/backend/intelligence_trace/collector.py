"""Collect normalized traces from intelligence decisions."""

from __future__ import annotations

from typing import Any

from .types import normalize_trace


class TraceCollector:
    def decision_trace(
        self,
        *,
        project_id: str,
        artifact_type: str,
        artifact_id: str,
        artifact_title: str,
        stage: str,
        source: str,
        decision: str,
        reason: str,
        confidence: float,
        evidence: list[Any] | None = None,
        memory_used: list[Any] | None = None,
        repository_evidence: list[Any] | None = None,
        graph_evidence: list[Any] | None = None,
        validation_result: dict[str, Any] | None = None,
        prompt_version: str = "",
        latency_ms: int = 0,
        model: str = "",
        token_usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return normalize_trace({
            "projectId": project_id,
            "artifactType": artifact_type,
            "artifactId": artifact_id,
            "artifactTitle": artifact_title,
            "stage": stage,
            "source": source,
            "decision": decision,
            "reason": reason,
            "confidence": confidence,
            "evidence": evidence or [],
            "memoryUsed": memory_used or [],
            "repositoryEvidence": repository_evidence or [],
            "graphEvidence": graph_evidence or [],
            "validationResult": validation_result or {},
            "promptVersion": prompt_version,
            "latencyMs": latency_ms,
            "model": model,
            "tokenUsage": token_usage or {},
            "metadata": metadata or {},
        })
