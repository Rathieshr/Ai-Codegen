"""QA test gap analysis."""

from __future__ import annotations

from typing import Any

from .qa_validation_rules import category_for, clean, does_test_cover_criterion


class TestGapAnalyzer:
    def analyze(
        self,
        acceptance_criteria: list[str],
        tests: list[dict[str, Any]],
        validation_results: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        seen: set[str] = set()
        duplicates: list[str] = []
        weak: list[str] = []
        for test in tests:
            title = clean(test.get("title"))
            key = title.casefold()
            if key in seen:
                duplicates.append(title)
            seen.add(key)
            if len(test.get("steps") or []) < 2 or not clean(test.get("expected_result") or test.get("expected")):
                weak.append(title)
        untested = [criterion for criterion in acceptance_criteria if not any(does_test_cover_criterion(test, criterion) for test in tests)]
        categories = {category_for(test) for test in tests}
        missing_categories = [category for category in ["Functional", "Negative", "Permission", "Regression"] if category not in categories]
        return {
            "missingTests": [*missing_categories, *untested],
            "duplicateTests": duplicates,
            "weakTests": weak,
            "untestedAcceptanceCriteria": untested,
            "missingPermissionOrSecurity": "Permission" in missing_categories or any("permission" in item.lower() or "security" in item.lower() or "access" in item.lower() for item in untested),
            "validationGaps": _validation_gaps(validation_results or {}),
        }


def _validation_gaps(validation: dict[str, Any]) -> list[str]:
    gaps = []
    if validation.get("status") in {"Failed", "NeedsReview"}:
        gaps.append(f"Implementation validation status is {validation.get('status')}.")
    for violation in validation.get("violations") or []:
        if isinstance(violation, dict):
            gaps.append(clean(violation.get("message") or violation.get("description") or violation.get("type")))
    return [gap for gap in gaps if gap]
