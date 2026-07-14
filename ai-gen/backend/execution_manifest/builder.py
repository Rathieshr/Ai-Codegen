"""Deterministic Execution Manifest builder.

The builder consumes one Execution Package. It performs no retrieval, prompt
formatting, provider selection, or LLM call.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from .models import ExecutionManifest, MANIFEST_VERSION, clean, items, mapping, now_iso, stable_hash, strings, unique


class IExecutionManifestBuilder(Protocol):
    def build(self, execution_package: dict[str, Any]) -> ExecutionManifest: ...


class ExecutionManifestBuilder:
    version = MANIFEST_VERSION

    def build(self, execution_package: dict[str, Any]) -> ExecutionManifest:
        package = mapping(execution_package)
        package_id = clean(package.get("packageId") or mapping(package.get("metadata")).get("packageId"))
        if not package_id:
            raise ValueError("A persisted Execution Package is required.")

        metadata = mapping(package.get("metadata"))
        planning = mapping(package.get("planningContext"))
        business = mapping(package.get("businessContext"))
        repository = mapping(package.get("repositoryContext"))
        implementation = mapping(package.get("implementationGuidance"))
        validation = mapping(package.get("validationGuidance"))
        qa = mapping(package.get("qaGuidance"))
        knowledge = mapping(package.get("knowledge"))
        diagnostics = mapping(package.get("diagnostics"))
        readiness = mapping(package.get("readiness"))

        acceptance = _acceptance(package, planning, validation)
        standards = _standards(package, knowledge, validation)
        risks = _risks(package, knowledge, validation)
        warnings = unique([
            *strings(diagnostics.get("warnings")),
            *strings(readiness.get("warnings")),
            *strings(mapping(diagnostics.get("executionReadiness")).get("warnings")),
        ])
        relevant_files = items(repository.get("relevantFiles")) or items(implementation.get("suggestedFiles"))
        dependencies = unique([
            *strings(repository.get("dependencies")),
            *strings(planning.get("dependencies")),
            *strings(mapping(package.get("implementationBoundary")).get("dependencies")),
        ])

        source_versions = {
            "executionPackageVersion": clean(diagnostics.get("builderVersion") or "2.0"),
            "contextCapsuleId": metadata.get("capsuleId") or diagnostics.get("capsuleId"),
            "contextCapsuleVersion": metadata.get("capsuleVersion"),
            "repositorySnapshotVersion": metadata.get("repositorySnapshotVersion") or package.get("repositorySnapshotVersion"),
            "knowledgeVersion": metadata.get("knowledgeVersion") or package.get("knowledgeVersion"),
            "planningVersion": metadata.get("planningVersion"),
            "engineeringMemoryVersion": metadata.get("engineeringMemoryVersion"),
        }
        token_estimates = _token_estimates(
            objective=clean(implementation.get("implementationObjective") or business.get("taskObjective") or _story_text(planning)),
            business_goal=clean(planning.get("businessGoal") or business.get("epicBusinessGoal") or business.get("businessGoal")),
            acceptance=acceptance,
            repository=repository,
            implementation=implementation,
            validation=validation,
            qa=qa,
            standards=standards,
            risks=risks,
        )
        core = {
            "manifestVersion": self.version,
            "sourcePackageId": package_id,
            "sourceVersions": source_versions,
            "objective": clean(implementation.get("implementationObjective") or business.get("taskObjective") or _story_text(planning)),
            "businessGoal": clean(planning.get("businessGoal") or business.get("epicBusinessGoal") or business.get("businessGoal")),
            "acceptanceCriteria": acceptance,
            "repositoryContext": repository,
            "relevantFiles": relevant_files,
            "dependencies": dependencies,
            "implementationGuidance": implementation,
            "validationGuidance": validation,
            "qaGuidance": qa,
            "engineeringStandards": standards,
            "risks": risks,
            "warnings": warnings,
            "confidence": float(metadata.get("confidence") if metadata.get("confidence") is not None else diagnostics.get("confidence") or 0),
            "tokenEstimates": token_estimates,
        }
        immutable_hash = stable_hash(core)
        manifest_id = f"execmanifest_{immutable_hash[:12]}"
        missing = [field for field in ("objective", "acceptanceCriteria", "implementationGuidance", "validationGuidance", "qaGuidance") if not core.get(field)]
        return {
            "manifestId": manifest_id,
            **core,
            "immutable": True,
            "immutableHash": immutable_hash,
            "generatedAt": now_iso(),
            "diagnostics": {
                "builderVersion": self.version,
                "sourcePackageId": package_id,
                "sourcePackageHash": stable_hash(package),
                "immutableHash": immutable_hash,
                "modelIndependent": True,
                "promptFormattingApplied": False,
                "providerSelected": False,
                "llmUsed": False,
                "retrievalPerformed": False,
                "missingFields": missing,
                "fieldCounts": {
                    "acceptanceCriteria": len(acceptance),
                    "relevantFiles": len(relevant_files),
                    "dependencies": len(dependencies),
                    "engineeringStandards": len(standards),
                    "risks": len(risks),
                    "warnings": len(warnings),
                },
            },
        }


def _acceptance(package: dict[str, Any], planning: dict[str, Any], validation: dict[str, Any]) -> list[dict[str, Any]]:
    mapped = items(package.get("acceptanceMapping")) or items(validation.get("acceptanceMapping"))
    if mapped:
        return [item for item in mapped if isinstance(item, dict)]
    raw = items(planning.get("acceptanceCriteria"))
    return [
        {"acceptanceCriteriaId": f"AC{index:03d}", "acceptanceText": clean(value), "implementationArea": "", "validationExpectation": ""}
        for index, value in enumerate(raw, start=1)
        if clean(value)
    ]


def _standards(package: dict[str, Any], knowledge: dict[str, Any], validation: dict[str, Any]) -> list[Any]:
    explicit = items(package.get("engineeringRules"))
    if explicit:
        return explicit
    return unique([
        *strings(knowledge.get("engineeringStandards")),
        *strings(knowledge.get("architectureRules")),
        *strings(knowledge.get("securityRules")),
        *strings(knowledge.get("validationRules")),
        *strings(validation.get("architectureConstraints")),
    ])


def _risks(package: dict[str, Any], knowledge: dict[str, Any], validation: dict[str, Any]) -> list[Any]:
    explicit = items(package.get("risks"))
    if explicit:
        return explicit
    return unique([*strings(knowledge.get("knownRisks")), *strings(validation.get("riskAreas"))])


def _story_text(planning: dict[str, Any]) -> str:
    story = mapping(planning.get("story"))
    return clean(story.get("description") or story.get("title"))


def _token_estimates(**sections: Any) -> dict[str, Any]:
    section_tokens = {
        name: max(1, len(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)) // 4)
        for name, value in sections.items()
    }
    return {
        "manifestTokens": sum(section_tokens.values()),
        "sectionTokens": section_tokens,
        "estimationMethod": "characters_divided_by_four",
    }
