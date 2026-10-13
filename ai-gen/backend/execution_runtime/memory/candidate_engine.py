"""Deterministic Engineering Memory candidate generation."""

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

REJECTED_STATUSES = {"blocked", "cancelled", "failed", "rejected", "timeout", "parse error", "parse_error"}
ELIGIBLE_STATUSES = {
    "Execution Result": {"completed", "passed", "success", "succeeded"},
    "Validation Result": {"approved", "completed", "passed", "ready"},
    "QA Result": {"approved", "completed", "passed", "ready", "ready for release", "ready with warnings"},
}
DEFAULT_POLICY = {
    "enabled": True,
    "minimumConfidence": 0.65,
    "minimumReuseScore": 0.55,
    "allowOrganizationScope": False,
    "organizationScopeMinimumConfidence": 0.85,
    "organizationScopeMinimumReuseScore": 0.8,
    "blockedCandidateTypes": [],
}


class MemoryCandidateGenerator:
    def generate(
        self,
        execution_result: dict[str, Any],
        validation_result: dict[str, Any],
        qa_result: dict[str, Any],
        engineering_diff: dict[str, Any],
        *,
        existing_memories: list[dict[str, Any]] | None = None,
        existing_candidates: list[dict[str, Any]] | None = None,
        policy: dict[str, Any] | None = None,
        project_id: str = "",
        organization_id: str = "",
    ) -> dict[str, Any]:
        _validate_inputs(execution_result, validation_result, qa_result, engineering_diff)
        active_policy = _policy(policy)
        lineage = _lineage(execution_result, validation_result, qa_result, engineering_diff)
        counts = {name: _change_count(engineering_diff.get(field)) for name, field in CHANGE_FIELDS.items()}
        evidence = _collect_evidence(execution_result, validation_result, qa_result, engineering_diff)
        proposals = _proposals(execution_result, validation_result, qa_result, engineering_diff, counts, evidence)
        known = [*(existing_memories or []), *(existing_candidates or [])]
        candidates: list[dict[str, Any]] = []

        for proposal in proposals:
            candidate = _candidate(
                proposal,
                lineage,
                active_policy,
                project_id=project_id or str(execution_result.get("projectId") or engineering_diff.get("projectId") or "default"),
                organization_id=organization_id,
                input_confidence=_input_confidence(execution_result, validation_result, qa_result, engineering_diff),
            )
            duplicate = _find_duplicate(candidate, [*known, *candidates])
            candidate["duplicateDetection"] = duplicate
            reasons = _rejection_reasons(candidate, execution_result, validation_result, qa_result, active_policy)
            if duplicate["isDuplicate"]:
                candidate["candidateId"] = f"{candidate['candidateId']}_duplicate_{stable_hash(duplicate)[:6]}"
                reasons.append(f"Duplicate of {duplicate['matchedId']}.")
            candidate["rejectionReasons"] = list(dict.fromkeys(reasons))
            candidate["policyDecision"]["allowed"] = not reasons
            candidate["policyDecision"]["reasons"] = deepcopy(candidate["rejectionReasons"])
            candidate["status"] = "Rejected" if reasons else "PendingApproval"
            candidate["approvalStatus"] = "Rejected" if reasons else "Pending"
            candidate["eventType"] = "MemoryCandidateRejected" if reasons else "MemoryCandidateCreated"
            candidates.append(candidate)

        return {
            "generationId": f"memory_candidate_generation_{stable_hash({'lineage': lineage, 'policy': active_policy})[:12]}",
            "generationVersion": "5.6",
            "status": "Completed",
            "candidates": candidates,
            "createdCandidates": [item["candidateId"] for item in candidates if item["status"] == "PendingApproval"],
            "rejectedCandidates": [item["candidateId"] for item in candidates if item["status"] == "Rejected"],
            "lineage": lineage,
            "policy": active_policy,
            "diagnostics": {
                "candidateCount": len(candidates),
                "createdCount": sum(item["status"] == "PendingApproval" for item in candidates),
                "rejectedCount": sum(item["status"] == "Rejected" for item in candidates),
                "memoryWrites": 0,
                "memoryIndexWrites": 0,
                "providerCalls": 0,
                "deterministic": True,
            },
            "generatedAt": _now(),
        }


