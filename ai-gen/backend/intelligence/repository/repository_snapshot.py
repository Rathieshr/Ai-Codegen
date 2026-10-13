from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


REPOSITORY_SNAPSHOT_SCHEMA_VERSION = "repository-snapshot-v1"


@dataclass(frozen=True)
class RepositoryFile:
    path: str
    content: str = ""
    language: str = "Unknown"
    size: int = 0
    hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", str(self.path).strip())
        object.__setattr__(self, "content", str(self.content or ""))
        if not self.path:
            raise ValueError("RepositoryFile.path is required")
        if not self.size:
            object.__setattr__(self, "size", len(self.content.encode("utf-8")))
        if not self.hash:
            object.__setattr__(self, "hash", _short_hash(self.content))
        if self.language == "Unknown":
            object.__setattr__(self, "language", detect_language_from_path(self.path))

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "language": self.language,
            "size": self.size,
            "hash": self.hash,
        }


@dataclass(frozen=True)
class DiscoveredItem:
    name: str
    type: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    source: str = "repository"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "type": self.type,
            "confidence": round(float(self.confidence), 3),
            "evidence": list(self.evidence),
            "source": self.source,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass
class RepositorySnapshot:
    repository_id: str
    scan_version: int
    scanned_at: str
    applications: list[DiscoveredItem] = field(default_factory=list)
    modules: list[DiscoveredItem] = field(default_factory=list)
    flows: list[DiscoveredItem] = field(default_factory=list)
    technologies: list[DiscoveredItem] = field(default_factory=list)
    architecture: list[DiscoveredItem] = field(default_factory=list)
    dependencies: list[DiscoveredItem] = field(default_factory=list)
    patterns: list[DiscoveredItem] = field(default_factory=list)
    standards: list[DiscoveredItem] = field(default_factory=list)
    services: list[DiscoveredItem] = field(default_factory=list)
    apis: list[DiscoveredItem] = field(default_factory=list)
    database_models: list[DiscoveredItem] = field(default_factory=list)
    files: list[RepositoryFile] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    graph_statistics: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    diagnostics: dict[str, Any] = field(default_factory=dict)
    schema_version: str = REPOSITORY_SNAPSHOT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "repositoryId": self.repository_id,
            "scanVersion": self.scan_version,
            "scannedAt": self.scanned_at,
            "applications": [item.to_dict() for item in self.applications],
            "modules": [item.to_dict() for item in self.modules],
            "flows": [item.to_dict() for item in self.flows],
            "technologies": [item.to_dict() for item in self.technologies],
            "architecture": [item.to_dict() for item in self.architecture],
            "dependencies": [item.to_dict() for item in self.dependencies],
            "patterns": [item.to_dict() for item in self.patterns],
            "standards": [item.to_dict() for item in self.standards],
            "services": [item.to_dict() for item in self.services],
            "apis": [item.to_dict() for item in self.apis],
            "databaseModels": [item.to_dict() for item in self.database_models],
            "files": [item.to_dict() for item in self.files],
            "sourceFiles": list(self.source_files),
            "graphStatistics": dict(self.graph_statistics),
            "confidence": round(float(self.confidence), 3),
            "diagnostics": dict(self.diagnostics),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RepositorySnapshot":
        return cls(
            repository_id=str(payload.get("repositoryId") or payload.get("repository_id") or ""),
            scan_version=int(payload.get("scanVersion") or payload.get("scan_version") or 1),
            scanned_at=str(payload.get("scannedAt") or payload.get("scanned_at") or datetime.now(timezone.utc).isoformat()),
            applications=_items(payload.get("applications")),
            modules=_items(payload.get("modules")),
            flows=_items(payload.get("flows")),
            technologies=_items(payload.get("technologies")),
            architecture=_items(payload.get("architecture")),
            dependencies=_items(payload.get("dependencies")),
            patterns=_items(payload.get("patterns")),
            standards=_items(payload.get("standards")),
            services=_items(payload.get("services")),
            apis=_items(payload.get("apis")),
            database_models=_items(payload.get("databaseModels") or payload.get("database_models")),
            files=[RepositoryFile(path=str(item.get("path")), language=str(item.get("language") or "Unknown"), size=int(item.get("size") or 0), hash=str(item.get("hash") or "")) for item in payload.get("files", []) if isinstance(item, dict)],
            source_files=list(payload.get("sourceFiles") or payload.get("source_files") or []),
            graph_statistics=dict(payload.get("graphStatistics") or payload.get("graph_statistics") or {}),
            confidence=float(payload.get("confidence") or 0.0),
            diagnostics=dict(payload.get("diagnostics") or {}),
            schema_version=str(payload.get("schema_version") or payload.get("schemaVersion") or REPOSITORY_SNAPSHOT_SCHEMA_VERSION),
        )


def detect_language_from_path(path: str) -> str:
    suffix = path.lower().rsplit(".", 1)[-1] if "." in path else ""
    return {
        "ts": "TypeScript",
        "tsx": "TypeScript",
        "js": "JavaScript",
        "jsx": "JavaScript",
        "cs": "C#",
        "java": "Java",
        "kt": "Kotlin",
        "swift": "Swift",
        "py": "Python",
        "xaml": "XAML",
        "sql": "SQL",
    }.get(suffix, "Unknown")


def _short_hash(value: str) -> str:
    return hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()[:16]


def _items(value: Any) -> list[DiscoveredItem]:
    result: list[DiscoveredItem] = []
    for item in value or []:
        if isinstance(item, DiscoveredItem):
            result.append(item)
        elif isinstance(item, dict):
            result.append(
                DiscoveredItem(
                    name=str(item.get("name") or item.get("title") or ""),
                    type=str(item.get("type") or "unknown"),
                    confidence=float(item.get("confidence") or 0.0),
                    evidence=list(item.get("evidence") or []),
                    source=str(item.get("source") or "repository"),
                    metadata=dict(item.get("metadata") or {}),
                )
            )
    return result
