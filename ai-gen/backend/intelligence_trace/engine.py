"""Intelligence Trace engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .collector import TraceCollector
from .diagnostics import TraceDiagnostics
from .repository import TraceRepository
from .search import TraceSearch
from .types import TRACE_STAGES, normalize_trace


class TraceEngine:
    def __init__(self, storage_path: Path | None = None) -> None:
        self.repository = TraceRepository(storage_path)
        self.collector = TraceCollector()
        self.searcher = TraceSearch()
        self.diagnostics = TraceDiagnostics()

    def record(self, trace: dict[str, Any]) -> dict[str, Any]:
        return self.repository.save(normalize_trace(trace))

    def record_decision(self, **kwargs: Any) -> dict[str, Any]:
        trace = self.collector.decision_trace(**kwargs)
        return self.repository.save(trace)

    def list_traces(self, project_id: str = "", artifact_id: str = "", stage: str = "") -> dict[str, Any]:
        traces = self.repository.list()
        filtered = [
            trace for trace in traces
            if (not project_id or trace.get("projectId") == project_id)
            and (not artifact_id or trace.get("artifactId") == artifact_id)
            and (not stage or trace.get("stage") == stage)
        ]
        return {"traces": filtered, "count": len(filtered), "diagnostics": self.diagnostics.summarize(filtered)}

    def search(self, query: dict[str, Any]) -> dict[str, Any]:
        return self.searcher.search(self.repository.list(), query)

    def timeline(self, artifact_id: str = "", project_id: str = "") -> dict[str, Any]:
        traces = self.list_traces(project_id=project_id, artifact_id=artifact_id).get("traces", [])
        steps = []
        for stage in TRACE_STAGES:
            stage_traces = [trace for trace in traces if trace.get("stage") == stage]
            steps.append({
                "stage": stage,
                "count": len(stage_traces),
                "traces": stage_traces,
                "status": "Complete" if stage_traces else "Pending",
            })
        return {"timeline": steps, "count": len(traces)}

    def explain(self, artifact_id: str, decision: str = "", project_id: str = "") -> dict[str, Any]:
        query = {"artifactId": artifact_id, "decision": decision, "projectId": project_id}
        matches = self.search(query).get("traces", [])
        return {
            "artifactId": artifact_id,
            "decision": decision,
            "traces": matches,
            "timeline": self.timeline(artifact_id, project_id).get("timeline", []),
            "count": len(matches),
        }

    def diagnostics_summary(self) -> dict[str, Any]:
        return self.diagnostics.summarize(self.repository.list())
