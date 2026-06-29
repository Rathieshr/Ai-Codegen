from __future__ import annotations

from typing import Any

from backend.intelligence.capability.capability_rules import canonical_capability


class DuplicateAnalyzer:
    def find_duplicate(self, title: str, description: str, existing_children: list[dict[str, Any]], threshold: float = 0.76) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        best_score = 0.0
        candidate = f"{title} {description}"
        candidate_capability = _capability_category(candidate)
        for child in existing_children:
            child_text = f"{child.get('title', '')} {child.get('purpose', '')} {child.get('description', '')}"
            child_capability = _capability_category(child_text)
            score = max(_similarity(candidate, child_text), _similarity(title, str(child.get("title") or "")))
            if candidate_capability and child_capability and candidate_capability == child_capability:
                score = max(score, 0.82)
            elif candidate_capability and child_capability and candidate_capability != child_capability:
                score = min(score, 0.66)
            if score > best_score:
                best_score = score
                best = child
        if best and best_score >= threshold:
            return {
                "id": best.get("id"),
                "type": best.get("type"),
                "title": best.get("title"),
                "confidence": round(best_score, 2),
                "reason": "Generated artifact is similar to an existing child artifact.",
            }
        return None


def _similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    return overlap / max(len(left_tokens), len(right_tokens))


def _capability_category(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["critical fault", "fault event", "fault detection", "fault monitoring", "severity"]):
        return canonical_capability("Fault Monitoring")
    if any(token in lowered for token in ["live operations", "operational awareness", "live status", "operations monitoring"]):
        return canonical_capability("Operational Awareness")
    if any(token in lowered for token in ["alert", "notification", "acknowledge", "escalation"]):
        return canonical_capability("Alert Management")
    if any(token in lowered for token in ["outage", "investigation", "root cause", "timeline"]):
        return canonical_capability("Outage Investigation")
    if any(token in lowered for token in ["analytics", "trend", "metric", "kpi", "reliability"]):
        return canonical_capability("Reliability Analytics")
    return ""


def _tokens(text: str) -> set[str]:
    stop = {"a", "an", "and", "for", "from", "in", "of", "the", "to", "with"}
    return {token for token in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if len(token) > 2 and token not in stop}
