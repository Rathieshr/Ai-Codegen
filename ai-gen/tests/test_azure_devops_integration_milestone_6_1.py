from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.integrations.azure_devops import build_azure_devops_router
from backend.integrations.azure_devops.application import AzureDevOpsConnectionService, AzureDevOpsProjectService
from backend.integrations.azure_devops.bootstrap import register_azure_devops_integration
from backend.integrations.azure_devops.domain import (
    AzureDevOpsAuthenticationError, AzureDevOpsCancelledError, AzureDevOpsConnection,
    AzureDevOpsConnectionStatus, AzureDevOpsTimeoutError, AzureDevOpsValidationError,
)
from backend.integrations.azure_devops.infrastructure import (
    AzureDevOpsConnectionRepository, AzureDevOpsReadClient, CancellationToken, HttpResponse,
)
from backend.integrations.azure_devops.mapping import map_pull_request, map_repository, map_work_item
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore


class StaticCredentials:
    def authorization_headers(self, connection, correlation_id=""):
        return {"Authorization": "Basic redacted"}


class SequenceExecutor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def execute(self, method, url, headers, body, timeout, cancellation=None):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, *, projects=None, error=None):
        self.projects = projects or []
        self.error = error
        self.correlation_id = ""

    def list_projects(self, **kwargs):
        if self.error:
            raise self.error
        return self.projects

    def get_project(self, project_id, **kwargs): return {"id": project_id, "name": "GridHub"}
    def list_teams(self, project_id, **kwargs): return []
    def list_iterations(self, project, **kwargs): return []
    def query_work_items(self, project, wiql, **kwargs): return []
    def get_work_item(self, project, work_item_id, **kwargs): return {"id": work_item_id, "fields": {"System.Title": "Story"}}
    def get_work_item_revisions(self, project, work_item_id, **kwargs): return []
    def list_repositories(self, project, **kwargs): return []
    def get_repository(self, project, repository_id, **kwargs): return {"id": repository_id, "name": "Repo"}
    def list_pull_requests(self, project, repository_id="", **kwargs): return []
    def get_pull_request(self, project, repository_id, pull_request_id, **kwargs): return {"pullRequestId": pull_request_id, "title": "PR", "status": "active"}
    def list_builds(self, project, **kwargs): return []


class FakeFactory:
    def __init__(self, client):
        self.client = client
        self.created = []

    def create(self, connection, *, correlation_id=""):
        self.created.append((connection.connection_id, correlation_id))
        self.client.correlation_id = correlation_id
        return self.client


def connection():
    return AzureDevOpsConnection.create({
        "connectionId": "ado-1", "organizationUrl": "https://dev.azure.com/hei",
        "organizationName": "hei", "authenticationMode": "PAT", "secretReference": "ADO_HEI_PAT",
    })


