"""Normalized HEI models for Azure DevOps read-only integration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from .errors import AzureDevOpsValidationError


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AzureDevOpsAuthenticationMode(str, Enum):
    PAT = "PAT"
    OAUTH = "OAuth"
    MANAGED_IDENTITY = "ManagedIdentity"


class AzureDevOpsConnectionStatus(str, Enum):
    PENDING_VALIDATION = "PendingValidation"
    CONNECTED = "Connected"
    DEGRADED = "Degraded"
    FAILED = "Failed"


@dataclass
class AzureDevOpsConnection:
    connection_id: str
    organization_url: str
    organization_name: str
    project_id: str = ""
    project_name: str = ""
    authentication_mode: str = AzureDevOpsAuthenticationMode.PAT.value
    secret_reference: str = ""
    status: str = AzureDevOpsConnectionStatus.PENDING_VALIDATION.value
    permissions: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    last_validated_at: str = ""
    validation_message: str = "Connection has not been validated."

    @classmethod
    def create(cls, value: dict[str, Any]) -> "AzureDevOpsConnection":
        organization_url = normalize_organization_url(str(value.get("organizationUrl") or value.get("organization_url") or ""))
        organization_name = str(value.get("organizationName") or value.get("organization_name") or organization_from_url(organization_url)).strip()
        authentication_mode = str(value.get("authenticationMode") or value.get("authentication_mode") or AzureDevOpsAuthenticationMode.PAT.value)
        if authentication_mode not in {item.value for item in AzureDevOpsAuthenticationMode}:
            raise AzureDevOpsValidationError(f"Unsupported Azure DevOps authentication mode: {authentication_mode}.")
        secret_reference = str(value.get("secretReference") or value.get("secret_reference") or "").strip()
        if authentication_mode == AzureDevOpsAuthenticationMode.PAT.value and not secret_reference:
            raise AzureDevOpsValidationError("secretReference is required for PAT authentication.")
        return cls(
            connection_id=str(value.get("connectionId") or value.get("connection_id") or f"ado-connection-{uuid4().hex[:12]}"),
            organization_url=organization_url,
            organization_name=organization_name,
            project_id=str(value.get("projectId") or value.get("project_id") or ""),
            project_name=str(value.get("projectName") or value.get("project_name") or ""),
            authentication_mode=authentication_mode,
            secret_reference=secret_reference,
            permissions=sorted({str(item) for item in value.get("permissions") or [] if str(item).strip()}),
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AzureDevOpsConnection":
        return cls(
            connection_id=str(value.get("connectionId") or ""),
            organization_url=str(value.get("organizationUrl") or ""),
            organization_name=str(value.get("organizationName") or ""),
            project_id=str(value.get("projectId") or ""),
            project_name=str(value.get("projectName") or ""),
            authentication_mode=str(value.get("authenticationMode") or "PAT"),
            secret_reference=str(value.get("secretReference") or ""),
            status=str(value.get("status") or AzureDevOpsConnectionStatus.PENDING_VALIDATION.value),
            permissions=list(value.get("permissions") or []),
            created_at=str(value.get("createdAt") or now_iso()),
            updated_at=str(value.get("updatedAt") or now_iso()),
            last_validated_at=str(value.get("lastValidatedAt") or ""),
            validation_message=str(value.get("validationMessage") or ""),
        )

    def to_storage_dict(self) -> dict[str, Any]:
        return self._to_dict(include_secret_reference=True)

    def to_public_dict(self) -> dict[str, Any]:
        value = self._to_dict(include_secret_reference=False)
        value["credentialConfigured"] = bool(self.secret_reference)
        return value

    def _to_dict(self, *, include_secret_reference: bool) -> dict[str, Any]:
        value = {
            "connectionId": self.connection_id, "organizationUrl": self.organization_url,
            "organizationName": self.organization_name, "projectId": self.project_id,
            "projectName": self.project_name, "authenticationMode": self.authentication_mode,
            "status": self.status, "permissions": list(self.permissions), "createdAt": self.created_at,
            "updatedAt": self.updated_at, "lastValidatedAt": self.last_validated_at,
            "validationMessage": self.validation_message,
        }
        if include_secret_reference:
            value["secretReference"] = self.secret_reference
        return value


def normalize_organization_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise AzureDevOpsValidationError("organizationUrl must be an absolute HTTP or HTTPS URL.")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise AzureDevOpsValidationError("Azure DevOps organizationUrl must use HTTPS outside local development.")
    return url


def organization_from_url(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    return parts[0] if parsed.netloc.lower() == "dev.azure.com" and parts else parsed.netloc


@dataclass
class ExternalProject:
    project_id: str
    name: str
    description: str = ""
    state: str = ""
    visibility: str = ""
    url: str = ""


@dataclass
class ExternalTeam:
    team_id: str
    name: str
    project_id: str = ""
    description: str = ""
    url: str = ""


@dataclass
class ExternalIteration:
    iteration_id: str
    name: str
    path: str = ""
    start_date: str = ""
    finish_date: str = ""
    time_frame: str = ""


@dataclass
class ExternalWorkItemLink:
    relation: str
    target_id: str = ""
    target_url: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExternalWorkItem:
    work_item_id: int
    work_item_type: str
    title: str
    state: str = ""
    description: str = ""
    acceptance_criteria: str = ""
    project_name: str = ""
    assigned_to: str = ""
    area_path: str = ""
    iteration_path: str = ""
    revision: int = 0
    links: list[ExternalWorkItemLink] = field(default_factory=list)
    changed_at: str = ""
    url: str = ""
    story_points: float | None = None
    effort: float | None = None
    original_estimate: float | None = None
    remaining_work: float | None = None
    completed_work: float | None = None
    created_at: str = ""
    activated_at: str = ""
    closed_at: str = ""
    state_change_date: str = ""
    tags: list[str] = field(default_factory=list)
    team_id: str = ""
    reopen_count: int = 0
    pr_iterations: int = 0
    escaped_defects: int = 0
    actual_cycle_time_days: float | None = None
    actual_active_time_days: float | None = None


@dataclass
class ExternalRepository:
    repository_id: str
    name: str
    project_id: str = ""
    project_name: str = ""
    default_branch: str = ""
    remote_url: str = ""
    web_url: str = ""
    size: int = 0


@dataclass
class ExternalPullRequest:
    pull_request_id: int
    title: str
    status: str
    repository_id: str = ""
    source_branch: str = ""
    target_branch: str = ""
    created_by: str = ""
    creation_date: str = ""
    is_draft: bool = False
    merge_status: str = ""
    url: str = ""
    linked_work_item_ids: list[str] = field(default_factory=list)
    commits: list[dict[str, Any]] = field(default_factory=list)
    changed_files: list[dict[str, Any]] = field(default_factory=list)
    source_commit_id: str = ""
    target_commit_id: str = ""
    repository_snapshot_before: str = ""
    repository_snapshot_after: str = ""


@dataclass
class ExternalBuild:
    build_id: int
    build_number: str
    status: str
    result: str = ""
    definition_name: str = ""
    source_branch: str = ""
    source_version: str = ""
    queue_time: str = ""
    start_time: str = ""
    finish_time: str = ""
    url: str = ""


def public_model(value: Any) -> dict[str, Any]:
    return _camelize(asdict(value))


def _camelize(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            parts = key.split("_")
            camel_key = "".join([parts[0], *[part.title() for part in parts[1:]]])
            output[camel_key] = _camelize(item)
        return output
    if isinstance(value, list):
        return [_camelize(item) for item in value]
    return value
