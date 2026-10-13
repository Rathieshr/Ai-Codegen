"""Read-only Azure DevOps integration application services."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from ..domain import (
    AzureDevOpsConnection, AzureDevOpsConnectionStatus, AzureDevOpsIntegrationError,
    AzureDevOpsNotFoundError, AzureDevOpsValidationError, public_model,
)
from ..mapping import map_build, map_iteration, map_project, map_pull_request, map_repository, map_team, map_work_item


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_pr_change(value: dict[str, Any]) -> dict[str, Any]:
    item = value.get("item") if isinstance(value.get("item"), dict) else {}
    return {
        "path": str(item.get("path") or value.get("path") or ""),
        "changeType": str(value.get("changeType") or value.get("changeTrackingId") or "Modified"),
        "objectId": str(item.get("objectId") or ""),
        "originalObjectId": str(item.get("originalObjectId") or ""),
    }


def _optional_pr_read(client: Any, method_name: str, *args, **kwargs) -> list[dict[str, Any]]:
    method = getattr(client, method_name, None)
    if not callable(method):
        return []
    value = method(*args, **kwargs)
    return value if isinstance(value, list) else []


class AzureDevOpsConnectionService:
    _PLAINTEXT_FIELDS = {"pat", "token", "password", "credential", "credentials", "secret", "secretvalue", "clientsecret"}

    def __init__(self, repository, client_factory, *, platform=None) -> None:
        self._repository = repository
        self._factory = client_factory
        self._platform = platform

    def register(self, value: dict[str, Any], *, correlation_id: str = "") -> dict[str, Any]:
        self._reject_plaintext(value)
        connection = AzureDevOpsConnection.create(value)
        if self._repository.find_duplicate(connection.organization_url, connection.project_id):
            raise AzureDevOpsValidationError("This Azure DevOps organization and project connection is already registered.", correlation_id=correlation_id)
        self._repository.save(connection)
        self._publish("AzureDevOpsConnectionRegistered", connection, correlation_id)
        return connection.to_public_dict()

    def list(self) -> list[dict[str, Any]]:
        return [item.to_public_dict() for item in self._repository.list()]

    def update(self, connection_id: str, value: dict[str, Any], *, correlation_id: str = "") -> dict[str, Any]:
        self._reject_plaintext(value)
        existing = self.require(connection_id)
        update_value = {**existing.to_storage_dict(), **value, "connectionId": connection_id}
        if not str(value.get("secretReference") or value.get("secret_reference") or "").strip():
            update_value["secretReference"] = existing.secret_reference
        updated = AzureDevOpsConnection.create(update_value)
        duplicate = self._repository.find_duplicate(updated.organization_url, updated.project_id)
        if duplicate and duplicate.connection_id != connection_id:
            raise AzureDevOpsValidationError(
                "This Azure DevOps organization and project connection is already registered.",
                correlation_id=correlation_id,
            )
        updated.created_at = existing.created_at
        updated.updated_at = _now()
        updated.status = AzureDevOpsConnectionStatus.PENDING_VALIDATION.value
        updated.last_validated_at = ""
        updated.validation_message = "Connection settings changed. Validate the connection before synchronization."
        self._repository.save(updated)
        self._publish("AzureDevOpsConnectionUpdated", updated, correlation_id)
        return updated.to_public_dict()

    def get(self, connection_id: str) -> dict[str, Any] | None:
        connection = self._repository.get(connection_id)
        return connection.to_public_dict() if connection else None

    def require(self, connection_id: str) -> AzureDevOpsConnection:
        connection = self._repository.get(connection_id)
        if not connection:
            raise AzureDevOpsNotFoundError(f"Azure DevOps connection '{connection_id}' was not found.")
        return connection

    def client(self, connection_id: str, correlation_id: str = ""):
        return self._factory.create(self.require(connection_id), correlation_id=correlation_id)

    def writer(self, connection_id: str, correlation_id: str = ""):
        factory_method = getattr(self._factory, "create_writer", None)
        if not callable(factory_method):
            raise AzureDevOpsValidationError("The configured Azure DevOps client factory does not support approved work-item automation.", correlation_id=correlation_id)
        return factory_method(self.require(connection_id), correlation_id=correlation_id)

    def pull_request_comment_writer(self, connection_id: str, correlation_id: str = ""):
        factory_method = getattr(self._factory, "create_pull_request_comment_writer", None)
        if not callable(factory_method):
            raise AzureDevOpsValidationError("The configured Azure DevOps client factory does not support approved pull-request comments.", correlation_id=correlation_id)
        return factory_method(self.require(connection_id), correlation_id=correlation_id)

    def validate(self, connection_id: str, *, correlation_id: str = "") -> dict[str, Any]:
        connection = self.require(connection_id)
        try:
            projects = self._factory.create(connection, correlation_id=correlation_id).list_projects()
            connection.status = AzureDevOpsConnectionStatus.CONNECTED.value
            connection.validation_message = f"Connection validated. {len(projects)} project(s) available."
            event = "AzureDevOpsConnectionValidated"
        except AzureDevOpsIntegrationError as error:
            connection.status = AzureDevOpsConnectionStatus.FAILED.value
            connection.validation_message = str(error)
            event = "AzureDevOpsConnectionFailed"
        connection.updated_at = connection.last_validated_at = _now()
        self._repository.save(connection)
        self._publish(event, connection, correlation_id, {"message": connection.validation_message})
        return connection.to_public_dict()

    def health(self, connection_id: str) -> dict[str, Any]:
        connection = self.require(connection_id)
        return {
            "connectionId": connection.connection_id,
            "status": connection.status,
            "healthy": connection.status == AzureDevOpsConnectionStatus.CONNECTED.value,
            "lastValidatedAt": connection.last_validated_at,
            "message": connection.validation_message,
            "credentialConfigured": bool(connection.secret_reference),
        }

    def _reject_plaintext(self, value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.replace("_", "").lower() in self._PLAINTEXT_FIELDS:
                    raise AzureDevOpsValidationError(f"Plaintext credential field '{key}' is not accepted; use secretReference.")
                self._reject_plaintext(item)
        elif isinstance(value, list):
            for item in value:
                self._reject_plaintext(item)

    def _publish(self, event_type: str, connection: AzureDevOpsConnection, correlation_id: str, extra: dict[str, Any] | None = None) -> None:
        if self._platform:
            self._platform.events.publish({"eventType": event_type, "source": "AzureDevOps", "projectId": connection.project_id, "correlationId": correlation_id, "payload": {"connectionId": connection.connection_id, **(extra or {})}})


class _ReadService:
    def __init__(self, connections: AzureDevOpsConnectionService, *, platform=None) -> None:
        self._connections = connections
        self._platform = platform

    def _read(self, connection_id: str, correlation_id: str, operation: Callable[[Any], Any]) -> Any:
        try:
            return operation(self._connections.client(connection_id, correlation_id))
        except AzureDevOpsIntegrationError as error:
            if self._platform:
                self._platform.events.publish({"eventType": "AzureDevOpsReadFailed", "source": "AzureDevOps", "correlationId": correlation_id, "payload": {"connectionId": connection_id, "errorCode": error.code}})
            raise


class AzureDevOpsProjectService(_ReadService):
    def list_organizations(self, connection_id: str) -> list[dict[str, Any]]:
        connection = self._connections.require(connection_id)
        return [{"name": connection.organization_name, "url": connection.organization_url}]

    def list_projects(self, connection_id: str, *, correlation_id: str = "", cancellation=None) -> list[dict[str, Any]]:
        values = self._read(connection_id, correlation_id, lambda client: client.list_projects(cancellation=cancellation))
        result = [public_model(map_project(item)) for item in values]
        if self._platform:
            for project in result:
                self._platform.events.publish({"eventType": "AzureDevOpsProjectDiscovered", "source": "AzureDevOps", "projectId": project["projectId"], "correlationId": correlation_id, "payload": {"connectionId": connection_id, "project": project}})
        return result

    def get_project(self, connection_id: str, project_id: str, *, correlation_id: str = "", cancellation=None) -> dict[str, Any]:
        return public_model(map_project(self._read(connection_id, correlation_id, lambda client: client.get_project(project_id, cancellation=cancellation))))

    def list_teams(self, connection_id: str, project_id: str, *, correlation_id: str = "", cancellation=None) -> list[dict[str, Any]]:
        return [public_model(map_team(item)) for item in self._read(connection_id, correlation_id, lambda client: client.list_teams(project_id, cancellation=cancellation))]


class AzureDevOpsWorkItemService(_ReadService):
    def query(self, connection_id: str, project: str, wiql: str, *, correlation_id: str = "", cancellation=None) -> list[dict[str, Any]]:
        if not wiql.strip().lower().startswith("select"):
            raise AzureDevOpsValidationError("WIQL must be a read-only SELECT query.")
        return [public_model(map_work_item(item)) for item in self._read(connection_id, correlation_id, lambda client: client.query_work_items(project, wiql, cancellation=cancellation))]

    def get_hierarchy(self, connection_id: str, project: str, work_item_id: int, *, correlation_id: str = "", cancellation=None) -> dict[str, Any]:
        return public_model(map_work_item(self._read(connection_id, correlation_id, lambda client: client.get_work_item(project, work_item_id, cancellation=cancellation))))

    def get_revisions(self, connection_id: str, project: str, work_item_id: int, *, correlation_id: str = "", cancellation=None) -> list[dict[str, Any]]:
        return [public_model(map_work_item(item)) for item in self._read(connection_id, correlation_id, lambda client: client.get_work_item_revisions(project, work_item_id, cancellation=cancellation))]

    def get_details(self, connection_id: str, project: str, work_item_id: int, *, correlation_id: str = "", cancellation=None) -> dict[str, Any]:
        def load(client):
            item = client.get_work_item(project, work_item_id, cancellation=cancellation)
            comments = _optional_pr_read(client, "get_work_item_comments", project, work_item_id, cancellation=cancellation)
            return {**item, "comments": comments}
        return public_model(map_work_item(self._read(connection_id, correlation_id, load)))


class AzureDevOpsRepositoryService(_ReadService):
    def list_repositories(self, connection_id: str, project: str, *, correlation_id: str = "", cancellation=None) -> list[dict[str, Any]]:
        return [public_model(map_repository(item)) for item in self._read(connection_id, correlation_id, lambda client: client.list_repositories(project, cancellation=cancellation))]

    def get_repository(self, connection_id: str, project: str, repository_id: str, *, correlation_id: str = "", cancellation=None) -> dict[str, Any]:
        return public_model(map_repository(self._read(connection_id, correlation_id, lambda client: client.get_repository(project, repository_id, cancellation=cancellation))))


class AzureDevOpsPullRequestService(_ReadService):
    def list_pull_requests(self, connection_id: str, project: str, repository_id: str = "", *, correlation_id: str = "", cancellation=None) -> list[dict[str, Any]]:
        return [public_model(map_pull_request(item)) for item in self._read(connection_id, correlation_id, lambda client: client.list_pull_requests(project, repository_id, cancellation=cancellation))]

    def get_pull_request(self, connection_id: str, project: str, repository_id: str, pull_request_id: int, *, correlation_id: str = "", cancellation=None) -> dict[str, Any]:
        return public_model(map_pull_request(self._read(connection_id, correlation_id, lambda client: client.get_pull_request(project, repository_id, pull_request_id, cancellation=cancellation))))

    def get_pull_request_context(self, connection_id: str, project: str, repository_id: str, pull_request_id: int, *, correlation_id: str = "", cancellation=None) -> dict[str, Any]:
        client = self._connections.client(connection_id, correlation_id)
        pull_request = client.get_pull_request(project, repository_id, pull_request_id, cancellation=cancellation)
        commits = _optional_pr_read(client, "get_pull_request_commits", project, repository_id, pull_request_id, cancellation=cancellation)
        work_items = _optional_pr_read(client, "get_pull_request_work_items", project, repository_id, pull_request_id, cancellation=cancellation)
        iterations = _optional_pr_read(client, "get_pull_request_iterations", project, repository_id, pull_request_id, cancellation=cancellation)
        latest_iteration = max((int(item.get("id") or 0) for item in iterations), default=0)
        changes = _optional_pr_read(client, "get_pull_request_iteration_changes", project, repository_id, pull_request_id, latest_iteration, cancellation=cancellation) if latest_iteration else []
        enriched = {
            **pull_request,
            "commits": commits,
            "linkedWorkItemIds": [str(item.get("id")) for item in work_items if item.get("id")],
            "changedFiles": [_normalize_pr_change(item) for item in changes],
        }
        return public_model(map_pull_request(enriched))

    def list_builds(self, connection_id: str, project: str, *, correlation_id: str = "", cancellation=None) -> list[dict[str, Any]]:
        return [public_model(map_build(item)) for item in self._read(connection_id, correlation_id, lambda client: client.list_builds(project, cancellation=cancellation))]


class AzureDevOpsIterationService(_ReadService):
    def list_iterations(self, connection_id: str, project: str, *, correlation_id: str = "", cancellation=None) -> list[dict[str, Any]]:
        return [public_model(map_iteration(item)) for item in self._read(connection_id, correlation_id, lambda client: client.list_iterations(project, cancellation=cancellation))]

    def get_current_sprint(self, connection_id: str, project: str, *, correlation_id: str = "", cancellation=None) -> dict[str, Any] | None:
        iterations = self.list_iterations(connection_id, project, correlation_id=correlation_id, cancellation=cancellation)
        return next((item for item in iterations if str(item.get("timeFrame", "")).lower() == "current"), None)


class AzureDevOpsWebhookService:
    """Normalizes inbound service-hook notifications without writing to Azure DevOps."""

    def __init__(self, connections: AzureDevOpsConnectionService, *, platform=None) -> None:
        self._connections = connections
        self._platform = platform

    def handle(self, connection_id: str, payload: dict[str, Any], *, correlation_id: str = "") -> dict[str, Any]:
        self._connections.require(connection_id)
        result = {"connectionId": connection_id, "eventType": str(payload.get("eventType") or "Unknown"), "resourceId": str((payload.get("resource") or {}).get("id") or ""), "correlationId": correlation_id, "accepted": True}
        if self._platform:
            self._platform.events.publish({"eventType": "AzureDevOpsWebhookReceived", "source": "AzureDevOps", "correlationId": correlation_id, "payload": result})
        return result
