"""Engineering Graph foundation entities for Repository Intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.platform.shared import clean, generated_id, now_iso


class EngineeringNodeType(str, Enum):
    MODULE = "Module"
    FILE = "File"
    UI = "UI"
    SERVICE = "Service"
    CONTROLLER = "Controller"
    REPOSITORY = "Repository"
    API = "API"
    DTO = "DTO"
    TEST = "Test"


class RelationshipType(str, Enum):
    RELATED_TO = "related_to"
    REFERENCES = "references"
    DEPENDS_ON = "depends_on"
    CONTAINS = "contains"
    TESTS = "tests"


@dataclass
class EngineeringNode:
    node_id: str
    repository_id: str
    node_type: EngineeringNodeType
    name: str
    path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodeId": self.node_id,
            "repositoryId": self.repository_id,
            "nodeType": self.node_type.value,
            "name": self.name,
            "path": self.path,
            "metadata": dict(self.metadata),
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EngineeringNode":
        return cls(
            node_id=clean(payload.get("nodeId") or payload.get("node_id")) or generated_id("graph_node"),
            repository_id=clean(payload.get("repositoryId") or payload.get("repository_id")) or "",
            node_type=_node_type(payload.get("nodeType") or payload.get("node_type")),
            name=clean(payload.get("name")) or "Engineering Node",
            path=clean(payload.get("path")),
            metadata=dict(payload.get("metadata") or {}),
            created_at=clean(payload.get("createdAt") or payload.get("created_at")) or now_iso(),
            updated_at=clean(payload.get("updatedAt") or payload.get("updated_at")) or now_iso(),
        )


@dataclass
class EngineeringRelationship:
    relationship_id: str
    repository_id: str
    from_node_id: str
    to_node_id: str
    relationship_type: RelationshipType
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "relationshipId": self.relationship_id,
            "repositoryId": self.repository_id,
            "fromNodeId": self.from_node_id,
            "toNodeId": self.to_node_id,
            "relationshipType": self.relationship_type.value,
            "metadata": dict(self.metadata),
            "createdAt": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EngineeringRelationship":
        return cls(
            relationship_id=clean(payload.get("relationshipId") or payload.get("relationship_id"))
            or generated_id("graph_relationship"),
            repository_id=clean(payload.get("repositoryId") or payload.get("repository_id")) or "",
            from_node_id=clean(payload.get("fromNodeId") or payload.get("from_node_id")) or "",
            to_node_id=clean(payload.get("toNodeId") or payload.get("to_node_id")) or "",
            relationship_type=_relationship_type(
                payload.get("relationshipType") or payload.get("relationship_type")
            ),
            metadata=dict(payload.get("metadata") or {}),
            created_at=clean(payload.get("createdAt") or payload.get("created_at")) or now_iso(),
        )


@dataclass
class EngineeringGraph:
    graph_id: str
    repository_id: str
    nodes: list[EngineeringNode] = field(default_factory=list)
    relationships: list[EngineeringRelationship] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "graphId": self.graph_id,
            "repositoryId": self.repository_id,
            "nodes": [node.to_dict() for node in self.nodes],
            "relationships": [relationship.to_dict() for relationship in self.relationships],
            "metadata": dict(self.metadata),
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EngineeringGraph":
        return cls(
            graph_id=clean(payload.get("graphId") or payload.get("graph_id")) or generated_id("engineering_graph"),
            repository_id=clean(payload.get("repositoryId") or payload.get("repository_id")) or "",
            nodes=[EngineeringNode.from_dict(node) for node in list(payload.get("nodes") or [])],
            relationships=[
                EngineeringRelationship.from_dict(item)
                for item in list(payload.get("relationships") or [])
            ],
            metadata=dict(payload.get("metadata") or {}),
            created_at=clean(payload.get("createdAt") or payload.get("created_at")) or now_iso(),
            updated_at=clean(payload.get("updatedAt") or payload.get("updated_at")) or now_iso(),
        )


def _node_type(value: Any) -> EngineeringNodeType:
    normalized = clean(value).lower()
    for node_type in EngineeringNodeType:
        if node_type.value.lower() == normalized:
            return node_type
    return EngineeringNodeType.REPOSITORY


def _relationship_type(value: Any) -> RelationshipType:
    normalized = clean(value).lower()
    for relationship_type in RelationshipType:
        if relationship_type.value.lower() == normalized:
            return relationship_type
    return RelationshipType.RELATED_TO
