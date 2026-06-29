from __future__ import annotations

from typing import Any


def build_diagnostics(
    *,
    intent_keywords: list[str],
    selected_capabilities: list[dict[str, Any]],
    selected_modules: list[dict[str, Any]],
    selected_flows: list[dict[str, Any]],
    selected_applications: list[dict[str, Any]],
    selected_dependencies: list[dict[str, Any]],
    selected_standards: list[dict[str, Any]],
    rejected_context: list[dict[str, Any]],
    duplicate_risks: list[dict[str, Any]],
    confidence: float,
    token_estimate: int,
) -> dict[str, Any]:
    return {
        "intentKeywords": intent_keywords,
        "selectedCapabilities": selected_capabilities,
        "selectedModules": selected_modules,
        "selectedFlows": selected_flows,
        "selectedApplications": selected_applications,
        "selectedDependencies": selected_dependencies,
        "selectedStandards": selected_standards,
        "rejectedContext": rejected_context,
        "duplicateRisks": duplicate_risks,
        "confidence": round(confidence, 2),
        "tokenEstimate": token_estimate,
    }
