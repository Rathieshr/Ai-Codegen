from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


GraphNodeSource = Literal[
    "repository",
    "knowledge_registry",
    "planning",
    "execution",
    "validation",
    "manual",
]


NODE_TYPES = {
    "Project",
    "Epic",
    "Feature",
    "Story",
    "Task",
    "Capability",
    "Persona",
    "BusinessGoal",
    "Module",
    "Flow",
    "Application",
    "Dependency",
    "Standard",
    "Repository",
    "File",
    "Service",
    "Controller",
    "API",
    "ViewModel",
    "Screen",
    "DatabaseEntity",
    "ContextCapsule",
    "ExecutionPackage",
    "ValidationReport",
}


@dataclass
class GraphNode:
    id: str
    type: str
    name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    source: GraphNodeSource | str | None = None
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.id = str(self.id).strip()
        self.type = _clean_text(self.type)
        self.name = _clean_text(self.name)
        if not self.id:
            raise ValueError("GraphNode.id is required")
        if not self.type:
            raise ValueError("GraphNode.type is required")
        if not self.name:
            raise ValueError("GraphNode.name is required")

    def merge(self, other: "GraphNode") -> "GraphNode":
        if self.id != other.id:
            raise ValueError("Cannot merge graph nodes with different ids")
        metadata = {**self.metadata, **other.metadata}
        evidence = _dedupe([*self.evidence, *other.evidence])
        confidence = max(
            [value for value in [self.confidence, other.confidence] if value is not None],
            default=None,
        )
        return GraphNode(
            id=self.id,
            type=other.type or self.type,
            name=other.name or self.name,
            metadata=metadata,
            confidence=confidence,
            source=other.source or self.source,
            evidence=evidence,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "metadata": dict(self.metadata),
            "evidence": list(self.evidence),
        }
        if self.confidence is not None:
            payload["confidence"] = round(float(self.confidence), 3)
        if self.source:
            payload["source"] = self.source
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GraphNode":
        return cls(
            id=str(payload.get("id", "")),
            type=str(payload.get("type", "")),
            name=str(payload.get("name") or payload.get("title") or payload.get("id") or ""),
            metadata=dict(payload.get("metadata") or {}),
            confidence=payload.get("confidence"),
            source=payload.get("source"),
            evidence=list(payload.get("evidence") or []),
        )


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("_", " ").split())


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean_text(value)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result
