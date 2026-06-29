from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.intelligence.capability.capability_rules import CAPABILITY_PURPOSE_GROUPS


@dataclass(frozen=True)
class DuplicateRisk:
    existing_id: int | str | None
    existing_title: str
    risk: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "existingId": self.existing_id,
            "existingTitle": self.existing_title,
            "risk": self.risk,
            "confidence": self.confidence,
        }


class PlanningDuplicateDetector:
    def detect(
        self,
        work_item: dict[str, Any],
        selected_capabilities: list[dict[str, Any]],
        existing_children: list[dict[str, Any]],
    ) -> list[DuplicateRisk]:
        target_text = _text(work_item)
        target_tokens = _tokens(target_text)
        target_groups = _purpose_groups(target_text, selected_capabilities)
        risks: list[DuplicateRisk] = []
        for child in existing_children or []:
            child_text = _text(child)
            child_tokens = _tokens(child_text)
            overlap = _jaccard(target_tokens, child_tokens)
            shared_groups = target_groups.intersection(_purpose_groups(child_text, []))
            title_similar = _normalize(child.get("title")) == _normalize(work_item.get("title"))
            if title_similar or overlap >= 0.34 or shared_groups:
                confidence = max(0.72 if shared_groups else 0.0, min(0.95, overlap + (0.25 if title_similar else 0.0)))
                reason = "Potential duplicate child artifact"
                if shared_groups:
                    reason += f" with overlapping capability boundary: {', '.join(sorted(shared_groups))}"
                elif overlap >= 0.34:
                    reason += " with similar purpose and vocabulary"
                risks.append(DuplicateRisk(child.get("id") or child.get("workItemId"), str(child.get("title") or "Untitled"), reason, round(confidence, 2)))
        return risks


def summarize_existing_children(existing_children: list[dict[str, Any]], risks: list[DuplicateRisk]) -> list[dict[str, Any]]:
    risky_ids = {str(risk.existing_id): risk for risk in risks if risk.existing_id is not None}
    summaries = []
    for child in existing_children or []:
        child_id = child.get("id") or child.get("workItemId")
        risk = risky_ids.get(str(child_id))
        summaries.append(
            {
                "id": child_id,
                "type": str(child.get("type") or child.get("workItemType") or "Artifact"),
                "title": str(child.get("title") or "Untitled"),
                "purpose": str(child.get("description") or child.get("purpose") or "")[:240],
                "duplicateRisk": risk is not None,
                "reason": risk.risk if risk else "",
            }
        )
    return summaries


def _purpose_groups(text: str, selected_capabilities: list[dict[str, Any]]) -> set[str]:
    groups = set()
    names = [str(item.get("name") or "") for item in selected_capabilities]
    names.extend(CAPABILITY_PURPOSE_GROUPS.keys())
    lowered = text.lower()
    for capability, group in CAPABILITY_PURPOSE_GROUPS.items():
        cap_lower = capability.lower()
        if cap_lower in lowered or any(part in lowered for part in _tokens(cap_lower)) or capability in names:
            groups.add(group)
    return groups


def _text(item: dict[str, Any]) -> str:
    return " ".join(str(item.get(key) or "") for key in ["title", "description", "acceptanceCriteria", "acceptance_criteria", "purpose"]).lower()


def _tokens(text: str) -> set[str]:
    stop = {"with", "from", "that", "this", "into", "only", "and", "the", "for", "can", "able", "live"}
    return {token for token in re.findall(r"[a-z][a-z0-9]{3,}", text.lower()) if token not in stop}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a.intersection(b)) / len(a.union(b))


def _normalize(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))
