"""Deterministic quality gates used by the hardening harness and package builder."""

from __future__ import annotations

import re
from typing import Any


TESTABLE_TERMS = {
    "can", "must", "shows", "displays", "returns", "rejects", "prevents", "records",
    "loads", "completes", "receives", "allows", "requires", "within", "when", "if",
}


def validate_acceptance_criteria(criteria: list[str], implementation_areas: list[str] | None = None) -> dict[str, Any]:
    areas = [str(item).strip() for item in (implementation_areas or []) if str(item).strip()]
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    for index, raw in enumerate(criteria or [], 1):
        text = " ".join(str(raw or "").split()).strip()
        normalized = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
        issues: list[str] = []
        if not text or len(text.split()) < 4:
            issues.append("fragment")
        if re.match(r"^(and|or)\b", text, flags=re.IGNORECASE):
            issues.append("leading_conjunction")
        if normalized in seen:
            issues.append("duplicate")
        seen.add(normalized)
        words = set(normalized.split())
        if not words.intersection(TESTABLE_TERMS):
            issues.append("not_testable")
        if text.count(" and ") >= 3 or text.count("; ") >= 2:
            issues.append("multiple_unrelated_conditions")
        implementation_area = areas[min(index - 1, len(areas) - 1)] if areas else ""
        validation_expectation = f"Verify that {text[0].lower() + text[1:] if text else 'the criterion is satisfied'}"
        if not implementation_area:
            issues.append("missing_implementation_area")
        status = "Rejected" if any(issue in {"fragment", "leading_conjunction", "duplicate"} for issue in issues) else "NeedsReview" if issues else "Approved"
        results.append({
            "acceptanceCriteriaId": f"AC{index:03d}",
            "acceptanceText": text,
            "implementationArea": implementation_area,
            "validationExpectation": validation_expectation,
            "status": status,
            "issues": issues,
        })
        if status == "Rejected":
            blockers.append(f"AC{index:03d} failed acceptance quality: {', '.join(issues)}.")
        elif status == "NeedsReview":
            warnings.append(f"AC{index:03d} needs review: {', '.join(issues)}.")
    if not criteria:
        blockers.append("Acceptance criteria are required.")
    overall = "Rejected" if blockers else "NeedsReview" if warnings else "Approved"
    score = round(sum(1 for item in results if item["status"] == "Approved") / len(results) * 100) if results else 0
    return {"status": overall, "score": score, "criteria": results, "blockers": blockers, "warnings": warnings}
