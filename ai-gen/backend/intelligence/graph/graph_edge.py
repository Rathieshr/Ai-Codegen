from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


EDGE_TYPES = {
    "contains",
    "derives_from",
    "implements",
    "uses",
    "depends_on",
    "related_to",
    "generated_from",
    "validated_by",
    "rejected",
    "references",
    "implemented_by",
    "tested_by",
    "belongs_to",
}


@dataclass
class GraphEdge:
    id: str
    from_node: str
    to_node: str
    type: str
    confidence: float | None = None
    reason: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        self.from_node = str(self.from_node).strip()
        self.to_node = str(self.to_node).strip()
        self.type = str(self.type or "").strip().lower()
        if not self.from_node:
            raise ValueError("GraphEdge.from_node is required")
        if not self.to_node:
            raise ValueError("GraphEdge.to_node is required")
        if not self.type:
            raise ValueError("GraphEdge.type is required")
        if not self.id:
            self.id = edge_id(self.from_node, self.type, self.to_node)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "from": self.from_node,
            "to": self.to_node,
            "type": self.type,
        }
        if self.confidence is not None:
            payload["confidence"] = round(float(self.confidence), 3)
        if self.reason:
            payload["reason"] = self.reason
        if self.source:
            payload["source"] = self.source
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GraphEdge":
        from_node = payload.get("from") or payload.get("from_node") or payload.get("fromNode")
        to_node = payload.get("to") or payload.get("to_node") or payload.get("toNode")
        edge_type = payload.get("type", "")
        return cls(
            id=str(payload.get("id") or edge_id(str(from_node), str(edge_type), str(to_node))),
            from_node=str(from_node or ""),
            to_node=str(to_node or ""),
            type=str(edge_type),
            confidence=payload.get("confidence"),
            reason=payload.get("reason"),
            source=payload.get("source"),
        )


def edge_id(from_node: str, edge_type: str, to_node: str) -> str:
    raw = f"{from_node}|{edge_type.lower()}|{to_node}"
    return f"edge_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"