def _validate_inputs(execution: Any, validation: Any, qa: Any, diff: Any) -> None:
    if not isinstance(execution, dict) or not str(execution.get("resultId") or execution.get("interpretationId") or ""):
        raise ValueError("executionResult with resultId is required.")
    if not isinstance(validation, dict) or not str(validation.get("reportId") or validation.get("validationId") or ""):
        raise ValueError("validationResult with reportId is required.")
    if not isinstance(qa, dict) or not str(qa.get("reportId") or qa.get("qaResultId") or qa.get("artifactId") or ""):
        raise ValueError("qaResult with reportId is required.")
    if not isinstance(diff, dict) or not str(diff.get("diffId") or ""):
        raise ValueError("engineeringDiff with diffId is required.")


def _policy(value: dict[str, Any] | None) -> dict[str, Any]:
    incoming = value if isinstance(value, dict) else {}
    policy = {**DEFAULT_POLICY, **incoming}
    policy["minimumConfidence"] = _score(policy["minimumConfidence"], 0.65)
    policy["minimumReuseScore"] = _score(policy["minimumReuseScore"], 0.55)
    policy["organizationScopeMinimumConfidence"] = _score(policy["organizationScopeMinimumConfidence"], 0.85)
    policy["organizationScopeMinimumReuseScore"] = _score(policy["organizationScopeMinimumReuseScore"], 0.8)
    policy["blockedCandidateTypes"] = _strings(policy.get("blockedCandidateTypes"))
    return policy


