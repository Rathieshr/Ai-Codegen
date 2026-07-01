"""Deterministic Execution Package V2 builder.

Execution Package V2 is intentionally deterministic-first: it consumes the
already-selected Context Capsule and DNA lineage instead of rebuilding broad
project context or asking a model to rediscover intent.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


FILE_RANKING_UNAVAILABLE = "Repository file ranking not available"


def build_execution_package_v2(
    *,
    story: dict[str, Any],
    selected_task: dict[str, Any] | None,
    acceptance_criteria: list[str],
    context_capsule: dict[str, Any],
    generated_tasks: list[dict[str, Any]] | None = None,
    task_plan: dict[str, Any] | None = None,
    readiness: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    validation_report: dict[str, Any] | None = None,
    ai_enrichment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a developer-ready execution package from a Context Capsule."""

    story = story or {}
    selected_task = selected_task or {}
    generated_tasks = generated_tasks or []
    task_plan = task_plan or {}
    readiness = readiness or {}
    profile = profile or {}
    validation_report = validation_report or {}
    capsule = context_capsule or {}
    dna = capsule.get("workItemDNA") if isinstance(capsule.get("workItemDNA"), dict) else {}
    dna_summary = _dna_summary(dna)
    generated_at = _now_iso()

    artifact_type = _artifact_type(story, selected_task)
    artifact_id = _item_id(selected_task) if artifact_type == "Task" else _item_id(story)
    task_id = _item_id(selected_task) if artifact_type == "Task" else None
    story_id = _item_id(story) or capsule.get("parentStoryId")
    feature_id = _lineage_id(story, selected_task, dna, "feature")
    epic_id = _lineage_id(story, selected_task, dna, "epic")
    package_seed = {
        "artifact": artifact_id,
        "artifactType": artifact_type,
        "task": task_id,
        "story": story_id,
        "capsule": capsule.get("capsuleId"),
        "dna": capsule.get("dnaId") or dna.get("dnaId"),
        "knowledge": capsule.get("knowledgeVersion"),
    }
    package_id = f"execpkg_{_stable_hash(package_seed)[:12]}"

    modules = _string_list(capsule.get("selectedModules"))
    flows = _string_list(capsule.get("selectedFlows"))
    dependencies = _string_list(capsule.get("selectedDependencies"))
    standards = _string_list(capsule.get("selectedStandards"))
    applications = _string_list(capsule.get("selectedApplications"))
    rejected_context = [item for item in capsule.get("rejectedContext", []) if isinstance(item, dict)]
    relevant_files = _repository_items(capsule.get("relevantFiles"), item_type="file")

    repository_context = {
        "relevantModules": _repository_items(modules, item_type="module", source="context_capsule"),
        "relevantFlows": _repository_items(flows, item_type="flow", source="context_capsule"),
        "relevantServices": _repository_named_items(profile, "services"),
        "relevantAPIs": _repository_named_items(profile, "apis"),
        "relevantFiles": relevant_files,
        "relatedTests": _repository_named_items(profile, "tests"),
        "dependencies": _repository_items(dependencies, item_type="dependency", source="context_capsule"),
        "fileRankingStatus": _clean(capsule.get("fileRankingStatus")) or FILE_RANKING_UNAVAILABLE,
    }
    if not relevant_files:
        repository_context["fileRankingStatus"] = FILE_RANKING_UNAVAILABLE

    acceptance_mapping = _acceptance_mapping(
        acceptance_criteria or _string_list(capsule.get("acceptanceCriteria")),
        selected_task,
        generated_tasks,
        modules,
        flows,
    )
    risks = _execution_risks(capsule, validation_report)
    engineering_rules = _engineering_rules(profile, standards, modules, flows)
    suggested_tests = _suggested_tests(story, selected_task, acceptance_mapping, modules, flows, risks)
    readiness_payload = _readiness(
        readiness,
        acceptance_mapping,
        repository_context,
        capsule,
        validation_report,
    )

    package = {
        "packageId": package_id,
        "artifactId": artifact_id,
        "artifactType": artifact_type,
        "taskId": task_id,
        "storyId": story_id,
        "featureId": feature_id,
        "epicId": epic_id,
        "dnaVersion": capsule.get("dnaVersion") or dna.get("version") or 1,
        "knowledgeVersion": _clean(capsule.get("knowledgeVersion")),
        "repositorySnapshotVersion": _clean(capsule.get("repositorySnapshotVersion")),
        "generatedAt": generated_at,
        "businessContext": {
            "epicBusinessGoal": _first(dna_summary.get("businessGoals")) or _clean(story.get("epic_business_goal")),
            "featureCapability": dna_summary.get("capability") or _first(capsule.get("selectedCapabilities")),
            "storyTitle": _clean(story.get("title")),
            "storyUserGoal": _story_goal(story, dna_summary),
            "taskObjective": _task_objective(selected_task, story),
            "businessValue": dna_summary.get("businessOutcome") or _clean(story.get("business_value")),
        },
        "engineeringDNA": {
            "dnaId": capsule.get("dnaId") or dna.get("dnaId"),
            "dnaVersion": capsule.get("dnaVersion") or dna.get("version") or 1,
            "capability": dna_summary.get("capability") or _first(capsule.get("selectedCapabilities")),
            "responsibilities": _string_list(dna.get("responsibilities")) if isinstance(dna, dict) else [],
            "inScope": _string_list(capsule.get("inScope")),
            "outOfScope": _string_list(capsule.get("outOfScope")),
            "repositoryEvidence": {
                "modules": modules,
                "flows": flows,
                "files": [item.get("name") for item in relevant_files],
            },
        },
        "implementationBoundary": {
            "inScope": _string_list(capsule.get("inScope")) or _default_scope(modules, flows),
            "outOfScope": _string_list(capsule.get("outOfScope")),
            "allowedModules": modules,
            "blockedModules": _rejected_names(rejected_context, "module"),
            "allowedFlows": flows,
            "blockedFlows": _rejected_names(rejected_context, "flow"),
            "assumptions": _assumptions(story, selected_task, capsule),
            "constraints": _string_list(capsule.get("constraints")),
        },
        "acceptanceMapping": acceptance_mapping,
        "repositoryContext": repository_context,
        "engineeringRules": engineering_rules,
        "risks": risks,
        "suggestedTests": suggested_tests,
        "readiness": readiness_payload,
        "aiEnrichment": ai_enrichment or {},
        "diagnostics": {
            "source": "deterministic_context_capsule",
            "capsuleId": capsule.get("capsuleId"),
            "capsuleType": capsule.get("capsuleType"),
            "dnaId": capsule.get("dnaId") or dna.get("dnaId"),
            "dnaVersion": capsule.get("dnaVersion") or dna.get("version"),
            "knowledgeVersion": capsule.get("knowledgeVersion"),
            "repositorySnapshotVersion": capsule.get("repositorySnapshotVersion"),
            "selectedModules": modules,
            "selectedFlows": flows,
            "selectedFiles": [item["name"] for item in relevant_files],
            "rejectedContext": rejected_context,
            "tokenEstimate": _estimate_tokens(json.dumps(package_seed, sort_keys=True)),
            "confidence": float(capsule.get("confidence") or 0),
            "freshnessStatus": _clean(capsule.get("freshnessStatus")) or "unknown",
            "validationStatus": _clean(validation_report.get("status")) or _clean(validation_report.get("validationStatus")),
            "taskPlanDiagnostics": task_plan.get("diagnostics") if isinstance(task_plan.get("diagnostics"), dict) else {},
        },
    }
    package["diagnostics"]["tokenEstimate"] = _estimate_tokens(json.dumps(package, sort_keys=True, default=str))
    return package


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace("\n", ",").split(",")]
        return _unique([part for part in parts if part])
    if isinstance(value, dict):
        return _unique([_clean(value.get("name") or value.get("title") or value.get("path"))])
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                result.append(_clean(item.get("name") or item.get("title") or item.get("path") or item.get("module") or item.get("flow")))
            else:
                result.extend(_string_list(item))
        return _unique([item for item in result if item])
    return [_clean(value)] if _clean(value) else []


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _item_id(item: dict[str, Any] | None) -> Any:
    if not isinstance(item, dict):
        return None
    for key in ("id", "work_item_id", "azure_work_item_id", "taskId", "storyId"):
        if item.get(key) not in ("", None):
            return item.get(key)
    return None


