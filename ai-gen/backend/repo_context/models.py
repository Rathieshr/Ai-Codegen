"""Dataclasses for repo-aware ai-gen context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    """Return an ISO timestamp for JSON records."""

    return datetime.now(timezone.utc).isoformat()


@dataclass
class ModuleInfo:
    name: str
    path: str = ""
    language: str = ""
    services: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class FileRecord:
    path: str
    language: str = ""
    module: str = ""
    summary_id: str | None = None
    last_indexed_at: str | None = None


@dataclass
class SummaryRecord:
    id: str
    path: str
    summary: str
    symbols: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class LogicUnit:
    id: str
    name: str
    summary: str = ""
    steps: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class GraphNode:
    id: str
    type: str
    label: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    from_id: str
    to_id: str
    type: str
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize with external from/to keys."""

        data: dict[str, Any] = {"from": self.from_id, "to": self.to_id, "type": self.type}
        if self.meta:
            data["meta"] = self.meta
        return data


@dataclass
class RepoMeta:
    repo_id: str
    repo_name: str
    git_remote: str | None = None
    repo_root: str = ""
    default_branch: str = "main"
    languages: list[str] = field(default_factory=list)
    modules: list[ModuleInfo] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    last_indexed_at: str | None = None
    index_version: str = "1"
    identity_mode: str = "path_fallback"
    canonical_remote: str | None = None
    aliases: list[str] = field(default_factory=list)


@dataclass
class BranchMeta:
    repo_id: str
    branch_name: str
    base_branch: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class ChangedFiles:
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)


@dataclass
class SessionContext:
    session_id: str
    repo_id: str
    branch_name: str
    ide: str = ""
    workspace_root: str = ""
    current_file: str = ""
    open_files: list[str] = field(default_factory=list)
    selected_text: str = ""
    current_task: str = ""
    last_query: str = ""
    last_execution_target: str = ""
    last_prompt_token_estimate: int | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class ContextRequest:
    repo_id: str | None = None
    branch_name: str | None = None
    session_id: str | None = None
    ide: str | None = None
    workspace_root: str | None = None
    open_files: list[str] = field(default_factory=list)
    current_file: str | None = None