class AzureDevOpsIntegrationMilestone61Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _service(self, client=None):
        repository = AzureDevOpsConnectionRepository(JsonMapStore(self.root / "connections.json"))
        factory = FakeFactory(client or FakeClient())
        return AzureDevOpsConnectionService(repository, factory), repository, factory

    def test_connection_registration_never_stores_or_returns_plaintext_credentials(self):
        service, _, _ = self._service()
        result = service.register({"organizationUrl": "https://dev.azure.com/hei", "authenticationMode": "PAT", "secretReference": "ADO_HEI_PAT"})
        stored = (self.root / "connections.json").read_text()
        self.assertNotIn("secretReference", json.dumps(result))
        self.assertIn("ADO_HEI_PAT", stored)
        self.assertNotIn("actual-pat-value", stored)
        with self.assertRaises(AzureDevOpsValidationError):
            service.register({"organizationUrl": "https://dev.azure.com/other", "authenticationMode": "PAT", "secretReference": "REF", "pat": "actual-pat-value"})

    def test_api_rejects_plaintext_without_echoing_the_credential(self):
        app = FastAPI()
        module = register_azure_devops_integration(self.root, client_factory=FakeFactory(FakeClient()))
        app.include_router(build_azure_devops_router(module))
        response = TestClient(app).post("/integrations/azure-devops/connections", json={
            "organizationUrl": "https://dev.azure.com/hei",
            "authenticationMode": "PAT",
            "secretReference": "ADO_HEI_PAT",
            "pat": "never-return-this-value",
        })
        self.assertEqual(400, response.status_code)
        self.assertNotIn("never-return-this-value", response.text)

    def test_successful_validation_sets_connected_status(self):
        service, _, factory = self._service(FakeClient(projects=[{"id": "p1", "name": "GridHub"}]))
        item = service.register({"organizationUrl": "https://dev.azure.com/hei", "authenticationMode": "PAT", "secretReference": "REF"})
        result = service.validate(item["connectionId"], correlation_id="corr-validation")
        self.assertEqual(AzureDevOpsConnectionStatus.CONNECTED.value, result["status"])
        self.assertEqual("corr-validation", factory.created[-1][1])

    def test_failed_connection_can_be_corrected_without_exposing_credentials(self):
        service, repository, _ = self._service(FakeClient(error=AzureDevOpsAuthenticationError("Invalid credential.")))
        item = service.register({
            "organizationUrl": "https://dev.azure.com/wrong", "projectId": "p1",
            "authenticationMode": "PAT", "secretReference": "WRONG_PAT",
        })
        failed = service.validate(item["connectionId"])
        self.assertEqual(AzureDevOpsConnectionStatus.FAILED.value, failed["status"])

        corrected = service.update(item["connectionId"], {
            "organizationUrl": "https://dev.azure.com/hei", "projectId": "p1",
            "authenticationMode": "PAT", "secretReference": "ADO_HEI_PAT",
        }, correlation_id="corr-correction")

        self.assertEqual(item["connectionId"], corrected["connectionId"])
        self.assertEqual(AzureDevOpsConnectionStatus.PENDING_VALIDATION.value, corrected["status"])
        self.assertEqual("https://dev.azure.com/hei", corrected["organizationUrl"])
        self.assertNotIn("secretReference", corrected)
        self.assertEqual("ADO_HEI_PAT", repository.get(item["connectionId"]).secret_reference)

    def test_connection_update_api_resets_failed_validation(self):
        app = FastAPI()
        module = register_azure_devops_integration(self.root, client_factory=FakeFactory(FakeClient()))
        item = module.connections.register({
            "organizationUrl": "https://dev.azure.com/wrong", "projectId": "p1",
            "authenticationMode": "PAT", "secretReference": "WRONG_PAT",
        })
        app.include_router(build_azure_devops_router(module))
        response = TestClient(app).put(
            f"/integrations/azure-devops/connections/{item['connectionId']}",
            json={
                "organizationUrl": "https://dev.azure.com/hei", "projectId": "p1",
                "authenticationMode": "PAT", "secretReference": "ADO_HEI_PAT",
            },
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(AzureDevOpsConnectionStatus.PENDING_VALIDATION.value, response.json()["status"])
        self.assertNotIn("ADO_HEI_PAT", response.text)

    def test_invalid_credentials_are_not_retried_by_read_client(self):
        executor = SequenceExecutor([HttpResponse(401, {}, {"message": "bad credential"})])
        client = AzureDevOpsReadClient(connection(), StaticCredentials(), executor=executor, max_attempts=3, sleeper=lambda _: None)
        with self.assertRaises(AzureDevOpsAuthenticationError):
            client.list_projects()
        self.assertEqual(1, len(executor.calls))

    def test_unavailable_organization_retries_safe_read(self):
        executor = SequenceExecutor([HttpResponse(503, {}, {}), HttpResponse(503, {}, {}), HttpResponse(200, {}, {"value": []})])
        client = AzureDevOpsReadClient(connection(), StaticCredentials(), executor=executor, max_attempts=3, sleeper=lambda _: None)
        self.assertEqual([], client.list_projects())
        self.assertEqual(3, len(executor.calls))

    def test_project_discovery_normalizes_dto_and_propagates_correlation(self):
        platform = PlatformFoundation(self.root / "platform")
        repository = AzureDevOpsConnectionRepository(JsonMapStore(self.root / "connections.json"))
        repository.save(connection())
        factory = FakeFactory(FakeClient(projects=[{"id": "p1", "name": "GridHub", "visibility": "private"}]))
        connections = AzureDevOpsConnectionService(repository, factory, platform=platform)
        projects = AzureDevOpsProjectService(connections, platform=platform).list_projects("ado-1", correlation_id="corr-project")
        self.assertEqual({"projectId": "p1", "name": "GridHub", "description": "", "state": "", "visibility": "private", "url": ""}, projects[0])
        events = platform.events.list_recent("AzureDevOpsProjectDiscovered")["events"]
        self.assertEqual("corr-project", events[0]["correlationId"])

    def test_work_item_query_handles_provider_pagination_and_batch_fetch(self):
        executor = SequenceExecutor([
            HttpResponse(200, {}, {"workItems": [{"id": 1}, {"id": 2}]}),
            HttpResponse(200, {}, {"value": [{"id": 1}, {"id": 2}]}),
        ])
        client = AzureDevOpsReadClient(connection(), StaticCredentials(), executor=executor, sleeper=lambda _: None)
        result = client.query_work_items("GridHub", "SELECT [System.Id] FROM WorkItems")
        self.assertEqual([1, 2], [item["id"] for item in result])
        self.assertEqual("POST", executor.calls[0]["method"])
        self.assertIn("ids=1%2C2", executor.calls[1]["url"])

    def test_pull_request_pagination_uses_continuation_token(self):
        executor = SequenceExecutor([
            HttpResponse(200, {"x-ms-continuationtoken": "next"}, {"value": [{"pullRequestId": 1}]}),
            HttpResponse(200, {}, {"value": [{"pullRequestId": 2}]}),
        ])
        client = AzureDevOpsReadClient(connection(), StaticCredentials(), executor=executor, sleeper=lambda _: None)
        self.assertEqual([1, 2], [item["pullRequestId"] for item in client.list_pull_requests("GridHub")])
        self.assertIn("continuationToken=next", executor.calls[1]["url"])

    def test_rate_limit_honors_retry_before_success(self):
        delays = []
        executor = SequenceExecutor([HttpResponse(429, {"retry-after": "0.01"}, {}), HttpResponse(200, {}, {"value": []})])
        client = AzureDevOpsReadClient(connection(), StaticCredentials(), executor=executor, sleeper=delays.append)
        self.assertEqual([], client.list_projects())
        self.assertEqual([0.01], delays)

    def test_timeout_and_cancellation_are_typed(self):
        executor = SequenceExecutor([AzureDevOpsTimeoutError(), AzureDevOpsTimeoutError(), AzureDevOpsTimeoutError()])
        client = AzureDevOpsReadClient(connection(), StaticCredentials(), executor=executor, max_attempts=3, sleeper=lambda _: None)
        with self.assertRaises(AzureDevOpsTimeoutError):
            client.list_projects()
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(AzureDevOpsCancelledError):
            client.list_projects(cancellation=token)

    def test_provider_dtos_are_normalized_before_return(self):
        repository = map_repository({"id": "r1", "name": "API", "defaultBranch": "refs/heads/main", "project": {"id": "p1", "name": "GridHub"}})
        work_item = map_work_item({"id": 12, "rev": 4, "fields": {"System.Title": "Device Health", "System.WorkItemType": "User Story"}})
        pull_request = map_pull_request({"pullRequestId": 7, "title": "Health", "status": "active", "repository": {"id": "r1"}})
        self.assertEqual(("r1", "p1"), (repository.repository_id, repository.project_id))
        self.assertEqual((12, "User Story"), (work_item.work_item_id, work_item.work_item_type))
        self.assertEqual((7, "r1"), (pull_request.pull_request_id, pull_request.repository_id))

    def test_module_registration_exposes_all_read_services(self):
        module = register_azure_devops_integration(self.root, client_factory=FakeFactory(FakeClient()))
        self.assertIsNotNone(module.connections)
        self.assertIsNotNone(module.projects)
        self.assertIsNotNone(module.work_items)
        self.assertIsNotNone(module.repositories)
        self.assertIsNotNone(module.pull_requests)
        self.assertIsNotNone(module.iterations)
        self.assertIsNotNone(module.webhooks)

    def test_read_client_has_no_azure_devops_write_operations(self):
        forbidden = {"create_work_item", "update_work_item", "delete_work_item", "create_pull_request", "queue_build"}
        self.assertTrue(forbidden.isdisjoint(set(dir(AzureDevOpsReadClient))))


if __name__ == "__main__":
    unittest.main()
