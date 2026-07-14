"""Central deterministic context orchestration pipeline."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Protocol

from backend.platform.shared import JsonMapStore

from .budgeting import ContextBudgetManager, IContextBudgetManager
from .filtering import ContextFilter
from .models import ContextCandidate, ContextRequest, ContextSourceResult, ContextSourceType
from .ranking import ContextRankingEngine, IContextRankingEngine
from .sources import IContextSource, item_content


PURPOSES = {"Planning", "ImplementationPackage", "DeveloperPrompt", "Validation", "QA", "PRReview", "AgentExecution"}


class IContextOrchestrator(Protocol):
    def orchestrate(self, request: ContextRequest) -> dict[str, Any]: ...


class ContextOrchestrator:
    def __init__(self, *, sources: list[IContextSource], store: JsonMapStore, ranking_engine: IContextRankingEngine | None = None, context_filter: ContextFilter | None = None, budget_manager: IContextBudgetManager | None = None, platform: Any | None = None) -> None:
        self.sources = sources
        self.store = store
        self.ranking_engine = ranking_engine or ContextRankingEngine()
        self.context_filter = context_filter or ContextFilter()
        self.budget_manager = budget_manager or ContextBudgetManager()
        self.platform = platform

    def orchestrate(self, request: ContextRequest) -> dict[str, Any]:
        started = time.perf_counter()
        self._validate(request)
        self._event("ContextOrchestrationRequested", request, {"purpose": request.purpose})
        results: list[ContextSourceResult] = []
        warnings: list[str] = []
        blockers: list[str] = []
        try:
            for source in self.sources:
                if not self._enabled(source.source_type, request):
                    continue
                try:
                    result = source.retrieve(request)
                except Exception as exc:  # one optional source must not destroy permitted context
                    result = ContextSourceResult(source.source_type, False, "Unavailable", warnings=[f"{source.source_type.value} source failed: {type(exc).__name__}"], diagnostics={"error": str(exc)[:300]})
                results.append(result)
                warnings.extend(result.warnings)
            stale_sources = [result.source_type.value for result in results if result.available and result.freshness == "Stale"]
            if stale_sources:
                warnings.append(f"Stale context detected for: {', '.join(stale_sources)}. Refresh is recommended before implementation.")
            candidates = self._normalize(request, results)
            ranked = self.ranking_engine.rank(request, candidates)
            filtered, rejected = self.context_filter.apply(request, ranked)
            selected, omitted, budget = self.budget_manager.apply(request, filtered)
            rejected.extend(omitted)
            if omitted:
                warnings.append(f"{len(omitted)} context candidate(s) omitted because of token budget.")
            if not selected:
                blockers.append("No context candidates satisfied the request boundaries and token budget.")
            confidence = round(sum(c.confidence_score for c in selected) / len(selected), 3) if selected else 0.0
            status = "Blocked" if blockers else "NeedsReview" if warnings or confidence < float(request.options.get("minimumConfidence", 0.5)) else "Ready"
            duration = round((time.perf_counter() - started) * 1000, 2)
            result = {
                "requestId": request.request_id, "correlationId": request.correlation_id, "purpose": request.purpose,
                "capsuleId": f"capsule_{request.request_id}", "capsuleVersion": "3.5",
                "projectId": request.project_id, "repositoryId": request.repository_id or None,
                "repositorySnapshotVersion": request.repository_snapshot_version or self._snapshot_version(results) or None,
                "planningVersion": self._source_version(results, ContextSourceType.PLANNING),
                "knowledgeVersion": self._source_version(results, ContextSourceType.KNOWLEDGE_REGISTRY),
                "engineeringMemoryVersion": self._source_version(results, ContextSourceType.ENGINEERING_MEMORY),
                "freshnessStatus": self._overall_freshness(results),
                "status": status, "selectedContext": [c.to_dict() for c in selected],
                "rejectedContext": [{"candidate": item["candidate"].to_dict(), "reason": item["reason"]} for item in rejected],
                "sourceSummary": self._source_summary(results, selected, rejected), "tokenBudget": budget,
                "confidence": confidence, "warnings": list(dict.fromkeys(warnings)), "blockers": blockers,
                "diagnostics": {"rankingVersion": self.ranking_engine.version, "budgetPolicyVersion": self.budget_manager.version, "durationMs": duration, "sources": {r.source_type.value: r.diagnostics for r in results}, "retrievalCounts": {r.source_type.value: 1 for r in results}, "contextOrchestrationRequests": 1},
            }
            self._save(result)
            event = "ContextOrchestrationCompleted" if status == "Ready" else "ContextOrchestrationNeedsReview"
            self._event(event, request, {"status": status, "durationMs": duration, "selectedSourceCounts": {s["sourceType"]: s["selectedCount"] for s in result["sourceSummary"]}, "tokenUsage": budget, "warnings": result["warnings"]})
            self._activity_and_audit(request, result)
            return result
        except Exception as exc:
            self._event("ContextOrchestrationFailed", request, {"failureReason": str(exc)[:300]})
            raise

    def get(self, request_id: str) -> dict[str, Any] | None:
        return self.store.read().get(request_id)

    def diagnostics(self, request_id: str) -> dict[str, Any] | None:
        result = self.get(request_id)
        if not result: return None
        return {"requestId": request_id, "correlationId": result["correlationId"], "status": result["status"], "sourceSummary": result["sourceSummary"], "tokenBudget": result["tokenBudget"], "warnings": result["warnings"], "blockers": result["blockers"], "diagnostics": result["diagnostics"]}

    def health(self) -> dict[str, Any]:
        return {"contextOrchestratorStatus": "healthy", "rankingEngineStatus": "healthy", "budgetManagerStatus": "healthy", "contextSourceStatus": {source.source_type.value: "healthy" for source in self.sources}}

    def _validate(self, request: ContextRequest) -> None:
        missing = [name for name, value in (("requestId", request.request_id), ("correlationId", request.correlation_id), ("projectId", request.project_id)) if not value]
        if missing: raise ValueError(f"Missing required field(s): {', '.join(missing)}")
        if request.purpose not in PURPOSES: raise ValueError(f"Unsupported context purpose '{request.purpose}'.")

    def _normalize(self, request: ContextRequest, results: list[ContextSourceResult]) -> list[ContextCandidate]:
        output: list[ContextCandidate] = []
        for result in results:
            freshness = {"Fresh": 1.0, "Stale": 0.4, "Unknown": 0.6, "Unavailable": 0.0}.get(result.freshness, 0.5)
            for index, raw in enumerate(result.items):
                item = raw if isinstance(raw, dict) else {"content": raw}
                content = item_content(item)
                identity = str(item.get("id") or item.get("candidateId") or item.get("path") or item.get("title") or index)
                output.append(ContextCandidate(
                    candidate_id=f"{result.source_type.value.lower()}_{hashlib.sha256(identity.encode()).hexdigest()[:12]}",
                    source_type=result.source_type, category=str(item.get("category") or self._category(result.source_type)),
                    title=str(item.get("title") or item.get("name") or item.get("path") or result.source_type.value), content=content,
                    relevance_score=self._score(item, "relevanceScore", "rankingScore", default=0.7),
                    confidence_score=self._score(item, "confidenceScore", "confidence", default=0.75), freshness_score=freshness,
                    evidence_score=self._score(item, "evidenceScore", "score", default=0.9 if item.get("directEvidence") else 0.6),
                    provenance={"projectId": item.get("projectId") or request.project_id, "repositoryId": request.repository_id or None, "snapshotVersion": result.version or None, "artifactId": item.get("artifactId") or request.artifact.get("artifactId"), "memoryId": item.get("id") if result.source_type == ContextSourceType.ENGINEERING_MEMORY else None, "filePath": item.get("path"), "sourceVersion": item.get("version")},
                    reasons=list(item.get("reasons") or item.get("matchReasons") or []), warnings=list(item.get("warnings") or []), metadata=item,
                ))
        return output

    @staticmethod
    def _score(item: dict, *keys: str, default: float) -> float:
        value = next((item.get(k) for k in keys if item.get(k) is not None), default)
        number = float(value or 0); return max(0.0, min(1.0, number / 100 if number > 1 else number))

    @staticmethod
    def _category(source: ContextSourceType) -> str:
        return {ContextSourceType.PLANNING: "Planning", ContextSourceType.REPOSITORY: "Module", ContextSourceType.ENGINEERING_MEMORY: "Memory", ContextSourceType.ENGINEERING_STANDARDS: "Standard", ContextSourceType.VALIDATION_HISTORY: "Validation", ContextSourceType.LOCAL_WORKSPACE: "File"}.get(source, "Knowledge")

    @staticmethod
    def _enabled(source: ContextSourceType, request: ContextRequest) -> bool:
        key = {ContextSourceType.REPOSITORY: "includeRepository", ContextSourceType.KNOWLEDGE_REGISTRY: "includeKnowledge", ContextSourceType.ENGINEERING_MEMORY: "includeMemory", ContextSourceType.ENGINEERING_STANDARDS: "includeStandards", ContextSourceType.PLANNING: "includePlanningLineage", ContextSourceType.VALIDATION_HISTORY: "includeValidationHistory"}.get(source)
        return not key or request.options.get(key, True)

    @staticmethod
    def _snapshot_version(results: list[ContextSourceResult]) -> str:
        return next((r.version for r in results if r.source_type == ContextSourceType.REPOSITORY and r.version), "")

    @staticmethod
    def _source_version(results: list[ContextSourceResult], source_type: ContextSourceType) -> str:
        return next((r.version for r in results if r.source_type == source_type and r.version), "")

    @staticmethod
    def _overall_freshness(results: list[ContextSourceResult]) -> str:
        available = [result.freshness for result in results if result.available]
        if not available:
            return "Unavailable"
        if any(value == "Stale" for value in available):
            return "Stale"
        if all(value == "Fresh" for value in available):
            return "Fresh"
        return "Unknown"

    @staticmethod
    def _source_summary(results: list[ContextSourceResult], selected: list[ContextCandidate], rejected: list[dict]) -> list[dict]:
        return [{"sourceType": result.source_type.value, "available": result.available, "selectedCount": sum(c.source_type == result.source_type for c in selected), "rejectedCount": sum(x["candidate"].source_type == result.source_type for x in rejected), "version": result.version or None, "freshness": result.freshness} for result in results]

    def _save(self, result: dict[str, Any]) -> None:
        values = self.store.read(); values[result["requestId"]] = result; self.store.write(values)

    def _event(self, event_type: str, request: ContextRequest, payload: dict) -> None:
        if self.platform: self.platform.events.publish({"eventType": event_type, "source": "API", "projectId": request.project_id, "repositoryId": request.repository_id, "correlationId": request.correlation_id, "payload": {"requestId": request.request_id, **payload}})

    def _activity_and_audit(self, request: ContextRequest, result: dict) -> None:
        if not self.platform: return
        self.platform.activity.add_activity({"activityType": "ContextOrchestration", "title": f"Context orchestration {result['status']}", "description": f"Selected {len(result['selectedContext'])} context candidates.", "source": "API", "projectId": request.project_id, "repositoryId": request.repository_id, "correlationId": request.correlation_id, "metadata": {"requestId": request.request_id, "durationMs": result["diagnostics"]["durationMs"], "tokenUsage": result["tokenBudget"]}})
        self.platform.audit.record({"action": "ContextOrchestrated", "actor": "system", "source": "API", "targetType": "ContextRequest", "targetId": request.request_id, "after": {"status": result["status"], "selectedCount": len(result["selectedContext"])}, "correlationId": request.correlation_id})
