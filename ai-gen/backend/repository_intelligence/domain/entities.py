"""Core Repository Intelligence entities for the Phase 2 foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.platform.shared import clean, generated_id, now_iso


class RepositoryLanguage(str, Enum):
    UNKNOWN = "Unknown"
    PYTHON = "Python"
    TYPESCRIPT = "TypeScript"
    JAVASCRIPT = "JavaScript"
    CSHARP = "C#"
    JAVA = "Java"
    KOTLIN = "Kotlin"
    DART = "Dart"
    SWIFT = "Swift"
    GO = "Go"
    RUST = "Rust"
    SQL = "SQL"
    XML = "XML"
    XAML = "XAML"
    YAML = "YAML"
    JSON = "JSON"
    MARKDOWN = "Markdown"


class RepositoryType(str, Enum):
    AZURE_DEVOPS = "AzureDevOps"
    GITHUB = "GitHub"


class RepositoryAuthenticationType(str, Enum):
    PAT = "PAT"
    OAUTH = "OAuth"
    SSH = "SSH"
    APP = "App"
    NONE = "None"


class RepositoryStatus(str, Enum):
    PENDING_SCAN = "PendingScan"
    ACTIVE = "Active"
    DISABLED = "Disabled"
    ERROR = "Error"


class RepositorySymbolKind(str, Enum):
    NAMESPACE = "Namespace"
    CLASS = "Class"
    INTERFACE = "Interface"
    ENUM = "Enum"
    METHOD = "Method"
    ATTRIBUTE = "Attribute"
    IMPORT = "Import"
    ROUTE = "Route"
    CONTROLLER = "Controller"
    REPOSITORY = "Repository"
    SERVICE = "Service"
    TEST = "Test"


@dataclass
class Repository:
    repository_id: str
    name: str
    url: str = ""
    default_branch: str = "main"
    repository_type: RepositoryType = RepositoryType.GITHUB
    authentication_type: RepositoryAuthenticationType = RepositoryAuthenticationType.NONE
    status: RepositoryStatus = RepositoryStatus.PENDING_SCAN
    project_id: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repositoryId": self.repository_id,
            "name": self.name,
            "url": self.url,
            "defaultBranch": self.default_branch,
            "repositoryType": self.repository_type.value,
            "authenticationType": self.authentication_type.value,
            "status": self.status.value,
            "projectId": self.project_id,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Repository":
        return cls(
            repository_id=clean(payload.get("repositoryId") or payload.get("repository_id")) or generated_id("repository"),
            name=clean(payload.get("name")) or "Repository",
            url=clean(payload.get("url") or payload.get("remoteUrl") or payload.get("remote_url")),
            default_branch=clean(payload.get("defaultBranch") or payload.get("default_branch")) or "main",
            repository_type=_repository_type(
                payload.get("repositoryType") or payload.get("repository_type") or payload.get("provider")
            ),
            authentication_type=_authentication_type(
                payload.get("authenticationType") or payload.get("authentication_type")
            ),
            status=_repository_status(payload.get("status")),
            project_id=clean(payload.get("projectId") or payload.get("project_id")),
            created_at=clean(payload.get("createdAt") or payload.get("created_at")) or now_iso(),
            updated_at=clean(payload.get("updatedAt") or payload.get("updated_at")) or now_iso(),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass
class RepositorySnapshot:
    snapshot_id: str
    repository_id: str
    version: int = 1
    created_at: str = field(default_factory=now_iso)
    branch: str = "main"
    commit_id: str = ""
    total_files: int = 0
    languages: dict[str, int] = field(default_factory=dict)
    modules: list[str] = field(default_factory=list)
    status: str = "Completed"
    summary: str = ""
    scan_mode: str = "Full"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshotId": self.snapshot_id,
            "repositoryId": self.repository_id,
            "version": self.version,
            "createdAt": self.created_at,
            "branch": self.branch,
            "commitId": self.commit_id,
            "totalFiles": self.total_files,
            "languages": dict(self.languages),
            "modules": list(self.modules),
            "status": self.status,
            "summary": self.summary,
            "scanMode": self.scan_mode,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RepositorySnapshot":
        return cls(
            snapshot_id=clean(payload.get("snapshotId") or payload.get("snapshot_id")) or generated_id("snapshot"),
            repository_id=clean(payload.get("repositoryId") or payload.get("repository_id")) or "",
            version=max(1, int(payload.get("version") or 1)),
            created_at=clean(payload.get("createdAt") or payload.get("created_at")) or now_iso(),
            branch=clean(payload.get("branch")) or "main",
            commit_id=clean(payload.get("commitId") or payload.get("commit_id")),
            total_files=max(0, int(payload.get("totalFiles") or payload.get("total_files") or 0)),
            languages=dict(payload.get("languages") or {}),
            modules=[clean(item) for item in list(payload.get("modules") or []) if clean(item)],
            status=clean(payload.get("status")) or "Completed",
            summary=clean(payload.get("summary")),
            scan_mode=clean(payload.get("scanMode") or payload.get("scan_mode")) or "Full",
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass
class RepositoryFile:
    file_id: str
    repository_id: str
    snapshot_id: str = ""
    path: str = ""
    language: RepositoryLanguage = RepositoryLanguage.UNKNOWN
    extension: str = ""
    size: int = 0
    content_hash: str = ""
    last_modified: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fileId": self.file_id,
            "repositoryId": self.repository_id,
            "snapshotId": self.snapshot_id,
            "path": self.path,
            "language": self.language.value,
            "extension": self.extension,
            "size": self.size,
            "contentHash": self.content_hash,
            "lastModified": self.last_modified,
            "metadata": dict(self.metadata),
        }


@dataclass
class RepositoryModule:
    module_id: str
    repository_id: str
    snapshot_id: str = ""
    name: str = ""
    path_prefix: str = ""
    language: RepositoryLanguage = RepositoryLanguage.UNKNOWN
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "moduleId": self.module_id,
            "repositoryId": self.repository_id,
            "snapshotId": self.snapshot_id,
            "name": self.name,
            "pathPrefix": self.path_prefix,
            "language": self.language.value,
            "metadata": dict(self.metadata),
        }


@dataclass
class RepositoryParsedSymbol:
    symbol_id: str
    repository_id: str
    snapshot_id: str = ""
    path: str = ""
    language: RepositoryLanguage = RepositoryLanguage.UNKNOWN
    kind: RepositorySymbolKind = RepositorySymbolKind.CLASS
    name: str = ""
    namespace: str = ""
    container: str = ""
    signature: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbolId": self.symbol_id,
            "repositoryId": self.repository_id,
            "snapshotId": self.snapshot_id,
            "path": self.path,
            "language": self.language.value,
            "kind": self.kind.value,
            "name": self.name,
            "namespace": self.namespace,
            "container": self.container,
            "signature": self.signature,
            "metadata": dict(self.metadata),
            "createdAt": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RepositoryParsedSymbol":
        return cls(
            symbol_id=clean(payload.get("symbolId") or payload.get("symbol_id")) or generated_id("parsed_symbol"),
            repository_id=clean(payload.get("repositoryId") or payload.get("repository_id")) or "",
            snapshot_id=clean(payload.get("snapshotId") or payload.get("snapshot_id")),
            path=clean(payload.get("path")),
            language=_repository_language(payload.get("language")),
            kind=_symbol_kind(payload.get("kind")),
            name=clean(payload.get("name")) or "Symbol",
            namespace=clean(payload.get("namespace")),
            container=clean(payload.get("container")),
            signature=clean(payload.get("signature")),
            metadata=dict(payload.get("metadata") or {}),
            created_at=clean(payload.get("createdAt") or payload.get("created_at")) or now_iso(),
        )


@dataclass
class RepositoryFileRanking:
    path: str
    confidence: float = 0.0
    reason: str = ""
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.path,
            "confidence": round(float(self.confidence or 0.0), 4),
            "reason": self.reason,
            "dependencies": list(self.dependencies),
            "metadata": dict(self.metadata),
        }


@dataclass
class RepositoryContextCapsule:
    story_title: str
    relevant_files: list[dict[str, Any]] = field(default_factory=list)
    relevant_apis: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    architecture_rules: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    suggested_tests: list[dict[str, Any]] = field(default_factory=list)
    module_context: list[dict[str, Any]] = field(default_factory=list)
    graph_references: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "storyTitle": self.story_title,
            "relevantFiles": list(self.relevant_files),
            "relevantAPIs": list(self.relevant_apis),
            "dependencies": list(self.dependencies),
            "architectureRules": list(self.architecture_rules),
            "risks": list(self.risks),
            "suggestedTests": list(self.suggested_tests),
            "moduleContext": list(self.module_context),
            "graphReferences": list(self.graph_references),
            "diagnostics": dict(self.diagnostics),
        }


@dataclass
class RepositoryScan:
    scan_id: str
    repository_id: str
    snapshot_id: str = ""
    status: str = RepositoryStatus.PENDING_SCAN.value
    requested_at: str = field(default_factory=now_iso)
    started_at: str = ""
    completed_at: str = ""
    requested_by: str = ""
    mode: str = "Full"
    root_path: str = ""
    progress: dict[str, Any] = field(default_factory=dict)
    message: str = "Repository Intelligence foundation is registered. Scanning is not implemented yet."
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanId": self.scan_id,
            "repositoryId": self.repository_id,
            "snapshotId": self.snapshot_id,
            "status": self.status,
            "requestedAt": self.requested_at,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "requestedBy": self.requested_by,
            "mode": self.mode,
            "rootPath": self.root_path,
            "progress": dict(self.progress),
            "message": self.message,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RepositoryScan":
        return cls(
            scan_id=clean(payload.get("scanId") or payload.get("scan_id")) or generated_id("repository_scan"),
            repository_id=clean(payload.get("repositoryId") or payload.get("repository_id")) or "",
            snapshot_id=clean(payload.get("snapshotId") or payload.get("snapshot_id")),
            status=clean(payload.get("status")) or RepositoryStatus.PENDING_SCAN.value,
            requested_at=clean(payload.get("requestedAt") or payload.get("requested_at")) or now_iso(),
            started_at=clean(payload.get("startedAt") or payload.get("started_at")),
            completed_at=clean(payload.get("completedAt") or payload.get("completed_at")),
            requested_by=clean(payload.get("requestedBy") or payload.get("requested_by")),
            mode=clean(payload.get("mode")) or "Full",
            root_path=clean(payload.get("rootPath") or payload.get("root_path")),
            progress=dict(payload.get("progress") or {}),
            message=clean(payload.get("message"))
            or "Repository Intelligence foundation is registered. Scanning is not implemented yet.",
            metadata=dict(payload.get("metadata") or {}),
        )


def _repository_type(value: Any) -> RepositoryType:
    normalized = clean(value).lower()
    if normalized in {"azuredevops", "azure_devops", "ado", "azure"}:
        return RepositoryType.AZURE_DEVOPS
    return RepositoryType.GITHUB


def _authentication_type(value: Any) -> RepositoryAuthenticationType:
    normalized = clean(value).lower()
    if normalized == "pat":
        return RepositoryAuthenticationType.PAT
    if normalized == "oauth":
        return RepositoryAuthenticationType.OAUTH
    if normalized == "ssh":
        return RepositoryAuthenticationType.SSH
    if normalized == "app":
        return RepositoryAuthenticationType.APP
    return RepositoryAuthenticationType.NONE


def _repository_status(value: Any) -> RepositoryStatus:
    normalized = clean(value).lower()
    if normalized == "active":
        return RepositoryStatus.ACTIVE
    if normalized == "disabled":
        return RepositoryStatus.DISABLED
    if normalized == "error":
        return RepositoryStatus.ERROR
    return RepositoryStatus.PENDING_SCAN


def _repository_language(value: Any) -> RepositoryLanguage:
    normalized = clean(value).lower()
    for language in RepositoryLanguage:
        if language.value.lower() == normalized:
            return language
    return RepositoryLanguage.UNKNOWN


def _symbol_kind(value: Any) -> RepositorySymbolKind:
    normalized = clean(value).lower()
    for kind in RepositorySymbolKind:
        if kind.value.lower() == normalized:
            return kind
    return RepositorySymbolKind.CLASS
