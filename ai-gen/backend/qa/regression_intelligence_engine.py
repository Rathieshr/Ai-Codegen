"""Regression scope analysis."""

from __future__ import annotations

from typing import Any

from .qa_validation_rules import clean, string_list, unique


class RegressionIntelligenceEngine:
    def analyze(
        self,
        execution_package: dict[str, Any] | None = None,
        repository_snapshot: dict[str, Any] | None = None,
        engineering_graph: dict[str, Any] | None = None,
        implementation_validation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        package = execution_package or {}
        repository = package.get("repositoryContext") if isinstance(package.get("repositoryContext"), dict) else {}
        validation = implementation_validation or {}
        changed_files = validation.get("changedFiles") if isinstance(validation.get("changedFiles"), list) else []
        changed_modules = _names(repository.get("relevantModules"))
        affected_services = _names(repository.get("relevantServices"))
        affected_apis = _names(repository.get("relevantAPIs"))
        affected_flows = _names(repository.get("relevantFlows"))
        graph = engineering_graph or {}
        related_features = string_list(graph.get("related_features") or graph.get("features"))
        related_stories = string_list(graph.get("related_stories") or graph.get("stories"))
        regression_areas = unique([*changed_modules, *affected_services, *affected_apis, *affected_flows])
        priority = "High" if len(regression_areas) >= 4 or changed_files else "Medium" if regression_areas else "Low"
        return {
            "changedModules": changed_modules,
            "affectedServices": affected_services,
            "affectedAPIs": affected_apis,
            "affectedFlows": affected_flows,
            "relatedFeatures": related_features,
            "relatedStories": related_stories,
            "potentialRegressionAreas": regression_areas,
            "recommendedRegressionTests": [f"Run regression coverage for {area}" for area in regression_areas[:8]],
            "regressionPriority": priority,
            "changedFiles": [clean(item.get("path") or item.get("file")) for item in changed_files if isinstance(item, dict)],
        }


def _names(values: Any) -> list[str]:
    if isinstance(values, list):
        return unique([clean(value.get("name") or value.get("path")) if isinstance(value, dict) else clean(value) for value in values if clean(value.get("name") if isinstance(value, dict) else value)])
    return string_list(values)
