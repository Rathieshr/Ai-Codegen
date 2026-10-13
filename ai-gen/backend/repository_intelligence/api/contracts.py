"""REST contracts for Repository Intelligence foundation endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateRepositoryRequest(BaseModel):
    name: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    default_branch: str = Field(default="main", alias="defaultBranch")
    repository_type: str = Field(..., alias="repositoryType")
    authentication_type: str = Field(default="None", alias="authenticationType")
    project_id: str = Field(default="", alias="projectId")
    requested_by: str = Field(default="", alias="requestedBy")
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        populate_by_name = True


class UpdateRepositoryRequest(BaseModel):
    name: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    default_branch: str = Field(default="main", alias="defaultBranch")
    repository_type: str = Field(..., alias="repositoryType")
    authentication_type: str = Field(default="None", alias="authenticationType")
    project_id: str = Field(default="", alias="projectId")
    status: str = "PendingScan"
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        populate_by_name = True


class RepositoryStatusResponse(BaseModel):
    repository_id: str = Field(alias="repositoryId")
    repository_name: str = Field(alias="repositoryName")
    scan_status: str = Field(alias="scanStatus")
    snapshot_status: str = Field(alias="snapshotStatus")
    graph_status: str = Field(alias="graphStatus")
    message: str = ""
    latest_snapshot_id: str = Field(default="", alias="latestSnapshotId")
    latest_scan_id: str = Field(default="", alias="latestScanId")

    class Config:
        populate_by_name = True


class RepositoryScanRequest(BaseModel):
    mode: str = "Full"
    requested_by: str = Field(default="", alias="requestedBy")
    root_path: str = Field(default="", alias="rootPath")
    manual_paths: list[str] = Field(default_factory=list, alias="manualPaths")

    class Config:
        populate_by_name = True


class CompareSnapshotsRequest(BaseModel):
    left_snapshot_id: str = Field(..., alias="leftSnapshotId")
    right_snapshot_id: str = Field(..., alias="rightSnapshotId")

    class Config:
        populate_by_name = True


class FileRankingRequest(BaseModel):
    artifact_type: str = Field(..., alias="artifactType", min_length=1)
    title: str = Field(..., min_length=1)
    description: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list, alias="acceptanceCriteria")
    tags: list[str] = Field(default_factory=list)
    selected_modules: list[str] = Field(default_factory=list, alias="selectedModules")
    selected_flows: list[str] = Field(default_factory=list, alias="selectedFlows")
    limit: int = 10

    class Config:
        populate_by_name = True


class RepositoryContextCapsuleRequest(BaseModel):
    story: dict[str, Any] = Field(default_factory=dict)
    selected_modules: list[str] = Field(default_factory=list, alias="selectedModules")
    selected_flows: list[str] = Field(default_factory=list, alias="selectedFlows")
    limit: int = 8

    class Config:
        populate_by_name = True


class RepositoryAgentTriggerRequest(BaseModel):
    trigger: str
    requested_by: str = Field(default="", alias="requestedBy")
    root_path: str = Field(default="", alias="rootPath")
    manual_paths: list[str] = Field(default_factory=list, alias="manualPaths")
    max_retries: int = Field(default=2, alias="maxRetries", ge=0, le=10)
    run_immediately: bool = Field(default=False, alias="runImmediately")

    class Config:
        populate_by_name = True
