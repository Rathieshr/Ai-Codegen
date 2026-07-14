"""Unapproved Engineering Memory candidate projection."""

from __future__ import annotations

from backend.token_intelligence.models import stable_hash


def build_memory_candidate(session: dict, result: dict, artifacts: list[dict], diff: dict) -> dict:
    core = {"sessionId": session["sessionId"], "resultId": result["resultId"], "diffId": diff["diffId"]}
    return {
        "candidateId": f"memorycandidate_{stable_hash(core)[:12]}",
        "status": "PendingValidation",
        "approvalStatus": "Draft",
        "indexed": False,
        "sessionId": session["sessionId"],
        "resultId": result["resultId"],
        "artifactIds": [artifact["artifactId"] for artifact in artifacts],
        "engineeringDiffId": diff["diffId"],
        "correlationId": session["correlationId"],
    }
