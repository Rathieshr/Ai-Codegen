"""Markdown rendering for Prompt Intelligence benchmark reports."""

from __future__ import annotations

from typing import Any


def render_benchmark_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Prompt Intelligence Benchmark",
        "",
        f"Generated: {report['generatedAt']}",
        "",
        f"Readiness: **{report['readiness']['status']}**",
        "",
        "## Quality Gates",
        "",
        "| Gate | Status | Details |",
        "| --- | --- | --- |",
    ]
    for gate in report["qualityGates"]:
        lines.append(f"| {gate['name']} | {'PASS' if gate['passed'] else 'FAIL'} | {gate['details']} |")
    lines.extend(["", "## Repository Scenarios", "", "| Scenario | Mode | Files | Status | Duration |", "| --- | --- | ---: | --- | ---: |"])
    for scenario in report["repositoryScenarios"]:
        lines.append(
            f"| {scenario['id']} ({scenario['name']}) | {scenario['repositoryMode']} | {scenario['fileCount']} | "
            f"{scenario['status']} | {scenario['durationMs']:.2f} ms |"
        )
    lines.extend(["", "## Model Adapters", "", "| Model | Status | Tokens | Duration |", "| --- | --- | ---: | ---: |"])
    for adapter in report["modelAdapters"]:
        lines.append(f"| {adapter['modelId']} | {adapter['status']} | {adapter['estimatedTokens']} | {adapter['durationMs']:.2f} ms |")
    lines.extend(["", "## Token Budgets", "", "| Budget | Safety Gate | Engine Result | Prompt Tokens | Remaining |", "| ---: | --- | --- | ---: | ---: |"])
    for budget in report["tokenBudgets"]:
        lines.append(
            f"| {budget['budgetTokens']} | {budget['status']} | {budget['budgetStatus']} | "
            f"{budget['estimatedTokens']} | {budget['remainingBudget']} |"
        )
    cache = report["cache"]
    lines.extend([
        "",
        "## Cache",
        "",
        f"- First request: {cache['firstStatus']}",
        f"- Repeated request: {cache['secondStatus']}",
        f"- Hit rate: {cache['metrics']['hitRate']}%",
        f"- Generations avoided: {cache['metrics']['generationsAvoided']}",
        f"- Estimated tokens saved: {cache['metrics']['estimatedTokensSaved']}",
        "",
        "## Routing And Diagnostics",
        "",
        f"- Routing rules passed: {report['routing']['passed']}/{report['routing']['total']}",
        f"- Diagnostics status: {report['diagnostics']['status']}",
        f"- Regression stability: {report['regression']['status']}",
        "",
        "## Performance",
        "",
        "| Stage | Average | Maximum | Target | Status |",
        "| --- | ---: | ---: | ---: | --- |",
    ])
    for stage, value in report["performance"]["stages"].items():
        lines.append(
            f"| {stage} | {value['averageMs']:.2f} ms | {value['maximumMs']:.2f} ms | "
            f"{value['targetMs']:.2f} ms | {'PASS' if value['withinTarget'] else 'FAIL'} |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    if report["readiness"]["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {item}" for item in report["readiness"]["blockers"])
    return "\n".join(lines).strip() + "\n"
