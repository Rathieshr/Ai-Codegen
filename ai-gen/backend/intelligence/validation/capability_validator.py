from __future__ import annotations

from typing import Any

from backend.intelligence.capability.capability_rules import canonical_capability, is_system_flow_name

from .validation_report import ValidationIssue
from .validation_utils import artifact_text, names


def validate_capability_alignment(planning_context: dict[str, Any], artifact: dict[str, Any]) -> tuple[int, list[ValidationIssue]]:
    selected = names(planning_context.get("selectedCapabilities"))
    generated = names((artifact.get("generatedUsing") or {}).get("capabilities") if isinstance(artifact.get("generatedUsing"), dict) else [])
    generated_flows = names((artifact.get("generatedUsing") or {}).get("flows") if isinstance(artifact.get("generatedUsing"), dict) else [])
    text = artifact_text(artifact).lower()
    issues: list[ValidationIssue] = []
    if not selected:
        return 55, [
            ValidationIssue(
                "Warning",
                "Capability Alignment",
                "PlanningContext does not contain selected capabilities.",
                "Rebuild PlanningContext through Capability Intelligence before validation.",
            )
        ]
    selected_canonical = [canonical_capability(capability) for capability in selected]
    generated_canonical = [canonical_capability(capability) for capability in generated]
    supported = [
        capability
        for capability in selected
        if capability.lower() in text or canonical_capability(capability) in generated_canonical
    ]
    unsupported_generated = [capability for capability in generated if canonical_capability(capability) not in selected_canonical]
    score = 62 + min(len(supported), 3) * 10 - len(unsupported_generated) * 18
    invalid_flows = [flow for flow in generated_flows if is_system_flow_name(flow)]
    if invalid_flows:
        score -= 32
        issues.append(
            ValidationIssue(
                "Error",
                "Flow Alignment",
                f"System/application names cannot be selected as flows: {', '.join(invalid_flows)}.",
                "Move system names to applications or remove them from generatedUsing.flows.",
            )
        )
    if unsupported_generated:
        issues.append(
            ValidationIssue(
                "Error",
                "Capability Alignment",
                f"Artifact references unsupported capabilities: {', '.join(unsupported_generated)}.",
                "Remove unsupported capabilities or update the parent artifact and PlanningContext.",
            )
        )
    if not supported:
        issues.append(
            ValidationIssue(
                "Warning",
                "Capability Alignment",
                "Artifact does not clearly map to selected capabilities.",
                "Tie the artifact title, description, or business value to a selected capability.",
            )
        )
    return max(0, min(score, 100)), issues
