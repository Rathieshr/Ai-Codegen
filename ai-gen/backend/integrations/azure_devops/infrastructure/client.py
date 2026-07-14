"""Resilient, read-only Azure DevOps REST client."""

from __future__ import annotations

import json
import time
from typing import Any, Callable
from urllib.parse import quote, urlencode

from ..domain import (
    AzureDevOpsAuthenticationError,
    AzureDevOpsAuthorizationError,
    AzureDevOpsCancelledError,
    AzureDevOpsConnection,
    AzureDevOpsIntegrationError,
    AzureDevOpsNotFoundError,
    AzureDevOpsRateLimitError,
    AzureDevOpsTimeoutError,
    AzureDevOpsUnavailableError,
)
from .http import CancellationToken, HttpResponse, IHttpExecutor, UrllibHttpExecutor


class AzureDevOpsReadClient:
    """Contains no Azure DevOps mutation operation by design."""

    def __init__(self, connection: AzureDevOpsConnection, credential_provider, *, correlation_id: str = "", executor: IHttpExecutor | None = None, timeout_seconds: float = 15, max_attempts: int = 3, sleeper: Callable[[float], None] = time.sleep) -> None:
        self._connection = connection
        self._credentials = credential_provider
        self._correlation_id = correlation_id
        self._executor = executor or UrllibHttpExecutor()
        self._timeout = timeout_seconds
        self._max_attempts = max(1, max_attempts)
        self._sleeper = sleeper

    def list_projects(self, *, cancellation=None) -> list[dict[str, Any]]:
        return self._paged("/_apis/projects", cancellation=cancellation)

    def get_project(self, project_id: str, *, cancellation=None) -> dict[str, Any]:
        return self._value(f"/_apis/projects/{quote(project_id, safe='')}", cancellation=cancellation)

    def list_teams(self, project_id: str, *, cancellation=None) -> list[dict[str, Any]]:
        return self._paged(f"/_apis/projects/{quote(project_id, safe='')}/teams", cancellation=cancellation)

    def list_iterations(self, project: str, *, cancellation=None) -> list[dict[str, Any]]:
        return self._paged(f"/{quote(project, safe='')}/_apis/work/teamsettings/iterations", cancellation=cancellation)

    def query_work_items(self, project: str, wiql: str, *, cancellation=None) -> list[dict[str, Any]]:
        result = self._value(f"/{quote(project, safe='')}/_apis/wit/wiql", method="POST", payload={"query": wiql}, cancellation=cancellation)
        ids = [int(item["id"]) for item in result.get("workItems", []) if item.get("id")]
        records: list[dict[str, Any]] = []
        for offset in range(0, len(ids), 200):
            query = {"ids": ",".join(map(str, ids[offset:offset + 200])), "$expand": "Relations"}
            records.extend(self._paged(f"/{quote(project, safe='')}/_apis/wit/workitems", query=query, cancellation=cancellation))
        return records

    def get_work_item(self, project: str, work_item_id: int, *, cancellation=None) -> dict[str, Any]:
        return self._value(f"/{quote(project, safe='')}/_apis/wit/workitems/{work_item_id}", query={"$expand": "Relations"}, cancellation=cancellation)

    def get_work_item_revisions(self, project: str, work_item_id: int, *, cancellation=None) -> list[dict[str, Any]]:
        return self._paged(f"/{quote(project, safe='')}/_apis/wit/workitems/{work_item_id}/revisions", cancellation=cancellation)

    def list_repositories(self, project: str, *, cancellation=None) -> list[dict[str, Any]]:
        return self._paged(f"/{quote(project, safe='')}/_apis/git/repositories", cancellation=cancellation)

    def get_repository(self, project: str, repository_id: str, *, cancellation=None) -> dict[str, Any]:
        return self._value(f"/{quote(project, safe='')}/_apis/git/repositories/{quote(repository_id, safe='')}", cancellation=cancellation)

    def list_pull_requests(self, project: str, repository_id: str = "", *, cancellation=None) -> list[dict[str, Any]]:
        suffix = f"/{quote(repository_id, safe='')}" if repository_id else ""
        return self._paged(f"/{quote(project, safe='')}/_apis/git/repositories{suffix}/pullrequests", query={"searchCriteria.status": "all"}, cancellation=cancellation)

    def get_pull_request(self, project: str, repository_id: str, pull_request_id: int, *, cancellation=None) -> dict[str, Any]:
        return self._value(f"/{quote(project, safe='')}/_apis/git/repositories/{quote(repository_id, safe='')}/pullrequests/{pull_request_id}", cancellation=cancellation)

    def get_pull_request_commits(self, project: str, repository_id: str, pull_request_id: int, *, cancellation=None) -> list[dict[str, Any]]:
        return self._paged(f"/{quote(project, safe='')}/_apis/git/repositories/{quote(repository_id, safe='')}/pullrequests/{pull_request_id}/commits", cancellation=cancellation)

    def get_pull_request_work_items(self, project: str, repository_id: str, pull_request_id: int, *, cancellation=None) -> list[dict[str, Any]]:
        return self._paged(f"/{quote(project, safe='')}/_apis/git/repositories/{quote(repository_id, safe='')}/pullrequests/{pull_request_id}/workitems", cancellation=cancellation)

    def get_pull_request_iterations(self, project: str, repository_id: str, pull_request_id: int, *, cancellation=None) -> list[dict[str, Any]]:
        return self._paged(f"/{quote(project, safe='')}/_apis/git/repositories/{quote(repository_id, safe='')}/pullrequests/{pull_request_id}/iterations", cancellation=cancellation)

    def get_pull_request_iteration_changes(self, project: str, repository_id: str, pull_request_id: int, iteration_id: int, *, cancellation=None) -> list[dict[str, Any]]:
        payload = self._value(f"/{quote(project, safe='')}/_apis/git/repositories/{quote(repository_id, safe='')}/pullrequests/{pull_request_id}/iterations/{iteration_id}/changes", cancellation=cancellation)
        return [item for item in payload.get("changeEntries") or payload.get("value") or [] if isinstance(item, dict)]

    def list_builds(self, project: str, *, cancellation=None) -> list[dict[str, Any]]:
        return self._paged(f"/{quote(project, safe='')}/_apis/build/builds", cancellation=cancellation)

    def _paged(self, path: str, *, query: dict[str, Any] | None = None, cancellation: CancellationToken | None = None) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        token = ""
        while True:
            page_query = dict(query or {})
            if token:
                page_query["continuationToken"] = token
            response = self._request("GET", path, query=page_query, cancellation=cancellation)
            body = response.payload if isinstance(response.payload, dict) else {}
            values.extend(item for item in body.get("value", []) if isinstance(item, dict))
            token = response.headers.get("x-ms-continuationtoken", "")
            if not token:
                return values

    def _value(self, path: str, *, method: str = "GET", query: dict[str, Any] | None = None, payload: dict[str, Any] | None = None, cancellation: CancellationToken | None = None) -> dict[str, Any]:
        response = self._request(method, path, query=query, payload=payload, cancellation=cancellation)
        return response.payload if isinstance(response.payload, dict) else {}

    def _request(self, method: str, path: str, *, query: dict[str, Any] | None = None, payload: dict[str, Any] | None = None, cancellation: CancellationToken | None = None) -> HttpResponse:
        if method not in {"GET", "POST"}:
            raise ValueError("AzureDevOpsReadClient supports safe reads and WIQL queries only.")
        query_value = {"api-version": "7.1", **(query or {})}
        url = f"{self._connection.organization_url}{path}?{urlencode(query_value)}"
        headers = {"Accept": "application/json", "Content-Type": "application/json", "X-Correlation-ID": self._correlation_id}
        headers.update(self._credentials.authorization_headers(self._connection, self._correlation_id))
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        last_error: AzureDevOpsIntegrationError | None = None
        for attempt in range(1, self._max_attempts + 1):
            if cancellation and cancellation.cancelled:
                raise AzureDevOpsCancelledError(correlation_id=self._correlation_id)
            try:
                response = self._executor.execute(method, url, headers, body, self._timeout, cancellation)
                if response.status < 400:
                    return response
                error = self._http_error(response)
            except (AzureDevOpsTimeoutError, AzureDevOpsUnavailableError) as caught:
                error = caught
                error.correlation_id = error.correlation_id or self._correlation_id
            if not error.retryable or attempt == self._max_attempts:
                raise error
            last_error = error
            delay = getattr(error, "retry_after_seconds", 0) or min(0.25 * (2 ** (attempt - 1)), 2.0)
            if cancellation and cancellation.wait(delay):
                raise AzureDevOpsCancelledError(correlation_id=self._correlation_id)
            if not cancellation:
                self._sleeper(delay)
        raise last_error or AzureDevOpsUnavailableError(correlation_id=self._correlation_id)

    def _http_error(self, response: HttpResponse) -> AzureDevOpsIntegrationError:
        message = _message(response.payload)
        kwargs = {"status": response.status, "correlation_id": self._correlation_id}
        if response.status == 401:
            return AzureDevOpsAuthenticationError(message or "Azure DevOps credentials were rejected.", **kwargs)
        if response.status == 403:
            return AzureDevOpsAuthorizationError(message or "Azure DevOps permission was denied.", **kwargs)
        if response.status == 404:
            return AzureDevOpsNotFoundError(message or "Azure DevOps resource was not found.", **kwargs)
        if response.status == 429:
            try:
                retry_after = float(response.headers.get("retry-after", "0"))
            except ValueError:
                retry_after = 0
            return AzureDevOpsRateLimitError(message or "Azure DevOps rate limit was exceeded.", retry_after_seconds=retry_after, **kwargs)
        return AzureDevOpsUnavailableError(message or "Azure DevOps read failed.", **kwargs)


def _message(payload: Any) -> str:
    return str(payload.get("message") or payload.get("error", {}).get("message") or "") if isinstance(payload, dict) else ""
