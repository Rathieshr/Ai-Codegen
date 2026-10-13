from __future__ import annotations

from typing import Any

from .capability_context import CapabilityMatch, RejectedCapability
from .capability_rules import CAPABILITY_PURPOSE_GROUPS, canonical_capability


def build_recommendations(scored_candidates: list[dict[str, Any]], threshold: int, max_items: int = 6) -> dict[str, Any]:
    accepted = _select_diverse_candidates(scored_candidates, max_items=max_items)
    accepted_names = {str(item.get("name") or "") for item in accepted}
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
        "recommendedBusinessCapabilities": [],
        "supportingCapabilities": [],
        "relatedCapabilities": [],
        "recommendations": [
            {
                "name": item.get("name"),
                "classification": item.get("classification", "Supporting"),
                "intent": item.get("intent_score", 0),
                "keywords": item.get("keyword_score", 0),
                "businessGoal": item.get("business_goal_score", 0),
                "domainExpansion": item.get("domain_expansion_score", 0),
                "repository": item.get("repository_score", 0),
                "knowledge": item.get("knowledge_score", 0),
                "memory": item.get("memory_score", 0),
                "businessPriority": item.get("business_priority", 0),
                "final": item.get("overall_score", 0),
                "confidence": item.get("confidence", 0),
                "accepted": str(item.get("name") or "") in accepted_names,
                "band": _confidence_band(int(item.get("overall_score", 0))),
                "reason": _reason(item),
                "evidence": _evidence(item),
            }
            for item in scored_candidates
        ],
    }
    for item in report["recommendations"]:
        classification = str(item.get("classification") or "Supporting")
        if item.get("accepted") and classification == "Business":
            report["recommendedBusinessCapabilities"].append(item)
        elif item.get("accepted") and item.get("final", 0) >= 75:
            report["supportingCapabilities"].append(item)
        else:
            report["relatedCapabilities"].append(item)
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
    classification = str(item.get("classification") or "Supporting").lower()
    if classification == "business":
        fragments.append("business capability reasoning")
    elif classification == "analytics":
        fragments.append("analytics intent")
    elif classification == "security":
        fragments.append("security intent")
    if item.get("business_goal_score", 0) >= 70:
        fragments.append("business goal")
    if item.get("domain_expansion_score", 0) >= 70:
        fragments.append("domain expansion")
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


def _confidence_band(score: int) -> str:
    if score >= 95:
        return "Core Capability"
    if score >= 85:
        return "Recommended"
    if score >= 75:
        return "Supporting"
    return "Related Capability"


def _select_diverse_candidates(scored_candidates: list[dict[str, Any]], max_items: int) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    seen_purposes: dict[str, str] = {}
    for item in scored_candidates:
        if not item.get("accepted"):
            continue
        name = str(item.get("name") or "")
        canonical = canonical_capability(name)
        purpose = CAPABILITY_PURPOSE_GROUPS.get(canonical, canonical)
        existing = seen_purposes.get(purpose)
        if existing and _can_share_purpose(existing, name):
            continue
        accepted.append(item)
        seen_purposes[purpose] = name
        if len(accepted) >= max_items:
            break
    return accepted


def _can_share_purpose(existing: str, candidate: str) -> bool:
    allowed_pairs = [
        {"Authentication", "Authorization"},
        {"Alert Management", "Notification Management"},
    ]
    return {existing, candidate} not in allowed_pairs
