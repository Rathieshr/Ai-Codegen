"""Repository Intelligence foundation API router."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .contracts import (
    CompareSnapshotsRequest,
    CreateRepositoryRequest,
    FileRankingRequest,
    RepositoryContextCapsuleRequest,
    RepositoryScanRequest,
    RepositoryAgentTriggerRequest,
    UpdateRepositoryRequest,
)


def build_repository_router(module: object) -> APIRouter:
    router = APIRouter(prefix="/repositories", tags=["Repository Intelligence"])

    @router.get("/dashboard/monitoring")
    def get_repository_monitoring_dashboard() -> dict:
        return module.application.get_repository_monitoring_dashboard()

    @router.post("")
    def create_repository(request: CreateRepositoryRequest) -> dict:
        try:
            return module.application.create_repository(request.model_dump(by_alias=True))
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": str(error)})

    @router.get("")
    def list_repositories() -> dict:
        return module.application.list_repositories()

    @router.get("/{repository_id}")
    def get_repository(repository_id: str) -> dict:
        repository = module.application.get_repository(repository_id)
        if not repository:
            return JSONResponse(
                status_code=404,
                content={"error": f"Repository '{repository_id}' was not found."},
            )
        return repository

    @router.put("/{repository_id}")
    def update_repository(repository_id: str, request: UpdateRepositoryRequest) -> dict:
        try:
            repository = module.application.update_repository(repository_id, request.model_dump(by_alias=True))
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": str(error)})
        if not repository:
            return JSONResponse(
                status_code=404,
                content={"error": f"Repository '{repository_id}' was not found."},
            )
        return repository

    @router.delete("/{repository_id}")
    def delete_repository(repository_id: str) -> dict:
        deleted = module.application.delete_repository(repository_id)
        if not deleted:
            return JSONResponse(
                status_code=404,
                content={"error": f"Repository '{repository_id}' was not found."},
            )
        return {"repositoryId": repository_id, "deleted": True}

    @router.get("/{repository_id}/status")
    def get_repository_status(repository_id: str) -> dict:
        status = module.application.get_repository_status(repository_id)
        if not status:
            return JSONResponse(
                status_code=404,
                content={"error": f"Repository '{repository_id}' was not found."},
            )
        return status

    @router.get("/{repository_id}/snapshots/current")
    def get_current_snapshot(repository_id: str) -> dict:
        snapshot = module.application.get_current_snapshot(repository_id)
        if snapshot is None:
            repository = module.application.get_repository(repository_id)
            if not repository:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Repository '{repository_id}' was not found."},
                )
            return JSONResponse(
                status_code=404,
                content={"error": f"Repository '{repository_id}' does not have a completed snapshot yet."},
            )
        return snapshot

    @router.get("/{repository_id}/snapshots")
    def list_snapshot_history(repository_id: str) -> dict:
        snapshots = module.application.list_snapshot_history(repository_id)
        if not snapshots:
            return JSONResponse(
                status_code=404,
                content={"error": f"Repository '{repository_id}' was not found."},
            )
        return snapshots

    @router.get("/{repository_id}/snapshots/compare")
    def compare_snapshots(
        repository_id: str,
        leftSnapshotId: str,
        rightSnapshotId: str,
    ) -> dict:
        try:
            request = CompareSnapshotsRequest(leftSnapshotId=leftSnapshotId, rightSnapshotId=rightSnapshotId)
            comparison = module.application.compare_snapshots(
                repository_id,
                request.left_snapshot_id,
                request.right_snapshot_id,
            )
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": str(error)})
        if not comparison:
            return JSONResponse(
                status_code=404,
                content={"error": f"Repository '{repository_id}' was not found."},
            )
        return comparison

    @router.get("/{repository_id}/graph")
    def get_repository_graph(repository_id: str) -> dict:
        graph = module.application.get_graph(repository_id)
        if not graph:
            return JSONResponse(
                status_code=404,
                content={"error": f"Engineering graph for repository '{repository_id}' was not found."},
            )
        return graph

    @router.get("/{repository_id}/graph/nodes")
    def query_repository_graph_nodes(
        repository_id: str,
        nodeType: str = "",
        search: str = "",
    ) -> dict:
        result = module.application.query_graph_nodes(repository_id, node_type=nodeType, search=search)
        if not result:
            return JSONResponse(
                status_code=404,
                content={"error": f"Repository '{repository_id}' was not found."},
            )
        return result

    @router.get("/{repository_id}/graph/relationships")
    def query_repository_graph_relationships(
        repository_id: str,
        relationshipType: str = "",
        fromNodeId: str = "",
        toNodeId: str = "",
        search: str = "",
    ) -> dict:
        result = module.application.query_graph_relationships(
            repository_id,
            relationship_type=relationshipType,
            from_node_id=fromNodeId,
            to_node_id=toNodeId,
            search=search,
        )
        if not result:
            return JSONResponse(
                status_code=404,
                content={"error": f"Repository '{repository_id}' was not found."},
            )
        return result

    @router.get("/{repository_id}/symbols")
    def list_repository_symbols(
        repository_id: str,
        snapshotId: str = "",
        language: str = "",
        kind: str = "",
        path: str = "",
        search: str = "",
    ) -> dict:
        result = module.application.list_symbols(
            repository_id,
            snapshot_id=snapshotId,
            language=language,
            kind=kind,
            path=path,
            search=search,
        )
        if not result:
            return JSONResponse(
                status_code=404,
                content={"error": f"Repository '{repository_id}' was not found."},
            )
        return result

    @router.post("/{repository_id}/file-ranking")
    def rank_repository_files(repository_id: str, request: FileRankingRequest) -> dict:
        result = module.application.rank_repository_files(
            repository_id,
            artifact_type=request.artifact_type,
            title=request.title,
            description=request.description,
            acceptance_criteria=request.acceptance_criteria,
            tags=request.tags,
            selected_modules=request.selected_modules,
            selected_flows=request.selected_flows,
            limit=request.limit,
        )
        if not result:
            return JSONResponse(
                status_code=404,
                content={"error": f"Repository '{repository_id}' was not found."},
            )
        return result

    @router.post("/{repository_id}/context-capsule")
    def build_repository_context_capsule(repository_id: str, request: RepositoryContextCapsuleRequest) -> dict:
        result = module.application.build_repository_context_capsule(
            repository_id,
            story=request.story,
            selected_modules=request.selected_modules,
            selected_flows=request.selected_flows,
            limit=request.limit,
        )
        if not result:
            return JSONResponse(
                status_code=404,
                content={"error": f"Repository '{repository_id}' was not found."},
            )
        return result

    @router.post("/{repository_id}/scan")
    def scan_repository(repository_id: str, request: RepositoryScanRequest) -> dict:
        try:
            result = module.application.scan_repository(
                repository_id,
                mode=request.mode,
                requested_by=request.requested_by,
                root_path=request.root_path,
                manual_paths=request.manual_paths,
            )
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": str(error)})
        if not result:
            return JSONResponse(
                status_code=404,
                content={"error": f"Repository '{repository_id}' was not found."},
            )
        return result

    @router.post("/{repository_id}/incremental-scan")
    def incremental_scan_repository(repository_id: str) -> dict:
        try:
            result = module.application.scan_repository(repository_id, mode="Incremental")
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": str(error)})
        if not result:
            return JSONResponse(
                status_code=404,
                content={"error": f"Repository '{repository_id}' was not found."},
            )
        return result

    @router.post("/{repository_id}/scan/cancel")
    def cancel_repository_scan(repository_id: str) -> dict:
        scan = module.application.cancel_scan(repository_id)
        if not scan:
            return JSONResponse(
                status_code=404,
                content={"error": f"Repository '{repository_id}' was not found."},
            )
        return scan

    @router.post("/{repository_id}/agent/trigger")
    def trigger_repository_agent(repository_id: str, request: RepositoryAgentTriggerRequest) -> dict:
        try:
            result = module.application.trigger_repository_agent(
                repository_id,
                trigger=request.trigger,
                requested_by=request.requested_by,
                root_path=request.root_path,
                manual_paths=request.manual_paths,
                max_retries=request.max_retries,
                run_immediately=request.run_immediately,
            )
        except ValueError as error:
            return JSONResponse(status_code=400, content={"error": str(error)})
        if not result:
            return JSONResponse(status_code=404, content={"error": f"Repository '{repository_id}' was not found."})
        return result

    @router.post("/{repository_id}/agent/jobs/{job_id}/run")
    def run_repository_agent_job(repository_id: str, job_id: str) -> dict:
        result = module.application.run_repository_agent_job(repository_id, job_id)
        if not result:
            return JSONResponse(status_code=404, content={"error": f"Agent job '{job_id}' was not found."})
        return result

    @router.get("/{repository_id}/agent/status")
    def get_repository_agent_status(repository_id: str) -> dict:
        result = module.application.get_repository_agent_status(repository_id)
        if not result:
            return JSONResponse(status_code=404, content={"error": f"Repository '{repository_id}' was not found."})
        return result

    @router.get("/{repository_id}/agent/jobs")
    def list_repository_agent_jobs(repository_id: str, limit: int = 50) -> dict:
        result = module.application.list_repository_agent_jobs(repository_id, limit=limit)
        if not result:
            return JSONResponse(status_code=404, content={"error": f"Repository '{repository_id}' was not found."})
        return result

    @router.get("/{repository_id}/monitoring")
    def get_repository_monitoring(repository_id: str) -> dict:
        result = module.application.get_repository_monitoring(repository_id)
        if not result:
            return JSONResponse(status_code=404, content={"error": f"Repository '{repository_id}' was not found."})
        return result

    return router
