from __future__ import annotations

from typing import Any

from .confidence_scorer import DEFAULT_DISCOVERY_THRESHOLD, score_candidates
from .intent_analyzer import IntentAnalyzer
from .knowledge_matcher import discover_knowledge_candidates
from .memory_matcher import apply_memory_scores, resolve_memory_context
from .recommendation_builder import build_recommendations
from .repository_matcher import apply_repository_scores


class CapabilityDiscoveryEngine:
    def __init__(self) -> None:
        self.intent_analyzer = IntentAnalyzer()

    def discover(self, intent_model: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        knowledge_registry = _knowledge_registry(options)
        repository_snapshot = _mapping(options.get("repository_snapshot") or options.get("repositorySnapshot"))
        threshold = int(options.get("capability_threshold") or options.get("capabilityThreshold") or DEFAULT_DISCOVERY_THRESHOLD)
        intent_summary = self.intent_analyzer.analyze(intent_model)
        candidates = discover_knowledge_candidates(intent_summary, knowledge_registry)
        apply_repository_scores(candidates, repository_snapshot, knowledge_registry)
        memory_context = resolve_memory_context(intent_summary, options)
        apply_memory_scores(candidates, memory_context)
        scored = score_candidates(candidates, threshold=threshold)
        built = build_recommendations(scored, threshold=threshold, max_items=6)
        return {
            "intentSummary": intent_summary,
            "memoryContext": memory_context,
            "accepted": built["accepted"],
            "rejected": built["rejected"],
            "report": built["report"],
        }


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


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
