from __future__ import annotations

from typing import Any

from .capability_context import CapabilityContext, CapabilityMatch
from .capability_deduplicator import dedupe_capabilities
from .capability_diagnostics import CapabilityDiagnostics
from .capability_matcher import match_applications, match_capabilities, match_dependencies, match_flows, match_modules
from .capability_rejection import reject_irrelevant_capabilities


class CapabilityEngine:
    def build_capability_context(self, intent_model: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        diagnostics = CapabilityDiagnostics()
        knowledge_registry = _knowledge_registry(options)
        project_profile = options.get("project_profile") or options.get("projectProfile") or {}

        raw_matches = match_capabilities(intent_model, diagnostics)
        accepted, rejected_by_rules = reject_irrelevant_capabilities(raw_matches, intent_model, diagnostics)
        deduped, rejected_duplicates = dedupe_capabilities(accepted, diagnostics)
        if not deduped:
            fallback = CapabilityMatch(
                name="Operational Awareness",
                type="capability",
                confidence=0.42,
                reason="No accepted capability remained after rejection; fallback selected for diagnostics only.",
                source="fallback_rules",
                evidence=[],
            )
            deduped = [fallback]
            diagnostics.add("Fallback capability selected after rejection rules removed all matches.")

        primary = deduped[0]
        secondary = deduped[1:8]
        modules = match_modules(deduped, intent_model, knowledge_registry, diagnostics)
        flows = match_flows(deduped, intent_model, knowledge_registry, diagnostics)
        applications = match_applications(intent_model, project_profile, diagnostics)
        dependencies = match_dependencies(modules, flows, knowledge_registry, diagnostics)
        confidence = _confidence(primary, secondary, modules, flows, knowledge_registry)

        context = CapabilityContext(
            work_item_id=intent_model.get("workItemId") or intent_model.get("work_item_id"),
            work_item_type=str(intent_model.get("workItemType") or intent_model.get("work_item_type") or "Story"),
            primary_capability=primary,
            secondary_capabilities=secondary,
            rejected_capabilities=[*rejected_by_rules, *rejected_duplicates],
            relevant_modules=modules,
            relevant_flows=flows,
            relevant_applications=applications,
            relevant_dependencies=dependencies,
            capability_reasoning=diagnostics.reasoning,
            confidence=confidence,
        )
        return context.to_dict()


def build_capability_context(intent_model: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
    return CapabilityEngine().build_capability_context(intent_model, options)


def buildCapabilityContext(intent_model: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_capability_context(intent_model, options)


def _knowledge_registry(options: dict[str, Any]) -> dict[str, Any]:
    registry = options.get("knowledge_registry") or options.get("knowledgeRegistry")
    if isinstance(registry, dict):
        return registry
    profile = options.get("project_profile") or options.get("projectProfile") or {}
    if isinstance(profile, dict) and isinstance(profile.get("knowledge_registry"), dict):
        return profile["knowledge_registry"]
    snapshot = options.get("repository_snapshot") or options.get("repositorySnapshot") or {}
    if isinstance(snapshot, dict) and isinstance(snapshot.get("knowledge_registry"), dict):
        return snapshot["knowledge_registry"]
    return {}


def _confidence(
    primary: CapabilityMatch,
    secondary: list[CapabilityMatch],
    modules: list[CapabilityMatch],
    flows: list[CapabilityMatch],
    knowledge_registry: dict[str, Any],
) -> float:
    score = primary.confidence * 0.55
    score += min(len(secondary), 4) * 0.04
    score += min(len(modules), 4) * 0.035
    score += min(len(flows), 4) * 0.035
    if knowledge_registry:
        score += 0.08
    return round(min(score, 0.96), 2)

