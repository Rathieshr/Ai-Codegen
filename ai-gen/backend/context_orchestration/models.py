"""Domain models for deterministic context orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ContextSourceType(str, Enum):
    PLANNING = "Planning"
    REPOSITORY = "Repository"
    KNOWLEDGE_REGISTRY = "KnowledgeRegistry"
    ENGINEERING_MEMORY = "EngineeringMemory"
    ENGINEERING_STANDARDS = "EngineeringStandards"
    VALIDATION_HISTORY = "ValidationHistory"
    LOCAL_WORKSPACE = "LocalWorkspace"


class RepositoryMode(str, Enum):
    CODE_INDEXED = "CodeIndexed"
    KNOWLEDGE_SNAPSHOT = "KnowledgeSnapshot"
    UNAVAILABLE = "Unavailable"


@dataclass
class ContextRequest:
    request_id: str
    correlation_id: str
    purpose: str
    project_id: str
    repository_id: str = ""
    repository_snapshot_version: str = ""
    artifact: dict[str, Any] = field(default_factory=dict)
    branch: str = ""
    commit_id: str = ""
    local_context: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ContextRequest":
        return cls(
            request_id=str(value.get("requestId") or value.get("request_id") or ""),
            correlation_id=str(value.get("correlationId") or value.get("correlation_id") or ""),
            purpose=str(value.get("purpose") or ""),
            project_id=str(value.get("projectId") or value.get("project_id") or ""),
            repository_id=str(value.get("repositoryId") or value.get("repository_id") or ""),
            repository_snapshot_version=str(value.get("repositorySnapshotVersion") or ""),
            artifact=dict(value.get("artifact") or {}),
            branch=str(value.get("branch") or ""),
            commit_id=str(value.get("commitId") or ""),
            local_context=dict(value.get("localContext") or {}),
            options=dict(value.get("options") or {}),
        )


@dataclass
class ContextSourceResult:
    source_type: ContextSourceType
    available: bool = True
    freshness: str = "Unknown"
    version: str = ""
    items: list[Any] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextCandidate:
    candidate_id: str
    source_type: ContextSourceType
    category: str
    title: str
    content: str
    relevance_score: float = 0.5
    confidence_score: float = 0.5
    freshness_score: float = 0.5
    evidence_score: float = 0.5
    final_score: float = 0.0
    token_estimate: int = 0
    provenance: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not self.token_estimate:
            self.token_estimate = max(1, (len(self.title) + len(self.content) + 3) // 4)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("metadata", None)
        value["sourceType"] = self.source_type.value
        mapping = {
            "candidate_id": "candidateId", "relevance_score": "relevanceScore",
            "confidence_score": "confidenceScore", "freshness_score": "freshnessScore",
            "evidence_score": "evidenceScore", "final_score": "finalScore",
            "token_estimate": "tokenEstimate",
        }
        for old, new in mapping.items():
            value[new] = value.pop(old)
        value.pop("source_type", None)
        return value


def source_result_dict(result: ContextSourceResult) -> dict[str, Any]:
    return {
        "sourceType": result.source_type.value,
        "available": result.available,
        "freshness": result.freshness,
        "version": result.version,
        "items": result.items,
        "warnings": result.warnings,
        "diagnostics": result.diagnostics,
    }
