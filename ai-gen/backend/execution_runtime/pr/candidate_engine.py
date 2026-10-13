"""Deterministic Pull Request candidate projection."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.token_intelligence.models import stable_hash


CHANGE_FIELDS = {
    "API": "apiChanges",
    "Module": "moduleChanges",
    "Service": "serviceChanges",
    "Dependency": "dependencyChanges",
    "Architecture": "architectureChanges",
    "Test": "testChanges",
    "Security": "securityChanges",
    "Configuration": "configurationChanges",
    "Database": "databaseChanges",
    "Documentation": "documentationChanges",
    "Refactoring": "refactoringChanges",
    "BreakingChange": "breakingChanges",
}


class PRCandidateGenerator:
    def generate(
        self,
        engineering_diff: dict[str, Any],
        validation_result: dict[str, Any],
        qa_result: dict[str, Any],
        execution_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        _validate_inputs(engineering_diff, validation_result, qa_result, execution_manifest)
        counts = {name: _change_count(engineering_diff.get(field)) for name, field in CHANGE_FIELDS.items()}
        total_changes = sum(counts.values()) + _graph_change_count(engineering_diff.get("dependencyGraphChanges"))
        change_kind = _change_kind(engineering_diff, execution_manifest, counts, total_changes)
        files = _files_changed(engineering_diff)
        modules = _modules(engineering_diff)
        acceptance = _acceptance_coverage(validation_result, qa_result, execution_manifest)
        risks = _risks(engineering_diff, validation_result, qa_result, execution_manifest)
        breaking = _change_records(engineering_diff.get("breakingChanges"))
        migration_notes = _migration_notes(engineering_diff)
        testing = _testing_summary(validation_result, qa_result, counts)
        architecture_notes = _architecture_notes(engineering_diff)
        release_notes = _release_notes(change_kind, counts, total_changes, engineering_diff)
        confidence, warnings = _confidence(engineering_diff, validation_result, qa_result, execution_manifest, files, total_changes)
        status = _status(validation_result, qa_result, acceptance)
        lineage = _lineage(engineering_diff, validation_result, qa_result, execution_manifest)
        core = {"lineage": lineage, "kind": change_kind, "files": files, "acceptance": acceptance}

        return {
            "candidateId": f"pr_candidate_{stable_hash(core)[:12]}",
            "candidateVersion": "5.7",
            "status": status,
            "candidateType": change_kind,
            "summary": _summary(change_kind, execution_manifest, total_changes, modules),
            "filesChanged": files,
            "modules": modules,
            "acceptanceCoverage": acceptance,
            "risks": risks,
            "breakingChanges": breaking,
            "migrationNotes": migration_notes,
            "testingSummary": testing,
            "architectureNotes": architecture_notes,
            "releaseNotes": release_notes,
            "confidence": confidence,
            "warnings": warnings,
            "sourceLineage": lineage,
            "created": False,
            "pullRequestId": "",
            "eventType": "PRCandidateCreated",
            "diagnostics": {
                "totalSemanticChanges": total_changes,
                "changeCounts": counts,
                "gitOperations": 0,
                "repositoryWrites": 0,
                "azureDevOpsWrites": 0,
                "pullRequestsCreated": 0,
                "providerCalls": 0,
                "deterministic": True,
            },
            "generatedAt": _now(),
        }


def _validate_inputs(diff: Any, validation: Any, qa: Any, manifest: Any) -> None:
    if not isinstance(diff, dict) or not str(diff.get("diffId") or ""):
        raise ValueError("engineeringDiff with diffId is required.")
    if not isinstance(validation, dict) or not str(validation.get("reportId") or validation.get("validationId") or ""):
        raise ValueError("validationResult with reportId is required.")
    if not isinstance(qa, dict) or not str(qa.get("reportId") or qa.get("qaResultId") or qa.get("artifactId") or ""):
        raise ValueError("qaResult with reportId is required.")
    if not isinstance(manifest, dict) or not str(manifest.get("manifestId") or ""):
        raise ValueError("executionManifest with manifestId is required.")


def _change_kind(diff: dict[str, Any], manifest: dict[str, Any], counts: dict[str, int], total: int) -> str:
    non_docs = sum(value for name, value in counts.items() if name != "Documentation")
    if counts["Documentation"] and not non_docs:
        return "Documentation"
    mode = " ".join(_strings((manifest.get("implementationGuidance") or {}).get("executionMode") if isinstance(manifest.get("implementationGuidance"), dict) else "")).casefold()
    objective = _text(manifest.get("objective")).casefold()
    if counts["Refactoring"] or "refactor" in mode or "refactor" in objective:
        return "Refactor"
    if "bug" in mode or "bug fix" in objective or "fix " in objective:
        return "Bug Fix"
    impact = _text((diff.get("impact") or {}).get("level")).casefold()
    if total >= 8 or impact in {"high", "critical"}:
        return "Large Feature"
    return "Small Change"


def _files_changed(diff: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for category, field in CHANGE_FIELDS.items():
        value = diff.get(field)
        if not isinstance(value, dict):
            continue
        for bucket in ("added", "modified", "removed", "moved"):
            for item in value.get(bucket) or []:
                if not isinstance(item, dict):
                    continue
                before = item.get("before") if isinstance(item.get("before"), dict) else {}
                after = item.get("after") if isinstance(item.get("after"), dict) else {}
                path = _text(after.get("path") or before.get("path") or item.get("path"))
                if not _looks_like_path(path):
                    continue
                change_type = _text(item.get("changeType") or bucket.title())
                key = (path.casefold(), change_type.casefold())
                if key in seen:
                    continue
                seen.add(key)
                output.append({
                    "path": path,
                    "changeType": change_type,
                    "category": category,
                    "confidence": _score(item.get("confidence"), 0.75),
                    "reason": _text(item.get("reason") or f"Reported by Engineering Diff {field}."),
                    "evidence": _strings(item.get("evidence")),
                })
    return sorted(output, key=lambda item: (item["path"].casefold(), item["changeType"]))


def _modules(diff: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    changes = diff.get("moduleChanges")
    if not isinstance(changes, dict):
        return output
    for bucket in ("added", "modified", "removed", "moved"):
        for item in changes.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            before = item.get("before") if isinstance(item.get("before"), dict) else {}
            after = item.get("after") if isinstance(item.get("after"), dict) else {}
            name = _text(item.get("name") or after.get("name") or before.get("name"))
            if not name or name.casefold() in seen:
                continue
            seen.add(name.casefold())
            output.append({"name": name, "changeType": _text(item.get("changeType") or bucket.title()), "confidence": _score(item.get("confidence"), 0.75)})
    return output


def _acceptance_coverage(validation: dict[str, Any], qa: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    criteria = manifest.get("acceptanceCriteria") if isinstance(manifest.get("acceptanceCriteria"), list) else []
    results = validation.get("acceptanceResults") if isinstance(validation.get("acceptanceResults"), list) else []
    mapped: list[dict[str, Any]] = []
    for index, criterion in enumerate(criteria):
        criterion_id = _criterion_id(criterion, index)
        text = _criterion_text(criterion)
        result = next((item for item in results if _text(item.get("acceptanceCriteriaId") or item.get("id")) == criterion_id), None)
        if result is None and index < len(results):
            result = results[index]
        mapped.append({
            "acceptanceCriteriaId": criterion_id,
            "acceptanceText": text,
            "status": _text((result or {}).get("status") or "Not Verifiable"),
            "evidence": _strings((result or {}).get("evidence") or (result or {}).get("notes")),
        })
    score = _numeric_score(
        validation.get("acceptanceCoverageScore"),
        (qa.get("acceptanceCoverage") or {}).get("coverageScore") if isinstance(qa.get("acceptanceCoverage"), dict) else qa.get("acceptanceCoverageScore"),
    )
    if score is None and mapped:
        covered = sum(item["status"].casefold() in {"covered", "implemented", "passed", "verified"} for item in mapped)
        partial = sum("partial" in item["status"].casefold() for item in mapped)
        score = round((covered + partial * 0.5) / len(mapped) * 100)
    score = int(score or 0)
    return {
        "score": score,
        "status": "Covered" if score >= 80 else "Partially Covered" if score > 0 else "Not Covered",
        "criteria": mapped,
        "total": len(criteria),
        "covered": sum(item["status"].casefold() in {"covered", "implemented", "passed", "verified"} for item in mapped),
        "missing": sum(item["status"].casefold() in {"missing", "not covered", "not verifiable"} for item in mapped),
    }


def _risks(diff: dict[str, Any], validation: dict[str, Any], qa: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    values = [
        *(manifest.get("risks") or []),
        *(validation.get("violations") or []),
        *(validation.get("warnings") or []),
        *(qa.get("risks") or qa.get("riskItems") or []),
        *((diff.get("impact") or {}).get("reasons") or []),
    ]
    return list(dict.fromkeys(_strings(values)))


def _migration_notes(diff: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    for label, field in (("Database", "databaseChanges"), ("Configuration", "configurationChanges")):
        for item in _change_records(diff.get(field)):
            name = _text(item.get("name") or (item.get("after") or {}).get("name") or (item.get("before") or {}).get("name"))
            notes.append(f"{label} {item.get('changeType', 'change')}: {name}." if name else f"{label} migration or rollout review is required.")
    return list(dict.fromkeys(notes))


def _testing_summary(validation: dict[str, Any], qa: dict[str, Any], counts: dict[str, int]) -> dict[str, Any]:
    tests = qa.get("tests") or qa.get("testCases") or qa.get("generatedTests") or []
    if not isinstance(tests, list):
        tests = []
    missing = qa.get("missingTests") or qa.get("gaps") or []
    categories = list(dict.fromkeys(_text(item.get("category") or item.get("type")) for item in tests if isinstance(item, dict) and _text(item.get("category") or item.get("type"))))
    return {
        "qaStatus": _text(qa.get("status") or qa.get("readinessStatus") or qa.get("releaseRecommendation")),
        "testCoverageScore": int(_numeric_score(validation.get("testCoverageScore"), qa.get("testCompleteness"), qa.get("coverageScore")) or 0),
        "testCount": len(tests),
        "changedTestArtifacts": counts["Test"],
        "categories": categories,
        "missingTests": _strings(missing),
        "summary": f"{len(tests)} QA test case(s) available; {len(_strings(missing))} missing-test item(s) remain.",
    }


def _architecture_notes(diff: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for item in _change_records(diff.get("architectureChanges")):
        values.extend(_strings(item.get("reason") or item.get("name") or (item.get("after") or {}).get("name")))
    return list(dict.fromkeys(values))


def _release_notes(kind: str, counts: dict[str, int], total: int, diff: dict[str, Any]) -> list[str]:
    notes = [f"{kind}: {total} semantic engineering change(s)."]
    labels = {
        "API": "API",
        "Module": "module",
        "Service": "service",
        "Architecture": "architecture",
        "Database": "database",
        "Configuration": "configuration",
        "Documentation": "documentation",
        "Refactoring": "refactoring",
        "BreakingChange": "breaking",
    }
    for name, label in labels.items():
        if counts[name]:
            notes.append(f"Includes {counts[name]} {label} change(s).")
    summary = diff.get("summary")
    if isinstance(summary, str) and summary.strip():
        notes.append(_text(summary))
    return notes


def _summary(kind: str, manifest: dict[str, Any], total: int, modules: list[dict[str, Any]]) -> dict[str, Any]:
    objective = _text(manifest.get("objective") or manifest.get("businessGoal") or "Engineering change")
    module_names = [item["name"] for item in modules]
    return {
        "title": objective,
        "description": f"{kind} candidate covering {total} semantic change(s).",
        "changeType": kind,
        "businessGoal": _text(manifest.get("businessGoal")),
        "moduleSummary": ", ".join(module_names),
    }


def _confidence(diff: dict[str, Any], validation: dict[str, Any], qa: dict[str, Any], manifest: dict[str, Any], files: list[dict[str, Any]], total: int) -> tuple[float, list[str]]:
    values = [
        _score(diff.get("confidence"), 0.75),
        _score(validation.get("confidence"), 0.82),
        _score(qa.get("confidence") or qa.get("readinessScore"), 0.8),
        _score(manifest.get("confidence"), 0.8),
    ]
    warnings: list[str] = []
    confidence = sum(values) / len(values)
    if total and not files:
        warnings.append("Engineering Diff contains semantic changes but no changed file paths.")
        confidence -= 0.08
    if _state(validation) in {"blocked", "failed", "rejected"}:
        warnings.append("Validation did not pass; PR candidate requires review.")
        confidence -= 0.15
    if _state(qa) in {"blocked", "failed", "needs review", "needs more testing"}:
        warnings.append("QA is not release-ready; PR candidate requires review.")
        confidence -= 0.12
    return round(max(0.1, min(0.99, confidence)), 2), warnings


def _status(validation: dict[str, Any], qa: dict[str, Any], acceptance: dict[str, Any]) -> str:
    if _state(validation) in {"blocked", "failed", "rejected"} or _state(qa) in {"blocked", "failed"}:
        return "Blocked"
    if acceptance["score"] < 80 or _state(qa) in {"needs review", "needs more testing", "ready with warnings"}:
        return "NeedsReview"
    return "Draft"


def _lineage(diff: dict[str, Any], validation: dict[str, Any], qa: dict[str, Any], manifest: dict[str, Any]) -> dict[str, str]:
    return {
        "engineeringDiffId": str(diff.get("diffId") or ""),
        "validationResultId": str(validation.get("reportId") or validation.get("validationId") or ""),
        "qaResultId": str(qa.get("reportId") or qa.get("qaResultId") or qa.get("artifactId") or ""),
        "executionManifestId": str(manifest.get("manifestId") or ""),
        "executionPackageId": str(manifest.get("sourcePackageId") or ""),
        "repositorySnapshotVersion": str((manifest.get("sourceVersions") or {}).get("repositorySnapshotVersion") or ""),
        "sessionId": str(diff.get("sessionId") or validation.get("sessionId") or ""),
        "correlationId": str(validation.get("correlationId") or qa.get("correlationId") or diff.get("correlationId") or ""),
    }


def _change_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    return [deepcopy(item) for bucket in ("added", "modified", "removed", "moved") for item in value.get(bucket) or [] if isinstance(item, dict)]


def _change_count(value: Any) -> int:
    return len(_change_records(value))


def _graph_change_count(value: Any) -> int:
    return sum(len(item) for item in value.values() if isinstance(item, list)) if isinstance(value, dict) else 0


def _criterion_id(value: Any, index: int) -> str:
    if isinstance(value, dict):
        return _text(value.get("acceptanceCriteriaId") or value.get("id") or value.get("key") or f"AC-{index + 1}")
    return f"AC-{index + 1}"


def _criterion_text(value: Any) -> str:
    return _text(value.get("acceptanceText") or value.get("text") or value.get("description")) if isinstance(value, dict) else _text(value)


def _looks_like_path(value: str) -> bool:
    if not value:
        return False
    leaf = value.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return "/" in value or "\\" in value or "." in leaf


def _numeric_score(*values: Any) -> float | None:
    for value in values:
        try:
            score = float(value)
        except (TypeError, ValueError):
            continue
        return score * 100 if 0 <= score <= 1 else max(0, min(100, score))
    return None


def _score(value: Any, default: float) -> float:
    score = _numeric_score(value)
    return default if score is None else score / 100


def _state(value: dict[str, Any]) -> str:
    return _text(value.get("status") or value.get("validationStatus") or value.get("readinessStatus") or value.get("releaseRecommendation")).casefold()


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_text(value)] if _text(value) else []
    if isinstance(value, dict):
        return _strings(value.get("message") or value.get("reason") or value.get("risk") or value.get("title") or value.get("name") or value.get("path"))
    if isinstance(value, (list, tuple, set)):
        output: list[str] = []
        for item in value:
            output.extend(_strings(item))
        return output
    return _strings(str(value))


def _text(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
