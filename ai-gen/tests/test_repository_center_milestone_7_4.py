from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.repository_intelligence import register_repository_intelligence
from backend.repository_intelligence.api.router import build_repository_router
from backend.repository_intelligence.domain import (
    EngineeringGraph,
    EngineeringNode,
    EngineeringNodeType,
    RepositorySnapshot,
)


class RepositoryCenterMilestone74Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = tempfile.TemporaryDirectory()
        self.module = register_repository_intelligence(Path(self.storage.name))
        app = FastAPI()
        app.include_router(build_repository_router(self.module))
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.storage.cleanup()

    def create_repository(self, name: str, suffix: str = "repo") -> dict:
        return self.module.application.create_repository({
            "name": name,
            "url": f"https://github.com/hei/{suffix}",
            "repositoryType": "GitHub",
            "authenticationType": "None",
        })

    def test_large_repository_health_is_summarized_and_bounded(self) -> None:
        repository = self.create_repository("Enterprise Platform", "enterprise-platform")
        repository_id = repository["repositoryId"]
        snapshot = RepositorySnapshot(
            snapshot_id="snapshot-large", repository_id=repository_id, version=12,
            branch="main", commit_id="abc123", total_files=125_000,
            languages={"TypeScript": 70_000, "C#": 55_000},
            modules=[f"Module {index}" for index in range(500)], status="Completed",
        )
        self.module.snapshot_service.save_snapshot(snapshot)
        graph = EngineeringGraph(
            graph_id="graph-large", repository_id=repository_id,
            nodes=[
                EngineeringNode(node_id=f"module-{index}", repository_id=repository_id, node_type=EngineeringNodeType.MODULE, name=f"Module {index}")
                for index in range(500)
            ] + [
                EngineeringNode(node_id=f"service-{index}", repository_id=repository_id, node_type=EngineeringNodeType.SERVICE, name=f"Service {index}")
                for index in range(400)
            ],
        )
        self.module.graph_service.save_graph(graph)

        response = self.client.get(f"/repositories/{repository_id}/health")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(125_000, payload["filesIndexed"])
        self.assertEqual(500, payload["engineeringGraph"]["counts"]["Module"])
        self.assertEqual(100, len(payload["modules"]))
        self.assertEqual(100, len(payload["services"]))

    def test_multiple_repositories_are_visible(self) -> None:
        self.create_repository("GridHub", "gridhub")
        self.create_repository("LineDefender", "linedefender")

        response = self.client.get("/repositories")

        self.assertEqual(200, response.status_code)
        self.assertEqual(2, response.json()["count"])
        self.assertEqual({"GridHub", "LineDefender"}, {item["name"] for item in response.json()["repositories"]})

    def test_offline_repository_preserves_previous_snapshot(self) -> None:
        repository = self.create_repository("Offline Repository", "offline")
        repository_id = repository["repositoryId"]
        self.module.snapshot_service.save_snapshot(RepositorySnapshot(
            snapshot_id="snapshot-before-outage", repository_id=repository_id,
            total_files=42, modules=["Fault Monitoring"], status="Completed",
        ))
        self.module.application.scan_repository(repository_id, mode="Incremental", root_path="/path/that/does/not/exist")

        health = self.client.get(f"/repositories/{repository_id}/health").json()
        snapshot = self.client.get(f"/repositories/{repository_id}/snapshot").json()

        self.assertEqual("Offline", health["availability"])
        self.assertEqual("snapshot-before-outage", snapshot["snapshotId"])
        self.assertIn("previous completed snapshot remains available", " ".join(health["warnings"]).lower())

    def test_repository_unavailable_returns_actionable_not_found(self) -> None:
        health = self.client.get("/repositories/missing/health")
        snapshot = self.client.get("/repositories/missing/snapshot")
        details = self.client.get("/repositories/missing")

        self.assertEqual(404, health.status_code)
        self.assertEqual(404, snapshot.status_code)
        self.assertEqual(404, details.status_code)
        self.assertIn("was not found", health.json()["error"])

    def test_required_repository_center_api_contracts(self) -> None:
        repository = self.create_repository("API Repository", "api-repository")
        repository_id = repository["repositoryId"]
        self.module.snapshot_service.save_snapshot(RepositorySnapshot(
            snapshot_id="snapshot-api", repository_id=repository_id, total_files=5, status="Completed",
        ))

        self.assertEqual(200, self.client.get("/repositories").status_code)
        self.assertEqual(200, self.client.get(f"/repositories/{repository_id}").status_code)
        self.assertEqual(200, self.client.get(f"/repositories/{repository_id}/health").status_code)
        self.assertEqual(200, self.client.get(f"/repositories/{repository_id}/snapshot").status_code)


if __name__ == "__main__":
    unittest.main()
