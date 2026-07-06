from __future__ import annotations

from typing import Any

from backend.engineering_memory import MemoryContextBuilder

from .capability_rules import CAPABILITY_RULES


def resolve_memory_context(intent_summary: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    provided = options.get("memory_context") or options.get("memoryContext")
    if isinstance(provided, dict):
        return provided
    project_id = _project_id(options)
    if not project_id:
        return {}
    builder = MemoryContextBuilder()
    return builder.build(
        purpose="capability_discovery",
        project_id=project_id,
        artifact_type=str(options.get("artifact_type") or options.get("work_item_type") or "Epic"),
        work_item={
            "title": intent_summary.get("title"),
            "description": intent_summary.get("description"),
        },
        modules=intent_summary.get("inferredModules") or [],
        flows=intent_summary.get("inferredFlows") or [],
        capability=str(intent_summary.get("primaryCapability") or ""),
    )


def apply_memory_scores(candidates: list[dict[str, Any]], memory_context: dict[str, Any]) -> None:
    relevant = memory_context.get("relevantMemories") if isinstance(memory_context, dict) else []
    memories = relevant if isinstance(relevant, list) else []
    for candidate in candidates:
        rules = CAPABILITY_RULES.get(str(candidate.get("name") or ""), {})
        capability = str(candidate.get("name") or "")
        hits: list[str] = []
        best_confidence = 0.0
        for memory in memories:
            if not isinstance(memory, dict):
                continue
            text = " ".join(
                str(memory.get(key) or "")
                for key in ["title", "summary", "contentPreview", "artifactType"]
            ).lower()
            tags = [str(item) for item in memory.get("tags", []) if item]
            if capability.lower() in text or any(keyword.lower() in text for keyword in rules.get("keywords", [])):
                hits.append(str(memory.get("title") or capability))
                best_confidence = max(best_confidence, float(memory.get("confidence") or 0))
            elif any(module.lower() in text for module in rules.get("modules", [])) or any(flow.lower() in text for flow in rules.get("flows", [])):
                hits.append(str(memory.get("title") or capability))
                best_confidence = max(best_confidence, float(memory.get("confidence") or 0))
            elif any(capability.lower() in str(tag).lower() for tag in tags):
                hits.append(str(memory.get("title") or capability))
                best_confidence = max(best_confidence, float(memory.get("confidence") or 0))
        candidate["memory_score"] = min(100, 30 + len(_unique(hits)) * 18 + round(best_confidence * 30)) if hits else 0
        candidate["memory_evidence"] = _unique(hits)[:4]


def _project_id(options: dict[str, Any]) -> str:
    for key in ["project_id", "projectId"]:
        value = options.get(key)
        if value:
            return str(value)
    profile = options.get("project_profile") or options.get("projectProfile") or {}
    if isinstance(profile, dict):
        for key in ["project_id", "projectId", "id", "project_name", "projectName", "name"]:
            value = profile.get(key)
            if value:
                return str(value)
    return ""


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(str(value).strip().split())
        key = cleaned.lower()
        if cleaned and key not in seen:
            output.append(cleaned)
            seen.add(key)
    return output
