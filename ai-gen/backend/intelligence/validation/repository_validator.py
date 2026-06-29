from __future__ import annotations

from typing import Any

from .validation_report import ValidationIssue
from .validation_utils import artifact_text, names


def validate_repository_alignment(planning_context: dict[str, Any], artifact: dict[str, Any], options: dict[str, Any]) -> tuple[int, list[ValidationIssue]]:
    evidence = artifact.get("generatedUsing") if isinstance(artifact.get("generatedUsing"), dict) else {}
    selected_modules = names(planning_context.get("selectedModules"))
    selected_flows = names(planning_context.get("selectedFlows"))
    selected_apps = names(planning_context.get("selectedApplications"))
    modules = names(evidence.get("modules"))
    flows = names(evidence.get("flows"))
    apps = names(evidence.get("applications"))
    repository_files = _artifact_files(artifact)
    known_files = _known_files(options)
    issues: list[ValidationIssue] = []
    unsupported_modules = [item for item in modules if item not in selected_modules]
    unsupported_flows = [item for item in flows if item not in selected_flows]
    unsupported_apps = [item for item in apps if selected_apps and item not in selected_apps]
    hallucinated_files = [path for path in repository_files if known_files and path not in known_files]
    score = 88
    if unsupported_modules:
        score -= 25
        issues.append(ValidationIssue("Error", "Repository Alignment", f"Unsupported modules referenced: {', '.join(unsupported_modules)}.", "Use only modules selected in PlanningContext."))
    if unsupported_flows:
        score -= 22
        issues.append(ValidationIssue("Error", "Repository Alignment", f"Unsupported flows referenced: {', '.join(unsupported_flows)}.", "Use only flows selected in PlanningContext."))
    if unsupported_apps:
        score -= 12
        issues.append(ValidationIssue("Warning", "Repository Alignment", f"Unsupported applications referenced: {', '.join(unsupported_apps)}.", "Constrain application references to PlanningContext evidence."))
    if hallucinated_files:
        score -= 35
        issues.append(ValidationIssue("Error", "Repository Alignment", f"Repository files are not known: {', '.join(hallucinated_files)}.", "Remove invented file paths or provide repository-ranked files in PlanningContext."))
    for rejected in planning_context.get("rejectedContext", []) or []:
        if isinstance(rejected, dict) and str(rejected.get("name") or "").lower() in artifact_text(artifact).lower():
            score -= 25
            issues.append(ValidationIssue("Error", "Repository Alignment", f"Artifact includes rejected context: {rejected.get('name')}.", "Remove rejected context before presenting the artifact."))
    return max(0, min(score, 100)), issues


def _artifact_files(artifact: dict[str, Any]) -> list[str]:
    files = artifact.get("repositoryFiles") or artifact.get("repository_files") or artifact.get("recommendedFiles") or artifact.get("recommended_files") or []
    if not isinstance(files, list):
        return []
    return [str(item.get("path") if isinstance(item, dict) else item).strip() for item in files if str(item.get("path") if isinstance(item, dict) else item).strip()]


def _known_files(options: dict[str, Any]) -> list[str]:
    repository = options.get("repository_intelligence") or options.get("repositoryIntelligence") or options.get("repository_snapshot") or options.get("repositorySnapshot") or {}
    ranked = repository.get("rankedFiles") or repository.get("ranked_files") or repository.get("source_files") or repository.get("sourceFiles") or []
    output: list[str] = []
    if isinstance(ranked, list):
        for item in ranked:
            path = item.get("path") if isinstance(item, dict) else item
            if path:
                output.append(str(path))
    return output

