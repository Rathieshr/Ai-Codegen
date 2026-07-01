"""Required test validation for implementation changes."""

from __future__ import annotations

from typing import Any

from .models import clean, lower_blob, score_from_results, violation


class TestCoverageValidator:
    def validate(self, execution_package: dict[str, Any], changed_files: list[dict[str, Any]], test_results: dict[str, Any] | None = None) -> dict[str, Any]:
        required = _required_tests(execution_package)
        test_files = [clean(file.get("path")) for file in changed_files if _is_test_file(clean(file.get("path")))]
        test_diffs = [clean(file.get("diff")) for file in changed_files if _is_test_file(clean(file.get("path")))]
        blob = lower_blob(*test_files, *test_diffs, (test_results or {}).get("summary", ""))
        results = []
        for test_type in required:
            keywords = _test_keywords(test_type)
            matched = [keyword for keyword in keywords if keyword in blob]
            if matched or any(keyword in clean(path).casefold() for path in test_files for keyword in keywords):
                status = "covered"
            elif test_results and (test_results.get("passed") or test_results.get("status") == "passed"):
                status = "partially covered"
            else:
                status = "missing"
            results.append({"testType": test_type, "status": status, "evidence": matched or test_files[:3]})
        violations = [
            violation(
                rule="test_coverage",
                severity="major",
                message=f"Required {item['testType']} evidence is {item['status']}.",
                recommendation="Add or run the required test coverage before approval.",
            )
            for item in results
            if item["status"] == "missing"
        ]
        return {"score": score_from_results(results, {"covered"}), "results": results, "violations": violations}


def _required_tests(execution_package: dict[str, Any]) -> list[str]:
    tests = execution_package.get("suggestedTests") if isinstance(execution_package.get("suggestedTests"), list) else []
    names = []
    for item in tests:
        if isinstance(item, dict):
            names.append(clean(item.get("testType") or item.get("category") or item.get("title")))
        else:
            names.append(clean(item))
    if not names:
        names = ["unit tests", "integration tests", "negative tests", "regression tests"]
    return list(dict.fromkeys([name for name in names if name]))


def _is_test_file(path: str) -> bool:
    lowered = path.casefold()
    return any(marker in lowered for marker in ["test", "spec", "__tests__", "/tests/"])


def _test_keywords(test_type: str) -> list[str]:
    lowered = clean(test_type).casefold()
    if "permission" in lowered or "auth" in lowered:
        return ["permission", "authorization", "role", "forbidden"]
    if "negative" in lowered or "error" in lowered:
        return ["negative", "invalid", "error", "missing"]
    if "integration" in lowered:
        return ["integration", "api", "repository"]
    if "regression" in lowered:
        return ["regression", "existing"]
    if "ui" in lowered:
        return ["ui", "screen", "component"]
    return ["unit", "test", "assert"]
