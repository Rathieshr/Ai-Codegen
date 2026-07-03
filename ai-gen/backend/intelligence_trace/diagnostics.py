"""Trace diagnostics."""

from __future__ import annotations

from typing import Any


class TraceDiagnostics:
    def summarize(self, traces: list[dict[str, Any]]) -> dict[str, Any]:
        by_stage: dict[str, int] = {}
        by_source: dict[str, int] = {}
        for trace in traces:
            stage = str(trace.get("stage") or "Unknown")
            source = str(trace.get("source") or stage)
            by_stage[stage] = by_stage.get(stage, 0) + 1
            by_source[source] = by_source.get(source, 0) + 1
        return {
            "traceCount": len(traces),
            "byStage": by_stage,
            "bySource": by_source,
            "latestTrace": traces[-1] if traces else {},
        }
