"""Canonical models for deterministic engineering estimation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str = "estimate") -> str:
    return f"{prefix}-{uuid4().hex[:14]}"


def estimation_record(*, artifact: dict[str, Any], result: dict[str, Any], version: int = 1, parent_estimate_id: str = "") -> dict[str, Any]:
    generated_at = now_iso()
    return {
        "schemaVersion": "hei-engineering-estimation-v1",
        "estimateId": new_id(),
        "artifactId": str(artifact.get("id") or artifact.get("artifactId") or artifact.get("artifact_id") or ""),
        "artifactType": str(artifact.get("type") or artifact.get("artifactType") or artifact.get("artifact_type") or "Story"),
        "title": str(artifact.get("title") or "Engineering Work"),
        "projectId": str(artifact.get("projectId") or artifact.get("project_id") or ""),
        "version": version,
        "status": "Draft",
        "standardModel": "Standard Engineering Estimation",
        "originalEstimate": result,
        "effectiveEstimate": result,
        "userEstimate": None,
        "overrideReason": "",
        "parentEstimateId": parent_estimate_id,
        "repositorySnapshot": str(result.get("repositorySnapshot") or ""),
        "createdAt": generated_at,
        "updatedAt": generated_at,
    }
