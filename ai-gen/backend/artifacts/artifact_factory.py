"""Factory and default definitions for HEI artifact types."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .artifact_definition import ArtifactDefinition
from .artifact_lifecycle import ArtifactStatus


ARTIFACT_TYPES = [
    "Epic",
    "Capability",
    "Feature",
    "Story",
    "Task",
    "Execution Package",
    "Context Capsule",
    "Developer Prompt",
    "Validation Report",
]


class ArtifactFactory:
    def __init__(self, definitions: dict[str, ArtifactDefinition] | None = None) -> None:
        self.definitions = definitions or default_artifact_definitions()

    def definition_for(self, artifact_type: str) -> ArtifactDefinition:
        normalized = _normalize_artifact_type(artifact_type)
        if normalized not in self.definitions:
            self.definitions[normalized] = default_artifact_definition(normalized)
        return self.definitions[normalized]

    def create(self, artifact_type: str, source: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        normalized = _normalize_artifact_type(artifact_type)
        parent_id = _clean(source.get("parentId") or source.get("parent_id") or context.get("parentId") or context.get("parent_id"))
        title = _clean(source.get("title")) or normalized
        artifact_id = _clean(source.get("id")) or _artifact_id(normalized, parent_id, title)
        return {
            "id": artifact_id,
            "type": normalized,
            "parentId": parent_id,
            "title": title,
            "description": _clean(source.get("description")),
            "businessGoal": _clean(source.get("businessGoal") or source.get("business_goal")),
            "businessValue": _clean(source.get("businessValue") or source.get("business_value")),
            "repositoryEvidence": _list(source.get("repositoryEvidence") or source.get("repository_evidence")),
            "knowledgeReferences": _list(source.get("knowledgeReferences") or source.get("knowledge_references")),
            "dependencies": _list(source.get("dependencies")),
            "responsibilities": _list(source.get("responsibilities")),
            "acceptanceThemes": _list(source.get("acceptanceThemes") or source.get("acceptance_themes") or source.get("acceptanceCriteria") or source.get("acceptance_criteria")),
            "dna": source.get("dna") if isinstance(source.get("dna"), dict) else {},
            "validation": source.get("validation") if isinstance(source.get("validation"), dict) else {},
            "confidence": float(source.get("confidence") or 0.75),
            "version": int(source.get("version") or 0),
            "status": _clean(source.get("status")) or ArtifactStatus.DRAFT,
            "createdAt": _clean(source.get("createdAt")) or datetime.now(timezone.utc).isoformat(),
        }


def default_artifact_definitions() -> dict[str, ArtifactDefinition]:
    return {artifact_type: default_artifact_definition(artifact_type) for artifact_type in ARTIFACT_TYPES}


def default_artifact_definition(artifact_type: str) -> ArtifactDefinition:
    normalized = _normalize_artifact_type(artifact_type)
    return ArtifactDefinition(
        artifact_type=normalized,
        analysis_strategy=_default_analysis,
        generation_strategy=_default_generation,
        validation_strategy=_default_validation,
        dna_builder=_default_dna,
        prompt_builder=_default_prompt,
        metadata={"sharedLifecycle": True},
    )


def _default_analysis(source: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {
        "analysis": {
            "sourceTitle": _clean(source.get("title")),
            "parentId": _clean(source.get("parentId") or context.get("parentId")),
            "knowledgeReferences": _list(source.get("knowledgeReferences") or context.get("knowledgeReferences")),
            "repositoryEvidence": _list(source.get("repositoryEvidence") or context.get("repositoryEvidence")),
        }
    }


def _default_generation(source: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {
        "description": _clean(source.get("description")) or f"Plan and deliver {_clean(source.get('title')) or 'artifact'} within approved scope.",
        "businessValue": _clean(source.get("businessValue") or source.get("business_value") or context.get("businessValue")),
        "responsibilities": _list(source.get("responsibilities") or context.get("responsibilities")),
        "acceptanceThemes": _list(source.get("acceptanceThemes") or source.get("acceptance_criteria") or context.get("acceptanceThemes")),
    }


def _default_validation(artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    issues = []
    if not _clean(artifact.get("title")):
        issues.append({"severity": "critical", "message": "Title is required."})
    if not _clean(artifact.get("description")) and artifact.get("type") not in {"Context Capsule", "Validation Report"}:
        issues.append({"severity": "warning", "message": "Description should be completed before approval."})
    return {
        "validationStatus": "Approved" if not issues else "NeedsReview",
        "issues": issues,
        "score": 100 - (10 * len(issues)),
    }


def _default_dna(artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    parent_dna = context.get("parentDna") if isinstance(context.get("parentDna"), dict) else {}
    return {
        "dnaId": f"dna_{artifact.get('id')}",
        "artifactId": artifact.get("id"),
        "artifactType": artifact.get("type"),
        "parentDNA": parent_dna.get("dnaId"),
        "capability": artifact.get("businessGoal") or artifact.get("title"),
        "responsibilities": artifact.get("responsibilities") or [],
        "inScope": artifact.get("acceptanceThemes") or [],
        "repositoryEvidence": artifact.get("repositoryEvidence") or [],
        "confidence": artifact.get("confidence") or 0,
    }


def _default_prompt(artifact: dict[str, Any], context: dict[str, Any]) -> str:
    return (
        f"Create a {artifact.get('type')} artifact titled {artifact.get('title')}. "
        "Use only the artifact DNA, validation, repository evidence, and knowledge references supplied by the engine."
    )


def _artifact_id(artifact_type: str, parent_id: str, title: str) -> str:
    seed = f"{artifact_type}|{parent_id}|{title}"
    return f"artifact_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def _normalize_artifact_type(value: str) -> str:
    text = _clean(value)
    lookup = {item.lower(): item for item in ARTIFACT_TYPES}
    return lookup.get(text.lower(), text or "Artifact")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item.get("name") if isinstance(item, dict) else item) for item in value if _clean(item.get("name") if isinstance(item, dict) else item)]
    if isinstance(value, str):
        return [_clean(item) for item in value.splitlines() if _clean(item)]
    return []

