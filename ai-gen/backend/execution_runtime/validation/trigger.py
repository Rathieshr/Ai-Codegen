"""Downstream intent construction without downstream service invocation."""

from __future__ import annotations

from typing import Any


def build_downstream_intents(session: dict[str, Any], result: dict[str, Any], diff: dict[str, Any]) -> list[dict[str, Any]]:
    common = {
        "sessionId": session["sessionId"],
        "resultId": result["resultId"],
        "engineeringDiffId": diff["diffId"],
        "correlationId": session["correlationId"],
        "executionPackageVersion": session["executionPackageVersion"],
        "repositorySnapshotVersion": session["repositorySnapshotVersion"],
    }
    return [
        {"type": "ImplementationValidation", "status": "Pending", "invoked": False, **common},
        {"type": "QAAnalysis", "status": "Pending", "invoked": False, **common},
        {"type": "EngineeringMemoryCandidate", "status": "PendingValidation", "invoked": False, **common},
        {"type": "PRCandidate", "status": "Draft", "invoked": False, **common},
    ]
