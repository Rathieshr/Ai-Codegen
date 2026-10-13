"""Acceptance coverage mapping."""

from __future__ import annotations

from typing import Any

from .qa_validation_rules import (
    STATUS_COVERED,
    STATUS_MISSING,
    STATUS_NOT_VERIFIABLE,
    STATUS_PARTIAL,
    clean,
    criterion_is_verifiable,
    does_test_cover_criterion,
)


class AcceptanceCoverageEngine:
    def analyze(
        self,
        acceptance_criteria: list[str],
        tests: list[dict[str, Any]],
        validation_results: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        covered_count = 0
        partial_count = 0
        missing: list[str] = []
        for index, criterion in enumerate(acceptance_criteria, start=1):
            mapped = [test for test in tests if does_test_cover_criterion(test, criterion)]
            verifiable = criterion_is_verifiable(criterion)
            if not verifiable and not mapped:
                status = STATUS_NOT_VERIFIABLE
            elif len(mapped) >= 2:
                status = STATUS_COVERED
                covered_count += 1
            elif len(mapped) == 1:
                status = STATUS_PARTIAL
                partial_count += 1
            else:
                status = STATUS_MISSING
                missing.append(criterion)
            items.append(
                {
                    "acceptanceCriteriaId": f"AC{index:03d}",
                    "acceptanceText": criterion,
                    "coverageStatus": status,
                    "mappedTests": [_test_ref(test) for test in mapped],
                    "validation": _validation_note(status, mapped, validation_results or {}),
                }
            )
        total = len(acceptance_criteria)
        coverage_percent = int(round(((covered_count + partial_count * 0.5) / total) * 100)) if total else 0
        return {
            "coveragePercent": coverage_percent,
            "coveredCount": covered_count,
            "partiallyCoveredCount": partial_count,
            "missingCount": len(missing),
            "missingCoverage": missing,
            "acceptanceCriteria": items,
            "validationNotes": _summary_notes(items),
        }


def _test_ref(test: dict[str, Any]) -> dict[str, Any]:
    return {
        "testId": clean(test.get("test_id") or test.get("testId")),
        "title": clean(test.get("title")),
        "category": clean(test.get("category")),
    }


def _validation_note(status: str, mapped: list[dict[str, Any]], validation_results: dict[str, Any]) -> str:
    if status == STATUS_COVERED:
        return "Covered by multiple verification paths."
    if status == STATUS_PARTIAL:
        return "Partially covered; add one stronger verification path."
    if status == STATUS_NOT_VERIFIABLE:
        return "Acceptance criterion is not objectively verifiable."
    if validation_results.get("status") in {"Failed", "NeedsReview"}:
        return "Missing verification and implementation validation needs review."
    return "No mapped test found."


def _summary_notes(items: list[dict[str, Any]]) -> list[str]:
    notes = []
    for item in items:
        if item["coverageStatus"] != STATUS_COVERED:
            notes.append(f"{item['acceptanceCriteriaId']}: {item['coverageStatus']} - {item['acceptanceText']}")
    return notes
