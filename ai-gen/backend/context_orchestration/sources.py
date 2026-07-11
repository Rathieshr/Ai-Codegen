"""Adapters over existing HEI context services."""

from __future__ import annotations

import json
from typing import Any, Protocol

from .models import ContextRequest, ContextSourceResult, ContextSourceType, RepositoryMode


class IContextSource(Protocol):
    source_type: ContextSourceType
    def retrieve(self, request: ContextRequest) -> ContextSourceResult: ...


class PlanningContextSource:
    source_type = ContextSourceType.PLANNING
    def retrieve(self, request: ContextRequest) -> ContextSourceResult:
        items = [request.artifact] if request.artifact else []
        return ContextSourceResult(self.source_type, bool(items), "Fresh" if items else "Unavailable", items=items)


class LocalWorkspaceContextSource:
    source_type = ContextSourceType.LOCAL_WORKSPACE
    def retrieve(self, request: ContextRequest) -> ContextSourceResult:
        items = [{"title": key, "content": value, "category": "File" if "File" in key else "Knowledge", "directEvidence": True} for key, value in request.local_context.items() if value]
        return ContextSourceResult(self.source_type, bool(items), "Fresh" if items else "Unavailable", items=items)


class EngineeringMemoryContextSource:
    source_type = ContextSourceType.ENGINEERING_MEMORY
    def __init__(self, engine: Any) -> None: self.engine = engine
    def retrieve(self, request: ContextRequest) -> ContextSourceResult:
        if not request.options.get("includeMemory", True):
            return ContextSourceResult(self.source_type, False, "Unavailable", diagnostics={"disabled": True})
        artifact = request.artifact
        response = self.engine.search({"projectId": request.project_id, "query": f"{artifact.get('title', '')} {artifact.get('description', '')}", "limit": int(request.options.get("maxMemories", 5))})
        return ContextSourceResult(self.source_type, True, "Unknown", items=list(response.get("results", [])), diagnostics={"existingService": "EngineeringMemoryEngine"})


class RepositoryContextSource:
    source_type = ContextSourceType.REPOSITORY
    def __init__(self, application: Any) -> None: self.application = application
    def retrieve(self, request: ContextRequest) -> ContextSourceResult:
        if not request.repository_id or not request.options.get("includeRepository", True):
            return ContextSourceResult(self.source_type, False, "Unavailable", warnings=["Repository context unavailable."] if request.repository_id else [])
        status = self.application.get_repository_status(request.repository_id)
        if not status:
            return ContextSourceResult(self.source_type, False, "Unavailable", warnings=["Repository is not registered."], diagnostics={"repositoryMode": RepositoryMode.UNAVAILABLE.value})
        snapshot = self.application.get_current_snapshot(request.repository_id) or {}
        mode = RepositoryMode.CODE_INDEXED if snapshot and status.get("graphStatus") not in {"NotConnected", "Unavailable"} else RepositoryMode.KNOWLEDGE_SNAPSHOT if snapshot else RepositoryMode.UNAVAILABLE
        if mode == RepositoryMode.UNAVAILABLE:
            return ContextSourceResult(self.source_type, False, "Unavailable", warnings=["Repository intelligence is unavailable; non-repository sources were used."], diagnostics={"repositoryMode": mode.value})
        artifact = request.artifact
        if mode == RepositoryMode.CODE_INDEXED:
            ranked = self.application.rank_repository_files(request.repository_id, artifact_type=str(artifact.get("artifactType") or "Story"), title=str(artifact.get("title") or ""), description=str(artifact.get("description") or ""), limit=int(request.options.get("maxFiles", 10))) or {}
            items = [{**item, "category": "File", "directEvidence": True} for item in ranked.get("files", [])]
        else:
            items = [{"title": module, "content": module, "category": "Module", "broadContext": True} for module in snapshot.get("modules", [])]
        return ContextSourceResult(self.source_type, True, "Fresh", version=str(snapshot.get("snapshotId") or ""), items=items, diagnostics={"repositoryMode": mode.value, "existingService": "RepositoryIntelligenceApplicationService"})


class StaticServiceContextSource:
    """Safe adapter for existing knowledge, standards, or validation providers."""
    def __init__(self, source_type: ContextSourceType, retriever: Any) -> None:
        self.source_type, self.retriever = source_type, retriever
    def retrieve(self, request: ContextRequest) -> ContextSourceResult:
        items = self.retriever(request) or []
        return ContextSourceResult(self.source_type, True, "Unknown", items=list(items))


def item_content(item: Any) -> str:
    if isinstance(item, str): return item
    if not isinstance(item, dict): return str(item)
    for key in ("content", "summary", "description", "contentPreview", "path", "title", "name"):
        if item.get(key): return str(item[key])
    return json.dumps(item, sort_keys=True, default=str)
