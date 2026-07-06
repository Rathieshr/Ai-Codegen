from __future__ import annotations

from typing import Any

from .capability_context import CapabilityMatch, RejectedCapability


def build_recommendations(scored_candidates: list[dict[str, Any]], threshold: int, max_items: int = 6) -> dict[str, Any]:
    accepted = [item for item in scored_candidates if item.get("accepted")][:max_items]
    rejected = [item for item in scored_candidates if not item.get("accepted")]
    matches = [
        CapabilityMatch(
            name=str(item.get("name") or ""),
            type="capability",
            confidence=float(item.get("confidence") or 0),
            reason=_reason(item),
            source=_source(item),
            evidence=_evidence(item),
        )
        for item in accepted
        if item.get("name")
    ]
    rejected_matches = [
        RejectedCapability(
            name=str(item.get("name") or ""),
            reason=_rejection_reason(item, threshold),
            confidence=float(item.get("confidence") or 0),
        )
        for item in rejected
        if item.get("name")
    ]
    report = {
        "threshold": threshold,
        "selectedCount": len(matches),
        "candidateCount": len(scored_candidates),
        "recommendations": [
            {
                "name": item.get("name"),
                "intent": item.get("intent_score", 0),
                "keywords": item.get("keyword_score", 0),
                "businessGoal": item.get("business_goal_score", 0),
                "repository": item.get("repository_score", 0),
                "knowledge": item.get("knowledge_score", 0),
                "memory": item.get("memory_score", 0),
                "final": item.get("overall_score", 0),
                "confidence": item.get("confidence", 0),
                "accepted": bool(item.get("accepted")),
                "reason": _reason(item),
                "evidence": _evidence(item),
            }
            for item in scored_candidates
        ],
    }
    return {"accepted": matches, "rejected": rejected_matches, "report": report}


def _source(item: dict[str, Any]) -> str:
    if item.get("repository_score", 0) >= item.get("knowledge_score", 0) and item.get("repository_score", 0) > 0:
        return "repository"
    if item.get("knowledge_score", 0) > 0:
        return "knowledge_registry"
    if item.get("memory_score", 0) > 0:
        return "memory"
    return "intent"


def _evidence(item: dict[str, Any]) -> list[str]:
    values = [
        *(item.get("evidence") or []),
        *(item.get("knowledge_evidence") or []),
        *(item.get("repository_evidence") or []),
        *(item.get("memory_evidence") or []),
    ]
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(str(value).strip().split())
        key = cleaned.lower()
        if cleaned and key not in seen:
            output.append(cleaned)
            seen.add(key)
    return output[:8]


def _reason(item: dict[str, Any]) -> str:
    evidence = _evidence(item)[:3]
    fragments = []
    if item.get("business_goal_score", 0) >= 70:
        fragments.append("business goal")
    if item.get("repository_score", 0) >= 70:
        fragments.append("repository evidence")
    if item.get("knowledge_score", 0) >= 70:
        fragments.append("knowledge registry")
    if item.get("memory_score", 0) >= 70:
        fragments.append("engineering memory")
    if not fragments:
        fragments.append("intent analysis")
    suffix = f" Evidence: {', '.join(evidence)}." if evidence else ""
    return f"{item.get('name')} is recommended because it strongly matches the epic goal through {', '.join(fragments)}.{suffix}"


def _rejection_reason(item: dict[str, Any], threshold: int) -> str:
    reasons = []
    if item.get("intent_score", 0) < 40:
        reasons.append("low intent match")
    if item.get("repository_score", 0) == 0:
        reasons.append("no repository evidence")
    if item.get("knowledge_score", 0) < 40:
        reasons.append("weak knowledge support")
    if not reasons:
        reasons.append(f"final score below threshold {threshold}")
    return f"{item.get('name')} rejected because {', '.join(reasons)}."
