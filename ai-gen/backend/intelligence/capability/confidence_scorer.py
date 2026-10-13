from __future__ import annotations


DEFAULT_DISCOVERY_THRESHOLD = 70


def score_candidates(candidates: list[dict], threshold: int = DEFAULT_DISCOVERY_THRESHOLD) -> list[dict]:
    scored: list[dict] = []
    for candidate in candidates:
        overall = (
            candidate.get("intent_score", 0) * 0.22
            + candidate.get("keyword_score", 0) * 0.10
            + candidate.get("business_goal_score", 0) * 0.16
            + candidate.get("domain_expansion_score", 0) * 0.14
            + candidate.get("knowledge_score", 0) * 0.14
            + candidate.get("repository_score", 0) * 0.12
            + candidate.get("memory_score", 0) * 0.04
            + candidate.get("business_priority", 0) * 0.08
        )
        synergy = 0
        if candidate.get("intent_score", 0) >= 60 and candidate.get("knowledge_score", 0) >= 70:
            synergy += 6
        if candidate.get("business_goal_score", 0) >= 70 and candidate.get("repository_score", 0) >= 70:
            synergy += 5
        if candidate.get("domain_expansion_score", 0) >= 70 and candidate.get("business_goal_score", 0) >= 70:
            synergy += 6
        if candidate.get("repository_score", 0) >= 80 and candidate.get("knowledge_score", 0) >= 80:
            synergy += 4
        if candidate.get("keyword_score", 0) >= 75 and candidate.get("intent_score", 0) >= 60:
            synergy += 3
        if candidate.get("keyword_score", 0) >= 70 and candidate.get("business_goal_score", 0) >= 60:
            synergy += 4
        if candidate.get("keyword_score", 0) >= 55 and candidate.get("repository_score", 0) >= 80 and candidate.get("knowledge_score", 0) >= 80:
            synergy += 6
        if candidate.get("name") == "Reliability Analytics" and candidate.get("keyword_score", 0) >= 70:
            synergy += 9
        if candidate.get("name") == "Trend Analysis" and candidate.get("keyword_score", 0) >= 75:
            synergy += 5
        if candidate.get("name") == "Deployment" and candidate.get("keyword_score", 0) >= 65:
            synergy += 4
        if candidate.get("name") == "Device Management" and candidate.get("keyword_score", 0) >= 70:
            synergy += 5
        if candidate.get("classification") == "Business":
            synergy += 4
        elif candidate.get("classification") == "Analytics":
            synergy += 2
        overall = round(min(overall + synergy, 98))
        candidate["overall_score"] = overall
        candidate["confidence"] = round(min(overall / 100, 0.98), 2)
        candidate["accepted"] = overall >= threshold
        scored.append(candidate)
    return sorted(
        scored,
        key=lambda item: (
            item.get("overall_score", 0),
            item.get("business_priority", 0),
            item.get("intent_score", 0),
            item.get("knowledge_score", 0),
        ),
        reverse=True,
    )
