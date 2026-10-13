"""Deterministic Execution Package V2 builder.

Execution Package V2 is intentionally deterministic-first: it consumes the
already-selected Context Capsule and DNA lineage instead of rebuilding broad
project context or asking a model to rediscover intent.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from .package_builder import ExecutionPackageBuilder
from .package_models import ExecutionRequest


FILE_RANKING_UNAVAILABLE = "Repository file ranking not available"
SOURCE_CODE_NOT_INDEXED = "Source Code: Not Indexed"


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

    normalized_story_title = _normalize_story_title(story)
    normalized_story_goal = _normalize_user_story(story, normalized_story_title, dna_summary)
    raw_acceptance = acceptance_criteria or _string_list(capsule.get("acceptanceCriteria"))
    normalized_acceptance = _normalize_acceptance_criteria(raw_acceptance, normalized_story_title)

    modules = _string_list(capsule.get("selectedModules"))
    flows = _string_list(capsule.get("selectedFlows"))
    dependencies = _string_list(capsule.get("selectedDependencies"))
    standards = _string_list(capsule.get("selectedStandards"))
    rejected_context = [item for item in capsule.get("rejectedContext", []) if isinstance(item, dict)]
    modules, flows, rejected_context = _tighten_repository_context(
        normalized_story_title,
        normalized_story_goal,
        normalized_acceptance,
        modules,
        flows,
        rejected_context,
    )
    relevant_files = _repository_items(capsule.get("relevantFiles"), item_type="file")

    repository_context = {
        "relevantModules": _repository_items(modules, item_type="module", source="context_capsule"),
        "relevantFlows": _repository_items(flows, item_type="flow", source="context_capsule"),
        "relevantServices": _repository_named_items(profile, "services"),
        "relevantAPIs": _repository_items(capsule.get("relevantAPIs"), item_type="api", source="context_capsule")
        or _repository_named_items(profile, "apis"),
        "relevantFiles": relevant_files,
        "relatedTests": _repository_named_items(profile, "tests"),
        "dependencies": _repository_items(dependencies, item_type="dependency", source="context_capsule"),
        "fileRankingStatus": _clean(capsule.get("fileRankingStatus")) or FILE_RANKING_UNAVAILABLE,
        "moduleContext": capsule.get("moduleContext") if isinstance(capsule.get("moduleContext"), list) else [],
    }
    if not relevant_files:
        repository_context["fileRankingStatus"] = FILE_RANKING_UNAVAILABLE

    acceptance_mapping, acceptance_quality = _acceptance_mapping(
        normalized_acceptance,
        raw_acceptance,
        normalized_story_title,
        selected_task,
        generated_tasks,
        modules,
        flows,
    )
    risks = _execution_risks(capsule, validation_report)
    engineering_rules = _engineering_rules(profile, standards, modules, flows)
    suggested_tests = _suggested_tests(story, selected_task, acceptance_mapping, modules, flows, risks)
    capsule_suggested_tests = capsule.get("suggestedTests") if isinstance(capsule.get("suggestedTests"), list) else []
    if capsule_suggested_tests:
        suggested_tests = _dedupe_named_dicts([*_normalize_suggested_tests(capsule_suggested_tests), *suggested_tests], key="title")[:8]
    readiness_payload = _readiness(
        readiness,
        acceptance_mapping,
        acceptance_quality,
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
            "storyTitle": normalized_story_title,
            "storyUserGoal": normalized_story_goal,
            "taskObjective": _task_objective(selected_task, story, normalized_story_title),
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
            "acceptanceQuality": acceptance_quality,
            "tokenEstimate": _estimate_tokens(json.dumps(package_seed, sort_keys=True)),
            "confidence": float(capsule.get("confidence") or 0),
            "freshnessStatus": _clean(capsule.get("freshnessStatus")) or "unknown",
            "validationStatus": _clean(validation_report.get("status")) or _clean(validation_report.get("validationStatus")),
            "taskPlanDiagnostics": task_plan.get("diagnostics") if isinstance(task_plan.get("diagnostics"), dict) else {},
        },
    }
    package["diagnostics"]["tokenEstimate"] = _estimate_tokens(json.dumps(package, sort_keys=True, default=str))
    # Compatibility adapter: legacy callers keep their established fields while
    # all canonical Milestone 3.3 sections are built through the strict
    # ContextCapsule + ExecutionRequest contract.
    canonical_capsule = {
        **capsule,
        "planningContext": {
            "businessGoal": package["businessContext"].get("epicBusinessGoal"),
            "epic": {"id": epic_id} if epic_id else {},
            "feature": {"id": feature_id} if feature_id else {},
            "story": {**story, "title": normalized_story_title},
            "task": selected_task,
            "acceptanceCriteria": normalized_acceptance,
            "assumptions": package["implementationBoundary"].get("assumptions", []),
            "planningConfidence": float(capsule.get("confidence") or 0),
        },
        "repositoryContext": {
            "repositoryMode": readiness_payload.get("repositoryMode") or "Unavailable",
            "snapshot": capsule.get("repositorySnapshotVersion"),
            "relevantModules": modules,
            "relevantFiles": [item.get("name") for item in relevant_files],
            "relevantAPIs": [item.get("name") for item in repository_context.get("relevantAPIs", [])],
            "dependencies": dependencies,
            "repositoryConfidence": float(capsule.get("confidence") or 0),
        },
        "knowledge": {
            "capabilities": _string_list(capsule.get("selectedCapabilities")),
            "flows": flows,
            "engineeringStandards": standards,
            "knownRisks": [item.get("description") or item.get("title") for item in risks],
            "securityRules": [item.get("rule") or item.get("title") for item in engineering_rules if "security" in str(item).casefold()],
        },
        "suggestedTests": [item.get("title") for item in suggested_tests],
    }
    canonical = ExecutionPackageBuilder().build(
        canonical_capsule,
        ExecutionRequest(
            purpose="ImplementationPackage", story_id=str(story_id or ""), task_id=str(task_id or ""),
            repository_snapshot_version=_clean(capsule.get("repositorySnapshotVersion")),
            execution_mode="Implement",
        ),
    )
    for section in ("metadata", "planningContext", "engineeringMemory", "knowledge", "implementationGuidance", "validationGuidance", "qaGuidance", "tokenGuidance"):
        package[section] = canonical[section]
    package["diagnostics"].update({
        "contextSourcesUsed": canonical["diagnostics"]["contextSourcesUsed"],
        "missingContext": canonical["diagnostics"]["missingContext"],
        "excludedContext": canonical["diagnostics"]["excludedContext"],
        "builderVersion": canonical["diagnostics"]["builderVersion"],
        "retrievalPerformed": False,
        "llmUsed": False,
    })
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
    return _normalize_user_story(story, _normalize_story_title(story), dna_summary)


def _task_objective(selected_task: dict[str, Any], story: dict[str, Any], normalized_story_title: str = "") -> str:
    objective = _clean(selected_task.get("objective"))
    if objective:
        return objective
    title = _clean(selected_task.get("title"))
    if title:
        return _normalize_sentence(title)
    story_title = normalized_story_title or _normalize_story_title(story)
    return f"Implement {story_title or _clean(story.get('title'))} within the approved story boundary."


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
    raw_acceptance_criteria: list[str],
    story_title: str,
    selected_task: dict[str, Any],
    generated_tasks: list[dict[str, Any]],
    modules: list[str],
    flows: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    task_area = _clean(selected_task.get("work_area") or selected_task.get("type") or selected_task.get("category")) or _infer_area(selected_task, modules)
    task_title = _clean(selected_task.get("title")) or "Selected execution task"
    quality = _acceptance_quality(acceptance_criteria, raw_acceptance_criteria)
    mappings: list[dict[str, Any]] = []
    for index, criterion in enumerate(acceptance_criteria, start=1):
        mappings.append(
            {
                "acceptanceCriteriaId": f"AC{index:03d}",
                "acceptanceText": criterion,
                "implementationArea": _implementation_area_for_criterion(criterion, task_area, modules, flows, story_title),
                "validationExpectation": _validation_expectation(criterion, flows),
                "mappedTasks": _mapped_task_titles(criterion, generated_tasks) or [task_title],
            }
        )
    return mappings, quality


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


def _implementation_area_for_criterion(
    criterion: str,
    default_area: str,
    modules: list[str],
    flows: list[str],
    story_title: str,
) -> str:
    text = f"{criterion} {story_title}".casefold()
    if any(term in text for term in ("display", "view", "screen", "dashboard", "page", "list")):
        return "UI Work"
    if any(term in text for term in ("api", "service", "endpoint", "sort", "filter", "order", "load", "retrieve")):
        return "Backend Work"
    if any(term in text for term in ("audit", "history", "persist", "store", "repository", "database")):
        return "Data Work"
    if any(term in text for term in ("telemetry", "classification", "severity")) and modules:
        return modules[0]
    if flows:
        return default_area
    return default_area


def _validation_expectation(criterion: str, flows: list[str]) -> str:
    lowered = criterion.casefold()
    if any(term in lowered for term in ("permission", "authorized", "unauthorized", "access denied")):
        return "Validate authorized access, denied access, and audit behavior."
    if any(term in lowered for term in ("load", "display", "view", "list", "details")):
        return "Validate positive rendering, empty state handling, and error handling."
    if any(term in lowered for term in ("sort", "filter", "order")):
        return "Validate ordering, filtering accuracy, and regression coverage."
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
    rules.extend(_stack_rule_items(profile.get("technology_stack")))
    rules.append(
        {
            "type": "architecture",
            "category": "Architecture Rules",
            "rule": "Preserve the approved implementation boundary from the Context Capsule.",
            "source": "context_capsule",
        }
    )
    rules.extend(_rule_items("architecture", dev.get("architecture_patterns") or standards, "Architecture rule selected from project standards.", category="Architecture Rules"))
    rules.extend(_rule_items("coding", dev.get("coding_guidelines"), "Coding rule selected from project standards.", category="Coding Standards"))
    rules.extend(_rule_items("security", dev.get("security_requirements"), "Security rule selected from project standards.", category="Security"))
    rules.extend(_rule_items("testing", dev.get("testing_requirements"), "Testing rule selected from project standards.", category="Testing"))
    rules.extend(_rule_items("ui", ui, "UI guideline selected from project profile.", category="UI Guidelines"))
    if modules:
        rules.append({"type": "validation", "category": "Implementation Boundary", "rule": f"Keep changes inside selected modules: {', '.join(modules)}.", "source": "context_capsule"})
    if flows:
        rules.append({"type": "audit", "category": "Implementation Boundary", "rule": f"Preserve behavior for selected flows: {', '.join(flows)}.", "source": "context_capsule"})
    if not rules:
        rules.append({"type": "coding", "category": "Coding Standards", "rule": "Follow existing repository conventions and project standards.", "source": "deterministic_default"})
    return rules[:16]


def _normalize_suggested_tests(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        title = _clean(item.get("title"))
        if not title:
            continue
        normalized.append(
            {
                "type": _clean(item.get("type")) or "test",
                "title": title,
                "coverage": _string_list(item.get("coverage")) or [],
                "priority": _clean(item.get("priority")) or "Medium",
            }
        )
    return normalized


def _dedupe_named_dicts(items: list[dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        marker = _clean(item.get(key)).casefold()
        if not marker or marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)
    return deduped


def _stack_rule_items(stack: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(stack, dict):
        labels = {
            "mobile": "Mobile",
            "backend": "Backend",
            "database": "Database",
            "analytics": "Analytics",
            "frontend": "Frontend",
            "firmware": "Firmware",
        }
        for key, label in labels.items():
            values = _string_list(stack.get(key))
            if values:
                items.append({"type": "technology", "category": "Technology Stack", "rule": f"{label}: {', '.join(values)}", "source": "execution_package"})
        return items
    values = _string_list(stack)
    return [{"type": "technology", "category": "Technology Stack", "rule": value, "source": "execution_package"} for value in values]


def _rule_items(rule_type: str, values: Any, reason: str, *, category: str) -> list[dict[str, Any]]:
    return [{"type": rule_type, "category": category, "rule": value, "source": "project_standards", "reason": reason} for value in _string_list(values)]


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
    title = _clean(selected_task.get("title")) or _normalize_story_title(story) or "approved behavior"
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
    acceptance_quality: dict[str, Any],
    repository_context: dict[str, Any],
    capsule: dict[str, Any],
    validation_report: dict[str, Any],
) -> dict[str, Any]:
    relevant_files = repository_context.get("relevantFiles") or []
    repo_alignment = 85 if (repository_context.get("relevantModules") or repository_context.get("relevantFlows")) else 50
    knowledge_alignment = round(float(capsule.get("confidence") or 0.7) * 100)
    acceptance_coverage = 100 if acceptance_mapping else 0
    file_confidence = round(sum(float(item.get("confidence") or 0) for item in relevant_files) / len(relevant_files) * 100) if relevant_files else 25
    validation_score = int(validation_report.get("score") or validation_report.get("validationScore") or 75)
    configured_score = int(readiness.get("score") or 0)
    score = round((repo_alignment + knowledge_alignment + acceptance_coverage + file_confidence + validation_score) / 5)
    if configured_score:
        score = round((score + configured_score) / 2)

    repository_mode = "CodeIndexed" if relevant_files else "Knowledge Snapshot"
    blockers: list[str] = []
    warnings: list[str] = []

    if not acceptance_mapping:
        status = "Blocked"
        score = min(score, 40)
        blockers.append("No acceptance criteria mapped to execution work.")
    else:
        status = "Ready" if score >= 80 else "NeedsReview"

    if repository_mode == "Knowledge Snapshot":
        score = min(score, 80)
        warnings.extend([FILE_RANKING_UNAVAILABLE, SOURCE_CODE_NOT_INDEXED])
        if status == "Ready":
            status = "NeedsReview"

    if acceptance_quality.get("issues"):
        score = min(score, 75)
        status = "NeedsReview"
        warnings.append("Acceptance criteria require cleanup before implementation.")

    return {
        "repositoryAlignmentScore": repo_alignment,
        "knowledgeAlignmentScore": knowledge_alignment,
        "acceptanceCoverageScore": acceptance_coverage,
        "fileConfidenceScore": file_confidence,
        "executionReadinessScore": score,
        "status": status,
        "repositoryMode": repository_mode,
        "sourceCodeStatus": "Indexed" if relevant_files else "Not Indexed",
        "fileRanking": "Available" if relevant_files else "Unavailable",
        "warnings": _unique(warnings),
        "blockers": blockers,
        "acceptanceQuality": acceptance_quality,
        "details": readiness.get("breakdown") if isinstance(readiness.get("breakdown"), dict) else {},
    }


def _normalize_story_title(story: dict[str, Any]) -> str:
    title = _clean(story.get("title"))
    return _title_case(title) if title else "Approved Story"


def _normalize_user_story(story: dict[str, Any], normalized_title: str, dna_summary: dict[str, Any]) -> str:
    raw = _clean(story.get("user_goal") or story.get("story_user_goal") or story.get("description"))
    if raw:
        return raw
    persona = _extract_persona(raw) or "Operations User"
    persona_phrase = f"As {_article_for(persona)} {persona},"
    outcome = dna_summary.get("businessOutcome") or "I can complete the approved operational workflow with confidence."
    action = _clean(normalized_title).casefold()
    if action.startswith("view "):
        action = f"view {action[5:]}"
    elif not action.startswith("to "):
        action = action
    return f"{persona_phrase} I want to {action} so that {_normalize_benefit(outcome)}"


def _normalize_acceptance_criteria(criteria: list[str], story_title: str) -> list[str]:
    values = [_clean(item) for item in criteria if _clean(item)]
    merged: list[str] = []
    field_buffer: list[str] = []
    list_prefix = ""
    for item in values:
        if _is_field_list_anchor(item):
            if field_buffer and list_prefix:
                merged.append(_build_field_list_sentence(list_prefix, field_buffer))
                field_buffer = []
            list_prefix, field_seed = _anchor_prefix(item, story_title)
            field_buffer.extend(field_seed)
            continue
        if field_buffer and _is_field_fragment(item):
            field_buffer.append(_field_fragment(item))
            continue
        if field_buffer and list_prefix:
            merged.append(_build_field_list_sentence(list_prefix, field_buffer))
            field_buffer = []
            list_prefix = ""
        merged.extend(_split_atomic_criteria(item))
    if field_buffer and list_prefix:
        merged.append(_build_field_list_sentence(list_prefix, field_buffer))
    normalized = [_normalize_sentence(item) for item in merged if _clean(item)]
    return _unique([item for item in normalized if item])


def _acceptance_quality(criteria: list[str], raw_criteria: list[str] | None = None) -> dict[str, Any]:
    issues: list[str] = []
    for criterion in raw_criteria or []:
        raw = _clean(criterion)
        if re.match(r"^(and|or|,)\b", raw, flags=re.IGNORECASE):
            issues.append(f"Acceptance criterion starts like a fragment: {raw}")
    seen: set[str] = set()
    for criterion in criteria:
        cleaned = _clean(criterion)
        lowered = cleaned.casefold()
        if lowered in seen:
            issues.append(f"Duplicate acceptance criterion: {cleaned}")
        seen.add(lowered)
        if not cleaned or len(cleaned.split()) < 4:
            issues.append(f"Fragmented acceptance criterion: {cleaned}")
        if re.match(r"^(and|or|,|[a-z])\b", cleaned):
            issues.append(f"Acceptance criterion starts like a fragment: {cleaned}")
        if len(cleaned) > 250:
            issues.append(f"Acceptance criterion is too long and should be split: {cleaned[:80]}...")
        if not cleaned.endswith("."):
            issues.append(f"Acceptance criterion is not a complete sentence: {cleaned}")
    return {"issues": issues, "passes": not issues, "count": len(criteria)}


def _tighten_repository_context(
    story_title: str,
    story_goal: str,
    acceptance_criteria: list[str],
    modules: list[str],
    flows: list[str],
    rejected_context: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    intent = " ".join([story_title, story_goal, *acceptance_criteria]).casefold()
    filtered_modules: list[str] = []
    filtered_flows: list[str] = []
    for module in modules:
        keep, reason = _repository_item_allowed(module, "module", intent)
        if keep:
            filtered_modules.append(module)
        else:
            rejected_context.append({"type": "module", "name": module, "reason": reason})
    for flow in flows:
        keep, reason = _repository_item_allowed(flow, "flow", intent)
        if keep:
            filtered_flows.append(flow)
        else:
            rejected_context.append({"type": "flow", "name": flow, "reason": reason})
    return _unique(filtered_modules), _unique(filtered_flows), rejected_context


def _repository_item_allowed(name: str, item_type: str, intent: str) -> tuple[bool, str]:
    lowered = name.casefold()
    if "firmware" in lowered and not any(term in intent for term in ("firmware", "upgrade", "rollout", "version", "rollback", "compliance")):
        return False, f"{name} removed because the current implementation does not involve firmware behavior."
    if "login flow" in lowered and not any(term in intent for term in ("login", "token", "session", "authentication refresh", "authorization failure")):
        return False, "Login Flow removed because login behavior is not changing in this implementation."
    if "device registration flow" in lowered and not any(term in intent for term in ("device registration", "register device", "onboard device")):
        return False, "Device Registration Flow removed because the story does not change device registration behavior."
    if "device management" in lowered and not any(term in intent for term in ("device health", "device details", "device status", "device condition")):
        return False, f"{name} removed because the story does not require device management behavior."
    if "analytics" in lowered and not any(term in intent for term in ("analytics", "trend", "report", "dashboard", "metric", "kpi")):
        return False, f"{name} removed because analytics behavior is not part of this implementation."
    if item_type == "flow" and "authentication" in lowered:
        return False, f"{name} removed because authentication belongs in standards unless the auth flow itself changes."
    return True, ""


def _contains_keywords(text: str, *keywords: str) -> bool:
    lowered = text.casefold()
    return all(keyword.casefold() in lowered for keyword in keywords)


def _title_case(text: str) -> str:
    return " ".join(word.capitalize() for word in text.split())


def _normalize_sentence(text: str) -> str:
    cleaned = _clean(text)
    if not cleaned:
        return ""
    cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned if cleaned.endswith(".") else f"{cleaned}."


def _extract_persona(raw: str) -> str:
    match = re.search(r"As\s+(?:an?|the)\s+([^,]+),", raw, flags=re.IGNORECASE)
    return _clean(match.group(1)) if match else ""


def _article_for(value: str) -> str:
    return "an" if value[:1].casefold() in {"a", "e", "i", "o", "u"} else "a"


def _is_field_list_anchor(text: str) -> bool:
    lowered = text.casefold()
    return "list shows" in lowered or "list displays" in lowered or "details show" in lowered


def _anchor_prefix(text: str, story_title: str) -> tuple[str, list[str]]:
    lowered = text.casefold()
    noun = "The fault event list displays" if "list" in lowered else "The fault event details display"
    fragments = re.split(r"\bshows\b|\bdisplays\b", text, flags=re.IGNORECASE)
    tail = fragments[-1] if fragments else text
    seed = [_field_fragment(tail)] if _field_fragment(tail) else []
    if not seed and _contains_keywords(story_title, "severity"):
        seed.append("Severity")
    return noun, seed


def _is_field_fragment(text: str) -> bool:
    cleaned = _clean(text)
    if not cleaned:
        return False
    if len(cleaned.split()) > 5:
        return False
    return not bool(re.search(r"\b(is|are|can|must|should|shows|displays|loads|sorts|filters)\b", cleaned.casefold()))


def _field_fragment(text: str) -> str:
    cleaned = _clean(re.sub(r"^(and|or|,)\s*", "", text, flags=re.IGNORECASE))
    return cleaned.rstrip(".")


def _build_field_list_sentence(prefix: str, fields: list[str]) -> str:
    unique_fields = _unique([field.rstrip(".") for field in fields if field.rstrip(".")])
    if not unique_fields:
        return ""
    if len(unique_fields) == 1:
        joined = unique_fields[0]
    else:
        joined = ", ".join(unique_fields[:-1]) + f", and {unique_fields[-1]}"
    return f"{prefix} {joined}."


def _normalize_benefit(outcome: str) -> str:
    cleaned = _clean(outcome)
    if not cleaned:
        return "I can complete the approved operational workflow with confidence."
    if cleaned.lower().startswith("i "):
        return "I" + cleaned[1:]
    return cleaned[0].lower() + cleaned[1:]


def _split_atomic_criteria(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"(?<=[.])\s+", text) if part.strip()]
    results: list[str] = []
    for part in parts:
        cleaned = _clean(part)
        if cleaned.casefold().startswith("and "):
            cleaned = cleaned[4:]
        if cleaned:
            results.append(cleaned)
    return results or [text]


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
