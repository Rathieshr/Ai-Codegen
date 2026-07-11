"""Deterministic Execution Package v2 builder; no retrieval and no LLM calls."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Protocol

from .package_models import ExecutionRequest, normalize_capsule


class IExecutionPackageBuilder(Protocol):
    def build(self, capsule: dict[str, Any], request: ExecutionRequest) -> dict[str, Any]: ...


class ExecutionPackageBuilder:
    """Consumes only a Unified Context Capsule and an ExecutionRequest."""

    version = "2.0"

    def build(self, capsule: dict[str, Any], request: ExecutionRequest) -> dict[str, Any]:
        request.validate()
        capsule = normalize_capsule(capsule)
        planning = _planning(capsule, request)
        repository = _repository(capsule, request)
        memory = _memory(capsule)
        knowledge = _knowledge(capsule)
        validation = _validation(capsule, planning, repository, knowledge)
        qa = _qa(capsule, planning, validation)
        implementation = _implementation(capsule, request, planning, repository, knowledge)
        readiness = _readiness(capsule, planning, repository, memory, knowledge, validation)
        generated_at = datetime.now(timezone.utc).isoformat()
        seed = {"capsule": capsule.get("capsuleId"), "story": request.story_id, "task": request.task_id, "mode": request.execution_mode, "snapshot": repository.get("snapshot")}
        package_id = f"execpkg_{hashlib.sha256(json.dumps(seed, sort_keys=True, default=str).encode()).hexdigest()[:12]}"
        warnings = _strings(capsule.get("warnings"))
        missing = _missing_context(planning, repository, knowledge, validation)
        token_guidance = _token_guidance(planning, repository, memory, knowledge, implementation, validation, qa)
        metadata = {
            "packageId": package_id, "generatedAt": generated_at, "capsuleVersion": str(capsule.get("capsuleVersion") or "1"),
            "repositorySnapshotVersion": repository.get("snapshot") or request.repository_snapshot_version,
            "knowledgeVersion": str(capsule.get("knowledgeVersion") or _version(capsule, "KnowledgeRegistry")),
            "planningVersion": str(capsule.get("planningVersion") or _version(capsule, "Planning")),
            "engineeringMemoryVersion": str(capsule.get("engineeringMemoryVersion") or _version(capsule, "EngineeringMemory")),
            "confidence": readiness["confidence"], "executionReadiness": readiness["score"], "status": readiness["status"],
        }
        result = {
            "metadata": metadata, "planningContext": planning, "repositoryContext": repository,
            "engineeringMemory": memory, "knowledge": knowledge, "implementationGuidance": implementation,
            "validationGuidance": validation, "qaGuidance": qa, "tokenGuidance": token_guidance,
            "diagnostics": {
                "contextSourcesUsed": sorted(capsule.get("contextSections", {}).keys()), "repositoryMode": repository["repositoryMode"],
                "confidence": readiness["confidence"], "warnings": warnings, "missingContext": missing,
                "excludedContext": capsule.get("excludedContext", []), "rejectedContext": capsule.get("rejectedContext", []),
                "executionReadiness": readiness, "capsuleId": capsule.get("capsuleId"), "builderVersion": self.version,
                "retrievalPerformed": False, "llmUsed": False,
            },
        }
        return _legacy_aliases(result, request)


def _items(capsule: dict, source: str = "", category: str = "") -> list[dict]:
    selected = capsule.get("selectedContext") if isinstance(capsule.get("selectedContext"), list) else []
    return [item for item in selected if isinstance(item, dict) and (not source or item.get("sourceType") == source) and (not category or item.get("category") == category)]


def _content(item: dict) -> str: return str(item.get("content") or item.get("title") or "")
def _titles(items: list[dict]) -> list[str]: return _unique([str(item.get("title") or _content(item)) for item in items])
def _strings(value: Any) -> list[str]:
    if isinstance(value, str): return [value] if value else []
    if isinstance(value, list): return _unique([str(item.get("title") or item.get("content") or item) if isinstance(item, dict) else str(item) for item in value if item])
    return []
def _unique(values: list[str]) -> list[str]: return list(dict.fromkeys(item.strip() for item in values if item and item.strip()))
def _version(capsule: dict, source: str) -> str:
    return next((str(item.get("version") or "") for item in capsule.get("sourceSummary", []) if item.get("sourceType") == source), "")


def _planning(capsule: dict, request: ExecutionRequest) -> dict:
    legacy = capsule.get("planningContext") if isinstance(capsule.get("planningContext"), dict) else {}
    planning_items = _items(capsule, "Planning")
    artifact = legacy.get("story") or capsule.get("artifact") or (planning_items[0] if planning_items else {})
    acceptance = _strings(legacy.get("acceptanceCriteria") or capsule.get("acceptanceCriteria") or artifact.get("acceptanceCriteria"))
    return {
        "businessGoal": legacy.get("businessGoal") or capsule.get("businessGoal") or "",
        "epic": legacy.get("epic") or capsule.get("epic") or {}, "feature": legacy.get("feature") or capsule.get("feature") or {},
        "story": artifact, "task": legacy.get("task") or capsule.get("task") or ({"id": request.task_id} if request.task_id else {}),
        "acceptanceCriteria": acceptance, "storyPoints": legacy.get("storyPoints") or artifact.get("storyPoints"),
        "assumptions": _strings(legacy.get("assumptions") or capsule.get("assumptions")),
        "planningConfidence": float(legacy.get("planningConfidence") or _source_confidence(capsule, "Planning")),
    }


def _repository(capsule: dict, request: ExecutionRequest) -> dict:
    legacy = capsule.get("repositoryContext") if isinstance(capsule.get("repositoryContext"), dict) else {}
    diagnostics = capsule.get("diagnostics") if isinstance(capsule.get("diagnostics"), dict) else {}
    mode = str(legacy.get("repositoryMode") or diagnostics.get("repositoryMode") or capsule.get("repositoryMode") or "Unavailable")
    files = _titles(_items(capsule, "Repository", "File")) or _strings(legacy.get("relevantFiles") or capsule.get("relevantFiles"))
    if mode != "CodeIndexed": files = []
    return {
        "repositoryMode": mode, "snapshot": legacy.get("snapshot") or capsule.get("repositorySnapshotVersion") or request.repository_snapshot_version,
        "relevantModules": _titles(_items(capsule, "Repository", "Module")) or _strings(legacy.get("relevantModules") or capsule.get("selectedModules")),
        "relevantFiles": files, "relevantAPIs": _titles(_items(capsule, "Repository", "API")) or (_strings(legacy.get("relevantAPIs")) if mode == "CodeIndexed" else []),
        "dependencies": _titles(_items(capsule, "Repository", "Dependency")) or _strings(legacy.get("dependencies") or capsule.get("selectedDependencies")),
        "engineeringGraphReferences": _strings(legacy.get("engineeringGraphReferences") or capsule.get("engineeringGraphReferences")),
        "repositoryConfidence": float(legacy.get("repositoryConfidence") or _source_confidence(capsule, "Repository")),
    }


def _memory(capsule: dict) -> dict:
    legacy = capsule.get("engineeringMemory") if isinstance(capsule.get("engineeringMemory"), dict) else {}
    memories = _items(capsule, "EngineeringMemory")
    all_titles = _titles(memories)
    return {key: _strings(legacy.get(key)) or ([title for title in all_titles if term in title.casefold()] if term else all_titles) for key, term in (("reusablePatterns", "pattern"), ("relatedImplementations", "implementation"), ("previousBugs", "bug"), ("reusableTests", "test"), ("architectureDecisions", "architecture"), ("lessonsLearned", "lesson"), ("reuseRecommendations", ""))}


def _knowledge(capsule: dict) -> dict:
    legacy = capsule.get("knowledge") if isinstance(capsule.get("knowledge"), dict) else {}
    knowledge = _items(capsule, "KnowledgeRegistry")
    standards = _items(capsule, "EngineeringStandards")
    return {
        "capabilities": _strings(legacy.get("capabilities") or capsule.get("selectedCapabilities")), "flows": _strings(legacy.get("flows") or capsule.get("selectedFlows")),
        "engineeringStandards": _titles(standards) or _strings(legacy.get("engineeringStandards") or capsule.get("selectedStandards")),
        "architectureRules": _strings(legacy.get("architectureRules")), "technologyStack": _strings(legacy.get("technologyStack")),
        "knownRisks": _strings(legacy.get("knownRisks") or capsule.get("risks")), "securityRules": _strings(legacy.get("securityRules")),
        "validationRules": _strings(legacy.get("validationRules")), "knowledgeItems": _titles(knowledge),
    }


def _implementation(capsule: dict, request: ExecutionRequest, planning: dict, repository: dict, knowledge: dict) -> dict:
    story = planning.get("story") if isinstance(planning.get("story"), dict) else {}
    objective = str(story.get("description") or story.get("title") or f"Execute {request.execution_mode} request")
    blocked_modules, blocked_flows = _blocked(capsule)
    sequence = ["Confirm acceptance criteria and implementation boundaries."]
    if repository["relevantFiles"]: sequence.append("Inspect the capsule-ranked repository files and graph references.")
    sequence.extend(["Implement the smallest change within allowed modules and flows.", "Add mapped tests and run validation guidance."])
    return {
        "implementationObjective": objective, "recommendedSequence": sequence,
        "implementationBoundaries": _strings(capsule.get("inScope")), "blockedModules": blocked_modules, "blockedFlows": blocked_flows,
        "suggestedFiles": repository["relevantFiles"], "recommendedAPIs": repository["relevantAPIs"],
        "expectedDeliverables": _strings(capsule.get("expectedDeliverables")) or ["Implementation changes", "Acceptance-mapped tests", "Validation evidence"],
        "executionMode": request.execution_mode, "targetPlatform": request.target_platform,
    }


def _validation(capsule: dict, planning: dict, repository: dict, knowledge: dict) -> dict:
    acceptance = planning["acceptanceCriteria"]
    mapping = [{"acceptanceCriteriaId": f"AC{i:03d}", "acceptanceText": text, "validationExpectation": f"Verify: {text}"} for i, text in enumerate(acceptance, 1)]
    return {
        "acceptanceMapping": mapping, "regressionAreas": _unique(repository["relevantModules"] + knowledge["flows"]),
        "permissionRequirements": knowledge["securityRules"], "riskAreas": knowledge["knownRisks"],
        "architectureConstraints": knowledge["architectureRules"] + knowledge["engineeringStandards"],
        "validationCompleteness": 1.0 if mapping and (knowledge["validationRules"] or repository["repositoryMode"] != "Unavailable") else 0.5 if mapping else 0.0,
    }


def _qa(capsule: dict, planning: dict, validation: dict) -> dict:
    acceptance = validation["acceptanceMapping"]
    functional = [f"Validate {item['acceptanceCriteriaId']}: {item['acceptanceText']}" for item in acceptance]
    return {
        "suggestedTests": _strings(capsule.get("suggestedTests")) or functional,
        "regressionTests": [f"Regression check for {area}" for area in validation["regressionAreas"]],
        "permissionTests": [f"Verify permission: {rule}" for rule in validation["permissionRequirements"]],
        "negativeTests": [f"Reject invalid input for {item['acceptanceCriteriaId']}" for item in acceptance],
        "performanceTests": _strings(capsule.get("performanceTests")),
        "coverageExpectations": {"acceptanceCriteria": "100%", "negativePaths": "Required", "permissions": "Required when security rules exist"},
    }


def _source_confidence(capsule: dict, source: str) -> float:
    values = [float(item.get("confidenceScore") or 0) for item in _items(capsule, source)]
    return round(sum(values) / len(values), 3) if values else 0.0


def _readiness(capsule: dict, planning: dict, repository: dict, memory: dict, knowledge: dict, validation: dict) -> dict:
    signals = {
        "planningCompleteness": _ratio([planning["story"], planning["acceptanceCriteria"]]),
        "repositoryConfidence": repository["repositoryConfidence"], "memoryConfidence": _source_confidence(capsule, "EngineeringMemory"),
        "knowledgeCompleteness": _ratio([knowledge["capabilities"] or knowledge["knowledgeItems"], knowledge["engineeringStandards"] or knowledge["architectureRules"]]),
        "acceptanceCompleteness": 1.0 if planning["acceptanceCriteria"] else 0.0,
        "validationCompleteness": validation["validationCompleteness"],
        "repositoryFreshness": 1.0 if str(capsule.get("freshnessStatus") or "").casefold() == "fresh" else 0.6 if repository["repositoryMode"] != "Unavailable" else 0.0,
    }
    weights = {"planningCompleteness": .2, "repositoryConfidence": .15, "memoryConfidence": .1, "knowledgeCompleteness": .15, "acceptanceCompleteness": .2, "validationCompleteness": .1, "repositoryFreshness": .1}
    score = round(sum(signals[key] * weights[key] for key in weights) * 100)
    blocked_modules, _ = _blocked(capsule)
    status = "Blocked" if not planning["story"] or not planning["acceptanceCriteria"] else "Ready" if score >= 75 and not blocked_modules else "Needs Review"
    confidence = round(float(capsule.get("confidence") or sum(signals.values()) / len(signals)), 3)
    return {"score": score, "status": status, "confidence": confidence, "signals": signals}


def _ratio(values: list[Any]) -> float: return sum(bool(value) for value in values) / len(values)
def _blocked(capsule: dict) -> tuple[list[str], list[str]]:
    modules, flows = [], []
    for item in capsule.get("rejectedContext", []):
        candidate = item.get("candidate", item) if isinstance(item, dict) else {}
        category = str(candidate.get("category") or candidate.get("type") or "").casefold()
        name = str(candidate.get("title") or candidate.get("name") or candidate.get("content") or "")
        reason = str(item.get("reason") or candidate.get("reason") or "").casefold()
        if "blocked" not in reason: continue
        (modules if "module" in category else flows if "flow" in category else modules).append(name)
    return _unique(modules), _unique(flows)


def _token_guidance(*sections: dict) -> dict:
    base = max(1, len(json.dumps(sections, sort_keys=True, default=str)) // 4)
    return {"developerPrompt": base, "validationPrompt": round(base * .55), "qaPrompt": round(base * .5), "prReviewPrompt": round(base * .45)}


def _missing_context(planning: dict, repository: dict, knowledge: dict, validation: dict) -> list[str]:
    missing = []
    if not planning["acceptanceCriteria"]: missing.append("Acceptance Criteria")
    if repository["repositoryMode"] == "Unavailable": missing.append("Repository Context")
    if not knowledge["engineeringStandards"]: missing.append("Engineering Standards")
    if not validation["acceptanceMapping"]: missing.append("Acceptance Mapping")
    return missing


def _legacy_aliases(result: dict, request: ExecutionRequest) -> dict:
    """Keep current Developer Prompt and VS Code consumers operational."""
    metadata, planning, repository = result["metadata"], result["planningContext"], result["repositoryContext"]
    result.update({"packageId": metadata["packageId"], "generatedAt": metadata["generatedAt"], "storyId": request.story_id or None, "taskId": request.task_id or None,
        "knowledgeVersion": metadata["knowledgeVersion"], "repositorySnapshotVersion": metadata["repositorySnapshotVersion"],
        "businessContext": {"epicBusinessGoal": planning["businessGoal"], "storyTitle": (planning["story"] or {}).get("title", ""), "taskObjective": result["implementationGuidance"]["implementationObjective"]},
        "implementationBoundary": {"inScope": result["implementationGuidance"]["implementationBoundaries"], "blockedModules": result["implementationGuidance"]["blockedModules"], "blockedFlows": result["implementationGuidance"]["blockedFlows"], "allowedModules": repository["relevantModules"]},
        "acceptanceMapping": result["validationGuidance"]["acceptanceMapping"], "suggestedTests": result["qaGuidance"]["suggestedTests"],
        "readiness": {"executionReadinessScore": metadata["executionReadiness"], "status": metadata["status"], "repositoryMode": repository["repositoryMode"]}})
    return result
