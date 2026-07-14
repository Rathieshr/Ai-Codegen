"""Normalized Azure DevOps operations exposed through the HEI Platform SDK."""

from __future__ import annotations

from typing import Any


class HEIAzureDevOpsSdk:
    """Keeps intelligence services independent from ADO clients and stores."""

    def __init__(self, integration: Any) -> None:
        self._integration = integration

    def cache_snapshot(self, project_id: str) -> dict[str, Any]:
        return self._integration.sync.cache.snapshot(project_id)

    def find_cached(self, collection: str, entity_id: str, project_id: str = ""):
        return self._integration.sync.cache.find(collection, str(entity_id), project_id)

    def cached_collection(self, project_id: str, collection: str) -> dict[str, dict[str, Any]]:
        return self._integration.sync.cache.collection(project_id, collection)

    def cache_upsert(self, project_id: str, collection: str, entity_id: str, value: dict[str, Any]) -> str:
        return self._integration.sync.cache.upsert(project_id, collection, str(entity_id), value)

    def pull_request_context(self, connection_id: str, project_id: str, repository_id: str, pull_request_id: int, *, correlation_id: str = "") -> dict[str, Any]:
        return self._integration.pull_requests.get_pull_request_context(connection_id, project_id, repository_id, pull_request_id, correlation_id=correlation_id)

    def public_connection(self, connection_id: str) -> dict[str, Any]:
        return self._integration.connections.get(connection_id) or {}

    def post_pull_request_comment(self, connection_id: str, project_id: str, repository_id: str, pull_request_id: int, content: str, *, correlation_id: str = "") -> dict[str, Any]:
        writer = self._integration.connections.pull_request_comment_writer(connection_id, correlation_id)
        return writer.add_comment(project_id, repository_id, pull_request_id, content)

    def request_reconciliation(self, connection_id: str, project_id: str, *, correlation_id: str = "") -> dict[str, Any]:
        return self._integration.sync.request_reconciliation(connection_id, project_id, correlation_id=correlation_id)

    def receive_webhook(self, payload: dict[str, Any], *, correlation_id: str = "") -> dict[str, Any]:
        return self._integration.sync.receive_webhook(payload, correlation_id=correlation_id)

    def validate_connection(self, connection_id: str, *, correlation_id: str = "") -> dict[str, Any]:
        return self._integration.connections.validate(connection_id, correlation_id=correlation_id)

    def list_connections(self) -> list[dict[str, Any]]:
        return self._integration.connections.list()


def as_azure_devops_sdk(value: Any) -> HEIAzureDevOpsSdk:
    return value if isinstance(value, HEIAzureDevOpsSdk) else HEIAzureDevOpsSdk(value)
