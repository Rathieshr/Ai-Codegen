"""Acceptance criteria coverage checks."""

from __future__ import annotations

from typing import Any

from .models import clean, lower_blob, score_from_results, violation


class AcceptanceCoverageValidator:
    def validate(self, execution_package: dict[str, Any], changed_files: list[dict[str, Any]]) -> dict[str, Any]:
        mappings = execution_package.get("acceptanceMapping") if isinstance(execution_package.get("acceptanceMapping"), list) else []
        if not mappings:
            return {
                "score": 0,
                "results": [],
                "violations": [
                    violation(
                        rule="acceptance_criteria_missing",
                        severity="critical",
                        message="Execution Package has no acceptance criteria mapping to validate.",
                        recommendation="Regenerate or repair the Execution Package before implementation validation.",
                    )
                ],
            }
        changed_blob = lower_blob(*[file.get("diff") for file in changed_files])
        results: list[dict[str, Any]] = []
        for index, mapping in enumerate(mappings, start=1):
            ac_text = clean(mapping.get("acceptanceText") or mapping.get("acceptance_criterion") or mapping.get("acceptanceCriteria") or mapping.get("acceptanceCriteriaId"))
            implementation = clean(mapping.get("implementationArea") or mapping.get("implementation_task") or mapping.get("implementation"))
            validation_expectation = clean(mapping.get("validationExpectation") or mapping.get("validation"))
            tokens = _keywords(ac_text, implementation)
            matched = [token for token in tokens if token.casefold() in changed_blob]
            if not changed_files:
                status = "not verifiable"
            elif len(matched) >= max(1, min(3, len(tokens))):
                status = "implemented"
            elif matched:
                status = "partially implemented"
            else:
                status = "missing"
            results.append(
                {
                    "acceptanceCriteriaId": clean(mapping.get("acceptanceCriteriaId")) or f"AC{index}",
                    "acceptanceText": ac_text,
                    "implementationArea": implementation,
                    "validationExpectation": validation_expectation,
                    "status": status,
                    "evidence": matched,
                }
            )
        violations = []
        for result in results:
            if result["status"] in {"missing", "not verifiable"}:
                violations.append(
                    violation(
                        rule="acceptance_criteria_coverage",
                        severity="major" if result["status"] == "missing" else "minor",
                        message=f"{result['acceptanceCriteriaId']} is {result['status']}.",
                        recommendation="Map a changed file, implementation note, or test to this acceptance criterion.",
                    )
                )
        return {
            "score": score_from_results(results, {"implemented"}),
            "results": results,
            "violations": violations,
        }


def _keywords(*values: str) -> list[str]:
    stop = {"user", "can", "the", "and", "with", "from", "that", "this", "into", "when", "then", "shall", "should"}
    words: list[str] = []
    for value in values:
        for raw in clean(value).replace("/", " ").replace("_", " ").replace("-", " ").split():
            token = "".join(ch for ch in raw if ch.isalnum())
            if len(token) >= 4 and token.casefold() not in stop:
                words.append(token)
    seen: set[str] = set()
    result: list[str] = []
    for word in words:
        key = word.casefold()
        if key not in seen:
            seen.add(key)
            result.append(word)
    return result[:10]
