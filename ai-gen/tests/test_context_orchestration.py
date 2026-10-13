from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.context_orchestration import (
    ContextBudgetManager,
    ContextCandidate,
    ContextFilter,
    ContextOrchestrator,
    ContextRankingEngine,
    ContextRequest,
    ContextSourceResult,
    ContextSourceType,
    PlanningContextSource,
)
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore


class Source:
    def __init__(self, source_type, items, *, available=True, freshness="Fresh", diagnostics=None):
        self.source_type, self.items = source_type, items
        self.available, self.freshness = available, freshness
        self.diagnostics = diagnostics or {}

    def retrieve(self, request):
        return ContextSourceResult(self.source_type, self.available, self.freshness, items=self.items, diagnostics=self.diagnostics)


def request(**changes):
    value = dict(request_id="ctx-1", correlation_id="corr-1", purpose="Planning", project_id="project-a", artifact={"artifactId": 1, "artifactType": "Story", "title": "Device health"}, options={"maxTokens": 1200})
    value.update(changes)
    return ContextRequest(**value)


class ContextOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.platform = PlatformFoundation(Path(self.tmp.name) / "platform")

    def tearDown(self): self.tmp.cleanup()

    def orchestrator(self, sources):
        engine = ContextOrchestrator(sources=sources, store=JsonMapStore(Path(self.tmp.name) / "requests.json"), platform=self.platform)
        self.platform.context_orchestrator = engine
        return engine

    def test_planning_only_preserves_correlation_and_records_platform_entries(self):
        engine = self.orchestrator([PlanningContextSource()])
        result = engine.orchestrate(request())
        self.assertEqual(result["correlationId"], "corr-1")
        self.assertEqual(result["selectedContext"][0]["sourceType"], "Planning")
        self.assertEqual(engine.get("ctx-1"), result)
        self.assertGreater(self.platform.events.list_recent(event_type="ContextOrchestrationCompleted")["count"], 0)
        self.assertGreater(self.platform.audit.by_correlation("corr-1")["count"], 0)

    def test_unavailable_repository_keeps_planning(self):
        repository = Source(ContextSourceType.REPOSITORY, [], available=False, freshness="Unavailable", diagnostics={"repositoryMode": "Unavailable"})
        result = self.orchestrator([repository, PlanningContextSource()]).orchestrate(request(repository_id="repo"))
        self.assertEqual([item["sourceType"] for item in result["selectedContext"]], ["Planning"])

    def test_knowledge_snapshot_contains_modules_not_invented_files(self):
        repository = Source(ContextSourceType.REPOSITORY, [{"title": "Telemetry", "content": "Telemetry", "category": "Module", "broadContext": True}], diagnostics={"repositoryMode": "KnowledgeSnapshot"})
        result = self.orchestrator([repository]).orchestrate(request(repository_id="repo"))
        self.assertEqual(result["selectedContext"][0]["category"], "Module")
        self.assertIsNone(result["selectedContext"][0]["provenance"]["filePath"])

    def test_filter_rejects_blocked_rejected_duplicate_and_cross_project_memory(self):
        base = ContextCandidate("a", ContextSourceType.PLANNING, "Planning", "A", "same", confidence_score=.9, metadata={"module": "blocked"})
        rejected_plan = ContextCandidate("b", ContextSourceType.PLANNING, "Planning", "B", "two", confidence_score=.9, metadata={"rejectedPlanning": True})
        memory = ContextCandidate("c", ContextSourceType.ENGINEERING_MEMORY, "Memory", "C", "three", confidence_score=.9, provenance={"projectId": "project-b"})
        duplicate1 = ContextCandidate("d", ContextSourceType.PLANNING, "Planning", "D", "dupe", confidence_score=.9)
        duplicate2 = ContextCandidate("e", ContextSourceType.PLANNING, "Planning", "E", "dupe", confidence_score=.9)
        selected, rejected = ContextFilter().apply(request(options={"blockedModules": ["blocked"]}), [base, rejected_plan, memory, duplicate1, duplicate2])
        self.assertEqual([item.candidate_id for item in selected], ["d"])
        self.assertEqual({item["reason"] for item in rejected}, {"blocked_module", "rejected_planning_context", "cross_project_memory_not_permitted", "duplicate_candidate"})

    def test_ranking_prefers_direct_repository_evidence(self):
        direct = ContextCandidate("direct", ContextSourceType.REPOSITORY, "File", "Direct", "x", relevance_score=.7, evidence_score=1, metadata={"directEvidence": True})
        inferred = ContextCandidate("inferred", ContextSourceType.REPOSITORY, "Module", "Inferred", "y", relevance_score=.7, evidence_score=.2)
        ranked = ContextRankingEngine().rank(request(), [inferred, direct])
        self.assertEqual(ranked[0].candidate_id, "direct")

    def test_budget_omits_low_value_whole_candidates_and_stays_within_small_limit(self):
        candidates = [ContextCandidate(str(i), ContextSourceType.PLANNING, "Planning", str(i), "x" * 120, final_score=1 - i / 10) for i in range(5)]
        selected, omitted, summary = ContextBudgetManager(system_reserve=20, output_reserve=20).apply(request(options={"maxTokens": 100, "reservedTokens": 20}), candidates)
        self.assertTrue(selected)
        self.assertTrue(omitted)
        self.assertLessEqual(summary["selected"] + summary["reserved"], summary["maximum"])
        self.assertEqual(selected[0].content, "x" * 120)


if __name__ == "__main__": unittest.main()