def _artifact_type(story: dict[str, Any], selected_task: dict[str, Any]) -> str:
    if selected_task:
        return "Task"
    explicit = _clean(story.get("artifactType") or story.get("artifact_type") or story.get("type") or story.get("work_item_type"))
    if explicit.casefold() == "task":
        return "Task"
    return "Story"


def _lineage_id(story: dict[str, Any], selected_task: dict[str, Any], dna: dict[str, Any], lineage: str) -> Any:
    keys = [f"{lineage}_id", f"parent_{lineage}_id", f"{lineage}Id"]
    for source in (selected_task, story):
        for key in keys:
            if source.get(key) not in ("", None):
                return source.get(key)
    parent_refs = dna.get("parentReferences") if isinstance(dna.get("parentReferences"), dict) else {}
    for key in keys:
        if parent_refs.get(key) not in ("", None):
            return parent_refs.get(key)
    return None


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _first(value: Any) -> str:
    items = _string_list(value)
    return items[0] if items else ""


def _dna_summary(dna: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(dna, dict):
        return {}
    evidence = dna.get("repositoryEvidence") if isinstance(dna.get("repositoryEvidence"), dict) else {}
    boundary = dna.get("planningBoundary") if isinstance(dna.get("planningBoundary"), dict) else {}
    return {
        "businessGoals": _string_list(dna.get("businessGoals")),
        "businessOutcome": _clean(dna.get("businessOutcome")),
        "capability": _clean(dna.get("capability")),
        "responsibilities": _string_list(dna.get("responsibilities")),
        "modules": _string_list(evidence.get("modules")),
        "flows": _string_list(evidence.get("flows")),
        "inScope": _string_list(boundary.get("inScope")),
        "outOfScope": _string_list(boundary.get("outOfScope")),
    }


def _story_goal(story: dict[str, Any], dna_summary: dict[str, Any]) -> str:
    return _clean(story.get("user_goal") or story.get("story_user_goal") or story.get("description")) or dna_summary.get("businessOutcome") or _clean(story.get("title"))


def _task_objective(selected_task: dict[str, Any], story: dict[str, Any]) -> str:
    return _clean(selected_task.get("objective") or selected_task.get("description") or selected_task.get("title")) or f"Deliver {_clean(story.get('title'))}"


def _default_scope(modules: list[str], flows: list[str]) -> list[str]:
    scope: list[str] = []
    if modules:
        scope.append(f"Implement only within selected modules: {', '.join(modules)}.")
    if flows:
        scope.append(f"Preserve selected flows: {', '.join(flows)}.")
    return scope


def _assumptions(story: dict[str, Any], selected_task: dict[str, Any], capsule: dict[str, Any]) -> list[str]:
    assumptions = _string_list(selected_task.get("assumptions")) + _string_list(story.get("assumptions"))
    if not assumptions:
        assumptions.append("Use only context approved in the Context Capsule.")
    if capsule.get("fileRankingStatus") == FILE_RANKING_UNAVAILABLE:
        assumptions.append(FILE_RANKING_UNAVAILABLE)
    return _unique(assumptions)


def _rejected_names(rejected_context: list[dict[str, Any]], item_type: str) -> list[str]:
    names: list[str] = []
    for item in rejected_context:
        candidate_type = _clean(item.get("type") or item.get("context_type")).casefold()
        if item_type in candidate_type:
            names.append(_clean(item.get("name") or item.get("title") or item.get("value")))
    return _unique([name for name in names if name])


def _repository_items(value: Any, *, item_type: str, source: str = "knowledge_registry") -> list[dict[str, Any]]:
    if not isinstance(value, list):
        value = _string_list(value)
    items: list[dict[str, Any]] = []
    for entry in value:
        if isinstance(entry, dict):
            name = _clean(entry.get("path") or entry.get("name") or entry.get("title") or entry.get("module") or entry.get("flow"))
            if not name:
                continue
            items.append(
                {
                    "name": name,
                    "type": _clean(entry.get("type")) or item_type,
                    "confidence": _float(entry.get("confidence") or entry.get("score"), 0.7),
                    "reason": _clean(entry.get("reason")) or f"Selected by {source}.",
                    "evidence": _string_list(entry.get("evidence")) or [name],
                    "source": _clean(entry.get("source")) or source,
                }
            )
            continue
        name = _clean(entry)
        if name:
            items.append(
                {
                    "name": name,
                    "type": item_type,
                    "confidence": 0.7,
                    "reason": f"Selected by {source}.",
                    "evidence": [name],
                    "source": source,
                }
            )
    return items


def _repository_named_items(profile: dict[str, Any], key: str) -> list[dict[str, Any]]:
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    candidates = registry.get(key) or registry.get(f"relevant_{key}") or []
    return _repository_items(candidates, item_type=key[:-1] if key.endswith("s") else key)


def _acceptance_mapping(
    acceptance_criteria: list[str],
    selected_task: dict[str, Any],
    generated_tasks: list[dict[str, Any]],
    modules: list[str],
    flows: list[str],
) -> list[dict[str, Any]]:
    task_area = _clean(selected_task.get("work_area") or selected_task.get("type") or selected_task.get("category")) or _infer_area(selected_task, modules)
    task_title = _clean(selected_task.get("title")) or "Selected execution task"
    mappings: list[dict[str, Any]] = []
    for index, criterion in enumerate(_string_list(acceptance_criteria), start=1):
        mappings.append(
            {
                "acceptanceCriteriaId": f"AC{index:03d}",
                "acceptanceText": criterion,
                "implementationArea": task_area,
                "validationExpectation": _validation_expectation(criterion, flows),
                "mappedTasks": _mapped_task_titles(criterion, generated_tasks) or [task_title],
            }
        )
    return mappings


def _infer_area(selected_task: dict[str, Any], modules: list[str]) -> str:
    text = f"{_clean(selected_task.get('title'))} {_clean(selected_task.get('description'))}".casefold()
    if any(term in text for term in ("ui", "screen", "view", "page")):
        return "UI Work"
    if any(term in text for term in ("api", "backend", "service", "controller")):
        return "Backend Work"
    if any(term in text for term in ("data", "repository", "database")):
        return "Data Work"
    if modules:
        return modules[0]
    return "Implementation Work"


def _validation_expectation(criterion: str, flows: list[str]) -> str:
    flow_text = f" in {', '.join(flows[:2])}" if flows else ""
    return f"Verify that {criterion.rstrip('.')} works as approved{flow_text}."


def _mapped_task_titles(criterion: str, tasks: list[dict[str, Any]]) -> list[str]:
    criterion_terms = set(_keywords(criterion))
    matches: list[str] = []
    for task in tasks:
        title = _clean(task.get("title"))
        if not title:
            continue
        task_terms = set(_keywords(f"{title} {_clean(task.get('description'))}"))
        if criterion_terms and len(criterion_terms & task_terms) >= 2:
            matches.append(title)
    return matches[:3]


def _keywords(text: str) -> list[str]:
    return [part for part in "".join(ch if ch.isalnum() else " " for ch in text.casefold()).split() if len(part) > 3]


def _engineering_rules(profile: dict[str, Any], standards: list[str], modules: list[str], flows: list[str]) -> list[dict[str, Any]]:
    dev = profile.get("development_standards") if isinstance(profile.get("development_standards"), dict) else {}
    ui = _string_list(profile.get("ui_guidelines"))
    rules: list[dict[str, Any]] = []
    stack_text = _format_stack(profile.get("technology_stack"))
    coding_text = "; ".join(
        _unique(
            [
                *_string_list(dev.get("architecture_patterns")),
                *_string_list(dev.get("coding_guidelines")),
                *_string_list(dev.get("testing_requirements")),
            ]
        )
    )
    if stack_text:
        rules.append({"type": "technology", "rule": f"Technology Stack: {stack_text}", "source": "execution_package"})
    if coding_text:
        rules.append({"type": "coding", "rule": f"Coding Standards: {coding_text}", "source": "execution_package"})
    rules.append({"type": "architecture", "rule": "Architecture Rules: preserve the boundaries in the selected context capsule.", "source": "context_capsule"})
    rules.extend(_rule_items("architecture", dev.get("architecture_patterns") or standards, "Architecture rule selected from project standards."))
    rules.extend(_rule_items("coding", dev.get("coding_guidelines"), "Coding rule selected from project standards."))
    rules.extend(_rule_items("security", dev.get("security_requirements"), "Security rule selected from project standards."))
    rules.extend(_rule_items("testing", dev.get("testing_requirements"), "Testing rule selected from project standards."))
    rules.extend(_rule_items("ui", ui, "UI guideline selected from project profile."))
    if modules:
        rules.append({"type": "validation", "rule": f"Keep changes inside selected modules: {', '.join(modules)}.", "source": "context_capsule"})
    if flows:
        rules.append({"type": "audit", "rule": f"Preserve behavior for selected flows: {', '.join(flows)}.", "source": "context_capsule"})
    if not rules:
        rules.append({"type": "coding", "rule": "Follow existing repository conventions and project standards.", "source": "deterministic_default"})
    return rules[:12]


def _format_stack(stack: Any) -> str:
    if isinstance(stack, dict):
        parts: list[str] = []
        for key, value in stack.items():
            values = _string_list(value)
            if values:
                parts.append(f"{key}: {', '.join(values)}")
        return "; ".join(parts)
    return "; ".join(_string_list(stack))


def _rule_items(rule_type: str, values: Any, reason: str) -> list[dict[str, Any]]:
    return [{"type": rule_type, "rule": value, "source": "project_standards", "reason": reason} for value in _string_list(values)]


def _execution_risks(capsule: dict[str, Any], validation_report: dict[str, Any]) -> list[dict[str, Any]]:
    risks = [{"type": "implementation", "risk": risk, "source": "context_capsule"} for risk in _string_list(capsule.get("risks"))]
    for issue in validation_report.get("issues", []) if isinstance(validation_report.get("issues"), list) else []:
        if isinstance(issue, dict):
            risks.append({"type": "validation", "risk": _clean(issue.get("message") or issue.get("reason") or issue.get("title")), "source": "validation"})
    if capsule.get("fileRankingStatus") == FILE_RANKING_UNAVAILABLE:
        risks.append({"type": "integration", "risk": FILE_RANKING_UNAVAILABLE, "source": "repository_intelligence"})
    return [risk for risk in risks if risk["risk"]][:10]


def _suggested_tests(
    story: dict[str, Any],
    selected_task: dict[str, Any],
    acceptance_mapping: list[dict[str, Any]],
    modules: list[str],
    flows: list[str],
    risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    title = _clean(selected_task.get("title")) or _clean(story.get("title")) or "approved behavior"
    flow = flows[0] if flows else "approved flow"
    tests = [
        {"type": "unit", "title": f"Validate {title} business rules", "coverage": _coverage_ids(acceptance_mapping), "priority": "High"},
        {"type": "integration", "title": f"Verify {flow} integration behavior", "coverage": _coverage_ids(acceptance_mapping), "priority": "High"},
        {"type": "negative", "title": f"Reject invalid or missing data for {title}", "coverage": _coverage_ids(acceptance_mapping), "priority": "Medium"},
        {"type": "permission", "title": f"Validate authorized access for {title}", "coverage": _coverage_ids(acceptance_mapping), "priority": "High"},
        {"type": "regression", "title": f"Regression check for {', '.join(modules[:2]) or 'selected modules'}", "coverage": _coverage_ids(acceptance_mapping), "priority": "Medium"},
    ]
    if any("ui" in _clean(selected_task.get("work_area")).casefold() or "ui" in _clean(selected_task.get("title")).casefold() for _ in [0]):
        tests.insert(2, {"type": "ui", "title": f"Verify UI states for {title}", "coverage": _coverage_ids(acceptance_mapping), "priority": "Medium"})
    if risks:
        tests.append({"type": "risk", "title": f"Validate mitigation for {risks[0]['risk']}", "coverage": _coverage_ids(acceptance_mapping), "priority": "Medium"})
    return tests[:8]


def _coverage_ids(acceptance_mapping: list[dict[str, Any]]) -> list[str]:
    return [item["acceptanceCriteriaId"] for item in acceptance_mapping]


def _readiness(
    readiness: dict[str, Any],
    acceptance_mapping: list[dict[str, Any]],
    repository_context: dict[str, Any],
    capsule: dict[str, Any],
    validation_report: dict[str, Any],
) -> dict[str, Any]:
    relevant_files = repository_context.get("relevantFiles") or []
    repo_alignment = 85 if (repository_context.get("relevantModules") or repository_context.get("relevantFlows")) else 50
    knowledge_alignment = round(float(capsule.get("confidence") or 0.7) * 100)
    acceptance_coverage = 100 if acceptance_mapping else 0
    file_confidence = round(sum(float(item.get("confidence") or 0) for item in relevant_files) / len(relevant_files) * 100) if relevant_files else 35
    validation_score = int(validation_report.get("score") or validation_report.get("validationScore") or 75)
    configured_score = int(readiness.get("score") or 0)
    score = round((repo_alignment + knowledge_alignment + acceptance_coverage + file_confidence + validation_score) / 5)
    if configured_score:
        score = round((score + configured_score) / 2)
    status = "Ready" if score >= 80 and acceptance_coverage else "Needs Review"
    if not acceptance_mapping:
        status = "Blocked"
    return {
        "repositoryAlignmentScore": repo_alignment,
        "knowledgeAlignmentScore": knowledge_alignment,
        "acceptanceCoverageScore": acceptance_coverage,
        "fileConfidenceScore": file_confidence,
        "executionReadinessScore": score,
        "status": status,
        "blockers": [] if status != "Blocked" else ["No acceptance criteria mapped to execution work."],
        "details": readiness.get("breakdown") if isinstance(readiness.get("breakdown"), dict) else {},
    }


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
