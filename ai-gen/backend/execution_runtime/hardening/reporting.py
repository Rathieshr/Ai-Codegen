"""Markdown rendering for Runtime Hardening reports."""

from __future__ import annotations

from typing import Any


def render_runtime_benchmark_markdown(report: dict[str, Any]) -> str:
    readiness = report.get("readiness") or {}
    performance = report.get("performance") or {}
    lines = [
        "# Execution Runtime Benchmark",
        "",
        f"- Run: `{report.get('runId', '')}`",
        f"- Generated: {report.get('generatedAt', '')}",
        f"- Runtime version: {report.get('runtimeVersion', '')}",
        f"- Readiness: **{readiness.get('status', 'Unknown')}**",
        f"- Gates: {readiness.get('passedGates', 0)}/{readiness.get('totalGates', 0)} passed",
        "",
        "## Workloads",
        "",
        "| Scenario | Repository files | Prompt bytes | Response bytes | Latency ms | Peak memory MB | Status |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report.get("workloads") or []:
        lines.append(
            f"| {item.get('name')} | {item.get('repositoryFiles')} | {item.get('promptBytes')} | "
            f"{item.get('responseBytes')} | {item.get('latencyMs')} | {item.get('peakMemoryMb')} | {item.get('status')} |"
        )
    lines.extend([
        "",
        "## Performance",
        "",
        f"- Average latency: {performance.get('averageLatencyMs', 0)} ms",
        f"- P95 latency: {performance.get('p95LatencyMs', 0)} ms",
        f"- Maximum latency: {performance.get('maximumLatencyMs', 0)} ms",
        f"- CPU time: {performance.get('cpuTimeMs', 0)} ms",
        f"- Peak memory: {performance.get('peakMemoryMb', 0)} MB",
        f"- Maximum response size: {performance.get('maximumResponseBytes', 0)} bytes",
        f"- P95 queue time: {(report.get('concurrency') or {}).get('p95QueueTimeMs', 0)} ms",
        f"- Failure rate: {performance.get('failureRate', 0)}%",
        "",
        "## Quality Gates",
        "",
    ])
    for gate in report.get("qualityGates") or []:
        lines.append(f"- {'PASS' if gate.get('passed') else 'FAIL'}: {gate.get('name')} - {gate.get('details')}")
    lines.extend(["", "## Known Limitations", ""])
    for value in report.get("limitations") or []:
        lines.append(f"- {value}")
    return "\n".join(lines) + "\n"
