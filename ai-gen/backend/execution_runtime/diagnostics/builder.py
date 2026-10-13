"""Execution Runtime diagnostics projection."""

from __future__ import annotations


def build_diagnostics(session: dict, result: dict | None = None, artifacts: list[dict] | None = None, diff: dict | None = None) -> dict:
    result = result or {}
    artifacts = artifacts or []
    return {
        "sessionId": session["sessionId"],
        "status": session["status"],
        "executionDurationMs": session["duration"],
        "provider": session["provider"],
        "model": session["model"],
        "tokenUsage": result.get("tokenUsage") or {},
        "confidence": session["confidence"],
        "warnings": list(session.get("warnings") or []),
        "repositorySnapshotVersion": session["repositorySnapshotVersion"],
        "executionPlanVersion": session["executionPlanVersion"],
        "executionPackageVersion": session["executionPackageVersion"],
        "correlationId": session["correlationId"],
        "resultId": result.get("resultId"),
        "responseType": result.get("responseType"),
        "artifactCount": len(artifacts),
        "engineeringDiffId": (diff or {}).get("diffId"),
        "repositoryModified": False,
        "gitOperations": 0,
        "azureDevOpsWrites": 0,
        "pullRequestsCreated": 0,
        "providerInvoked": False,
        "llmCalls": 0,
        "downstreamServicesInvoked": 0,
        "attempt": int(session.get("attempt") or 1),
        "maxRetries": int(session.get("maxRetries") or 0),
        "retryCount": int((session.get("recovery") or {}).get("retryCount") or 0),
        "resumeCount": int((session.get("recovery") or {}).get("resumeCount") or 0),
        "duplicateResponseCount": int(session.get("duplicateResponseCount") or 0),
        "partialResponseCount": len(session.get("partialResponses") or []),
        "lastCheckpoint": str(session.get("lastCheckpoint") or ""),
        "failureType": str((session.get("lastFailure") or {}).get("type") or ""),
        "recoveryHistory": list((session.get("recovery") or {}).get("history") or []),
    }