def _proposals(execution: dict[str, Any], validation: dict[str, Any], qa: dict[str, Any], diff: dict[str, Any], counts: dict[str, int], evidence: list[str]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    changed_names = _changed_names(diff)
    subject = changed_names[0] if changed_names else "engineering outcome"

    if counts["Architecture"]:
        proposals.append(_proposal("Architecture Decision", f"Architecture decision for {subject}", "Architecture Memory", 0.78, evidence))
    if _is_bug_fix(execution):
        proposals.append(_proposal("Bug Fix", f"Bug fix pattern for {subject}", "Execution Memory", 0.76, evidence))
    implementation_count = sum(counts[name] for name in ("API", "Module", "Service", "Dependency", "Security", "Configuration", "Database", "Refactoring"))
    if implementation_count:
        proposals.append(_proposal("Implementation Pattern", f"Implementation pattern for {subject}", "Pattern Memory", 0.82, evidence))
    if implementation_count >= 2 or _graph_change_count(diff.get("dependencyGraphChanges")):
        proposals.append(_proposal("Reusable Pattern", f"Reusable engineering pattern for {subject}", "Pattern Memory", 0.84, evidence))
    tests = _qa_tests(qa)
    if tests or counts["Test"]:
        test_evidence = [*_test_titles(tests), *evidence]
        proposals.append(_proposal("Reusable Test", f"Reusable test coverage for {subject}", "QA Memory", 0.86, test_evidence))
    lessons = _quality_notes(validation, qa, execution, diff)
    if lessons:
        proposals.append(_proposal("Lesson Learned", f"Lesson learned from {subject}", "Lessons Learned", 0.72, [*lessons, *evidence]))
    return proposals


def _proposal(candidate_type: str, title: str, category: str, reuse_score: float, evidence: list[str]) -> dict[str, Any]:
    selected = list(dict.fromkeys(_strings(evidence)))[:12]
    summary = selected[0] if selected else f"Validated {candidate_type.casefold()} candidate."
    return {"candidateType": candidate_type, "title": title, "summary": summary, "suggestedCategory": category, "reuseScore": reuse_score, "evidence": selected}


def _candidate(proposal: dict[str, Any], lineage: dict[str, str], policy: dict[str, Any], *, project_id: str, organization_id: str, input_confidence: float) -> dict[str, Any]:
    confidence = round(max(0.1, min(0.99, input_confidence + min(0.04, len(proposal["evidence"]) * 0.005))), 2)
    reuse_score = round(max(0.1, min(0.99, float(proposal["reuseScore"]) + min(0.05, len(proposal["evidence"]) * 0.005))), 2)
    organization_eligible = bool(
        policy["allowOrganizationScope"]
        and organization_id
        and confidence >= policy["organizationScopeMinimumConfidence"]
        and reuse_score >= policy["organizationScopeMinimumReuseScore"]
    )
    core = {"type": proposal["candidateType"], "title": proposal["title"], "lineage": lineage, "projectId": project_id}
    fingerprint = stable_hash({"type": proposal["candidateType"], "title": _key(proposal["title"]), "projectId": project_id, "evidence": sorted(_key(item) for item in proposal["evidence"])})
    return {
        "candidateId": f"memory_candidate_{stable_hash(core)[:12]}",
        "candidateVersion": "5.6",
        "candidateType": proposal["candidateType"],
        "title": proposal["title"],
        "summary": proposal["summary"],
        "content": {"evidence": deepcopy(proposal["evidence"]), "sourceLineage": deepcopy(lineage)},
        "confidence": confidence,
        "reuseScore": reuse_score,
        "suggestedCategory": proposal["suggestedCategory"],
        "projectScope": {"projectId": project_id, "eligible": True},
        "organizationScope": {
            "organizationId": organization_id,
            "eligible": organization_eligible,
            "reason": "Organization policy and quality thresholds passed." if organization_eligible else "Candidate remains project-scoped unless organization policy and quality thresholds pass.",
        },
        "approvalRequired": True,
        "stored": False,
        "indexed": False,
        "memoryId": "",
        "sourceLineage": deepcopy(lineage),
        "evidence": deepcopy(proposal["evidence"]),
        "candidateFingerprint": fingerprint,
        "policyDecision": {"allowed": True, "rules": deepcopy(policy)},
        "createdAt": _now(),
        "updatedAt": _now(),
    }


def _rejection_reasons(candidate: dict[str, Any], execution: dict[str, Any], validation: dict[str, Any], qa: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not policy["enabled"]:
        reasons.append("Engineering Memory candidate generation is disabled by organization policy.")
    if candidate["candidateType"] in policy["blockedCandidateTypes"]:
        reasons.append(f"{candidate['candidateType']} candidates are blocked by organization policy.")
    if candidate["confidence"] < policy["minimumConfidence"]:
        reasons.append(f"Confidence {candidate['confidence']:.2f} is below the required {policy['minimumConfidence']:.2f}.")
    if candidate["reuseScore"] < policy["minimumReuseScore"]:
        reasons.append(f"Reuse score {candidate['reuseScore']:.2f} is below the required {policy['minimumReuseScore']:.2f}.")
    for name, value in (("Execution Result", execution), ("Validation Result", validation), ("QA Result", qa)):
        status = _status(value)
        if status in REJECTED_STATUSES:
            reasons.append(f"{name} status is {status}; failed or rejected outcomes cannot become memory candidates.")
        elif status not in ELIGIBLE_STATUSES[name]:
            reasons.append(f"{name} status is {status or 'missing'}; only completed, approved, passed, or ready outcomes can become memory candidates.")
    return reasons


def _find_duplicate(candidate: dict[str, Any], known: list[dict[str, Any]]) -> dict[str, Any]:
    for item in known:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("candidateId") or item.get("id") or item.get("memoryId") or "existing-memory")
        if item.get("candidateFingerprint") == candidate["candidateFingerprint"]:
            return {"isDuplicate": True, "matchedId": item_id, "matchType": "fingerprint", "score": 1.0}
        same_title = _key(item.get("title")) == _key(candidate["title"])
        same_category = str(item.get("suggestedCategory") or item.get("category") or "") == candidate["suggestedCategory"]
        if same_title and same_category:
            return {"isDuplicate": True, "matchedId": item_id, "matchType": "title_and_category", "score": 0.95}
    return {"isDuplicate": False, "matchedId": "", "matchType": "none", "score": 0.0}


def _lineage(execution: dict[str, Any], validation: dict[str, Any], qa: dict[str, Any], diff: dict[str, Any]) -> dict[str, str]:
    return {
        "executionResultId": str(execution.get("resultId") or execution.get("interpretationId") or ""),
        "validationResultId": str(validation.get("reportId") or validation.get("validationId") or ""),
        "qaResultId": str(qa.get("reportId") or qa.get("qaResultId") or qa.get("artifactId") or ""),
        "engineeringDiffId": str(diff.get("diffId") or ""),
        "sessionId": str(execution.get("sessionId") or diff.get("sessionId") or ""),
        "correlationId": str(execution.get("correlationId") or validation.get("correlationId") or qa.get("correlationId") or ""),
    }


def _input_confidence(execution: dict[str, Any], validation: dict[str, Any], qa: dict[str, Any], diff: dict[str, Any]) -> float:
    values = [
        _score(execution.get("confidence"), 0.75),
        _score(validation.get("confidence"), 0.85),
        _score(qa.get("confidence") or qa.get("readinessScore") or qa.get("overallReadiness"), 0.82),
        _score(diff.get("confidence"), 0.8),
    ]
    return sum(values) / len(values)


def _collect_evidence(execution: dict[str, Any], validation: dict[str, Any], qa: dict[str, Any], diff: dict[str, Any]) -> list[str]:
    values = [
        *(diff.get("warnings") or []),
        *(validation.get("recommendations") or []),
        *(qa.get("recommendedActions") or qa.get("recommendations") or []),
        *_changed_names(diff),
        *_test_titles(_qa_tests(qa)),
    ]
    for artifact in execution.get("engineeringArtifacts") or execution.get("artifacts") or []:
        if isinstance(artifact, dict):
            values.extend(_strings(artifact.get("evidence")))
            values.extend(_strings(artifact.get("title") or artifact.get("path")))
    return list(dict.fromkeys(_strings(values)))


def _changed_names(diff: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in CHANGE_FIELDS.values():
        change = diff.get(field)
        if not isinstance(change, dict):
            continue
        for bucket in ("added", "modified", "removed", "moved"):
            for item in change.get(bucket) or []:
                if isinstance(item, dict):
                    values.extend(_strings(item.get("name") or (item.get("after") or {}).get("name") or (item.get("before") or {}).get("name")))
                else:
                    values.extend(_strings(item))
    return list(dict.fromkeys(values))


def _quality_notes(validation: dict[str, Any], qa: dict[str, Any], execution: dict[str, Any], diff: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys(_strings([
        *(validation.get("violations") or []),
        *(validation.get("recommendations") or []),
        *(validation.get("warnings") or []),
        *(qa.get("gaps") or qa.get("missingTests") or []),
        *(qa.get("recommendations") or qa.get("recommendedActions") or []),
        *(execution.get("warnings") or []),
        *(diff.get("warnings") or []),
    ])))


def _qa_tests(qa: dict[str, Any]) -> list[Any]:
    direct = qa.get("tests") or qa.get("testCases") or qa.get("generatedTests")
    if isinstance(direct, list):
        return direct
    intelligence = qa.get("testIntelligence")
    if isinstance(intelligence, dict):
        return intelligence.get("tests") or intelligence.get("testCases") or []
    return []


def _test_titles(tests: list[Any]) -> list[str]:
    values: list[str] = []
    for test in tests:
        values.extend(_strings(test.get("title") or test.get("name") or test.get("testId")) if isinstance(test, dict) else _strings(test))
    return values


def _is_bug_fix(execution: dict[str, Any]) -> bool:
    if "bug" in _status({"status": execution.get("responseType")}) or "fix" in _status({"status": execution.get("responseType")}):
        return True
    artifacts = execution.get("engineeringArtifacts") or execution.get("artifacts") or []
    return any(str(item.get("type") or "").casefold() == "bugfix" for item in artifacts if isinstance(item, dict))


def _change_count(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    return sum(len(value.get(bucket) or []) for bucket in ("added", "modified", "removed", "moved"))


def _graph_change_count(value: Any) -> int:
    return sum(len(item) for item in value.values() if isinstance(item, list)) if isinstance(value, dict) else 0


def _status(value: dict[str, Any]) -> str:
    return " ".join(str(value.get("status") or value.get("validationStatus") or value.get("readinessStatus") or value.get("releaseRecommendation") or "").replace("_", " ").split()).casefold()


def _score(value: Any, default: float) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return default
    if score > 1:
        score /= 100
    return max(0.0, min(1.0, score))


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = " ".join(value.split()).strip()
        return [text] if text else []
    if isinstance(value, dict):
        text = value.get("message") or value.get("reason") or value.get("title") or value.get("name") or value.get("path")
        return _strings(text)
    if isinstance(value, (list, tuple, set)):
        output: list[str] = []
        for item in value:
            output.extend(_strings(item))
        return output
    return _strings(str(value))


def _key(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
