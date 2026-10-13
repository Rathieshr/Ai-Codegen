"""Build workflow-safe Engineering Memory context."""

from __future__ import annotations

from typing import Any

from .engine import EngineeringMemoryEngine
from .types import clean, string_list, unique


SAFE_MEMORY_STATUSES = {"Approved", "Indexed", "Available"}
MIN_MEMORY_CONFIDENCE = 0.55


class MemoryContextBuilder:
    def __init__(self, engine: EngineeringMemoryEngine | None = None) -> None:
        self.engine = engine or EngineeringMemoryEngine()

    def build(
        self,
        *,
        purpose: str,
        project_id: str,
        artifact_type: str,
        work_item: dict[str, Any],
        modules: list[str] | None = None,
        flows: list[str] | None = None,
        acceptance_criteria: list[str] | None = None,
        repository_files: list[str] | None = None,
        capability: str = "",
    ) -> dict[str, Any]:
        query = {
            "projectId": project_id,
            "query": " ".join(
                [
                    clean(work_item.get("title")),
                    clean(work_item.get("description")),
                    capability,
                    " ".join(acceptance_criteria or []),
                    " ".join(modules or []),
                    " ".join(flows or []),
                    " ".join(repository_files or []),
                ]
            ),
            "module": modules or [],
            "flow": flows or [],
            "repository": repository_files or [],
            "includeDrafts": True,
            "limit": 20,
        }
        if artifact_type:
            query["artifactType"] = artifact_type
        response = self.engine.search(query)
        candidates = response.get("results", []) if isinstance(response, dict) else []
        ranked: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        for memory in candidates:
            score, reasons, exclusions = self._rank_memory(
                memory,
                project_id=project_id,
                artifact_type=artifact_type,
                modules=modules or [],
                flows=flows or [],
                repository_files=repository_files or [],
                capability=capability,
            )
            if exclusions:
                excluded.append({"id": memory.get("id"), "title": memory.get("title"), "reasons": exclusions})
                continue
            ranked.append({
                **_memory_summary(memory),
                "rankingScore": score,
                "retrievalReasons": reasons,
            })
        ranked.sort(key=lambda item: (item.get("rankingScore", 0), item.get("confidence", 0)), reverse=True)
        selected = ranked[:5]
        return {
            "purpose": purpose,
            "query": query,
            "relevantMemories": selected,
            "matchedPatterns": [memory for memory in selected if memory.get("category") == "Pattern Memory"],
            "previousSuccessfulArtifacts": [
                memory for memory in selected
                if memory.get("category") in {"Execution Memory", "QA Memory"} or memory.get("artifactType") in {"Execution Package", "Test Suite"}
            ],
            "knownRisks": _extract_tagged_lines(selected, ["risk", "warning", "regression", "validation"]),
            "reusableAcceptanceCriteria": _extract_tagged_lines(selected, ["acceptance", "criteria", "story"]),
            "reusableTests": _extract_tagged_lines(selected, ["test", "qa", "regression", "permission"]),
            "confidence": _context_confidence(selected),
            "retrievalReasons": _unique_reasons(selected),
            "excludedMemory": excluded[:8],
            "diagnostics": {
                "memoryQuery": query,
                "memoryMatches": len(selected),
                "candidateCount": len(candidates),
                "excludedCount": len(excluded),
                "staleMemoryWarnings": [item for item in excluded if "deprecated_or_archived" in item.get("reasons", [])],
            },
        }

    def _rank_memory(
        self,
        memory: dict[str, Any],
        *,
        project_id: str,
        artifact_type: str,
        modules: list[str],
        flows: list[str],
        repository_files: list[str],
        capability: str,
    ) -> tuple[int, list[str], list[str]]:
        status = clean(memory.get("approvalStatus"))
        confidence = float(memory.get("confidence") or 0)
        exclusions: list[str] = []
        if project_id and clean(memory.get("projectId")) not in {project_id, "default"}:
            exclusions.append("different_project")
        if status not in SAFE_MEMORY_STATUSES:
            exclusions.append("not_approved_indexed_or_available")
        if status in {"Deprecated", "Archived"}:
            exclusions.append("deprecated_or_archived")
        if confidence < MIN_MEMORY_CONFIDENCE:
            exclusions.append("low_confidence")
        if _source_failed(memory):
            exclusions.append("failed_or_rejected_source")
        index = memory.get("index") if isinstance(memory.get("index"), dict) else {}
        memory_modules = {item.lower() for item in string_list(index.get("modules")) + string_list(memory.get("knowledgeReferences"))}
        memory_flows = {item.lower() for item in string_list(index.get("flows")) + string_list(memory.get("knowledgeReferences"))}
        memory_repository = {item.lower() for item in string_list(index.get("repository"))}
        has_boundary = bool(modules or flows or repository_files)
        if has_boundary:
            module_match = _overlap(modules, memory_modules)
            flow_match = _overlap(flows, memory_flows)
            repository_match = _overlap(repository_files, memory_repository)
            if not any([module_match, flow_match, repository_match, _capability_match(capability, memory)]):
                exclusions.append("outside_current_planning_boundary")
        if exclusions:
            return 0, [], exclusions
        score = int(memory.get("searchScore") or 0)
        reasons = list(memory.get("matchReasons") or [])
        if clean(memory.get("projectId")) == project_id:
            score += 20
            reasons.append("same_project")
        if clean(memory.get("artifactType")).lower() == artifact_type.lower():
            score += 8
            reasons.append("same_artifact_type")
        if _overlap(modules, memory_modules):
            score += 14
            reasons.append("same_module")
        if _overlap(flows, memory_flows):
            score += 12
            reasons.append("same_flow")
        if _overlap(repository_files, memory_repository):
            score += 10
            reasons.append("same_repository_file")
        if _capability_match(capability, memory):
            score += 16
            reasons.append("same_capability")
        if int(memory.get("usageCount") or 0) > 0:
            score += 4
            reasons.append("recent_successful_use")
        score += int(confidence * 10)
        return score, unique(reasons), []


def _memory_summary(memory: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": clean(memory.get("id")),
        "projectId": clean(memory.get("projectId")),
        "category": clean(memory.get("category")),
        "title": clean(memory.get("title")),
        "summary": clean(memory.get("summary")),
        "contentPreview": clean(memory.get("content"))[:360],
        "artifactType": clean(memory.get("artifactType")),
        "artifactId": clean(memory.get("artifactId")),
        "tags": string_list(memory.get("tags")),
        "confidence": float(memory.get("confidence") or 0),
        "approvalStatus": clean(memory.get("approvalStatus")),
        "version": int(memory.get("version") or 1),
        "knowledgeReferences": string_list(memory.get("knowledgeReferences")),
        "graphReferences": string_list(memory.get("graphReferences")),
    }


def _source_failed(memory: dict[str, Any]) -> bool:
    source = memory.get("source") if isinstance(memory.get("source"), dict) else {}
    text = " ".join(string_list([source.get("status"), source.get("validationStatus"), source.get("approvalStatus")])).lower()
    return any(word in text for word in ["failed", "rejected", "blocked", "timeout", "parse_error"])


def _overlap(values: list[str], candidates: set[str]) -> bool:
    return bool({item.lower() for item in string_list(values)} & candidates)


def _capability_match(capability: str, memory: dict[str, Any]) -> bool:
    text = f"{memory.get('title', '')} {memory.get('summary', '')} {' '.join(string_list(memory.get('tags')))}".lower()
    return bool(capability and capability.lower() in text)


def _extract_tagged_lines(memories: list[dict[str, Any]], terms: list[str]) -> list[str]:
    output: list[str] = []
    for memory in memories:
        text = f"{memory.get('title')}: {memory.get('summary')} {memory.get('contentPreview', '')}"
        lowered = text.lower()
        if any(term in lowered for term in terms):
            output.append(clean(text))
    return unique(output)[:8]


def _context_confidence(memories: list[dict[str, Any]]) -> float:
    if not memories:
        return 0.0
    return round(sum(float(memory.get("confidence") or 0) for memory in memories) / len(memories), 2)


def _unique_reasons(memories: list[dict[str, Any]]) -> list[str]:
    return unique([
        reason
        for memory in memories
        for reason in string_list(memory.get("retrievalReasons"))
    ])
