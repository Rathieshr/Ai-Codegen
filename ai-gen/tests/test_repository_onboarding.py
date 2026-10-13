from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.intelligence.repository import RepositoryOnboardingEngine, RepositorySnapshotStore


class RepositoryOnboardingEngineTests(unittest.TestCase):
    def _repo(self, root: Path) -> None:
        (root / "src" / "api" / "Controllers").mkdir(parents=True)
        (root / "src" / "api" / "Services").mkdir(parents=True)
        (root / "src" / "api" / "Repositories").mkdir(parents=True)
        (root / "docs").mkdir()
        (root / "LineDefender.sln").write_text("", encoding="utf-8")
        (root / "src" / "api" / "LineDefender.Api.csproj").write_text(
            """
            <Project Sdk="Microsoft.NET.Sdk.Web">
              <PackageReference Include="Microsoft.AspNetCore.Authentication.JwtBearer" Version="8.0.0" />
              <PackageReference Include="Dapper" Version="2.0.0" />
              <PackageReference Include="xunit" Version="2.6.0" />
            </Project>
            """,
            encoding="utf-8",
        )
        (root / "README.md").write_text(
            """
            # LineDefender
            ASP.NET operations platform with JWT authentication.
            Operators review telemetry, critical fault events, device health, and outage investigations.
            The system uses structured logging, authorization checks, validation, and unit tests.
            Architecture follows controller, service, repository layers.
            """,
            encoding="utf-8",
        )
        (root / "docs" / "architecture.md").write_text(
            "Clean Architecture with Controller, Service, Repository and Dependency Injection.",
            encoding="utf-8",
        )
        (root / "src" / "api" / "Controllers" / "FaultEventController.cs").write_text(
            """
            [ApiController]
            public class FaultEventController : ControllerBase {
              public IActionResult GetCriticalFaultEvent() => Ok();
            }
            """,
            encoding="utf-8",
        )
        (root / "src" / "api" / "Services" / "TelemetryService.cs").write_text(
            "public class TelemetryService { public void PublishTelemetry() {} }",
            encoding="utf-8",
        )
        (root / "src" / "api" / "Repositories" / "FaultEventRepository.cs").write_text(
            "public class FaultEventRepository { }",
            encoding="utf-8",
        )

    def test_repository_onboarding_builds_versioned_snapshot_and_knowledge(self) -> None:
        with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as store_dir:
            root = Path(repo_dir)
            self._repo(root)
            engine = RepositoryOnboardingEngine(store=RepositorySnapshotStore(store_dir))

            result = engine.buildRepositorySnapshot({"path": str(root), "repositoryId": "LineDefender"})
            snapshot = result["repositorySnapshot"]
            registry = result["knowledgeRegistry"]

        self.assertEqual(snapshot["scanVersion"], 1)
        self.assertIn("ASP.NET", [item["name"] for item in snapshot["technologies"]])
        self.assertIn("JWT", [item["name"] for item in snapshot["technologies"]])
        self.assertIn("Fault Monitoring", registry["modules"])
        self.assertIn("Telemetry", registry["modules"])
        self.assertIn("Outage Investigation", registry["flows"])
        self.assertIn("Repository Pattern", registry["patterns"])
        self.assertGreater(snapshot["graphStatistics"]["nodes"], 0)
        self.assertEqual(result["repositoryDrift"]["status"], "initial_snapshot")

    def test_snapshot_store_keeps_history_and_drift_between_versions(self) -> None:
        with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as store_dir:
            root = Path(repo_dir)
            self._repo(root)
            engine = RepositoryOnboardingEngine(store=RepositorySnapshotStore(store_dir))

            first = engine.buildRepositorySnapshot({"path": str(root), "repositoryId": "LineDefender"})
            (root / "src" / "api" / "Services" / "FirmwareRolloutService.cs").write_text(
                "public class FirmwareRolloutService { public void UpgradeFirmware() {} }",
                encoding="utf-8",
            )
            second = engine.buildRepositorySnapshot({"path": str(root), "repositoryId": "LineDefender"})
            history = engine.store.list_snapshots("LineDefender")

        self.assertEqual(first["repositorySnapshot"]["scanVersion"], 1)
        self.assertEqual(second["repositorySnapshot"]["scanVersion"], 2)
        self.assertEqual([snapshot.scan_version for snapshot in history], [1, 2])
        self.assertEqual(second["repositoryDrift"]["status"], "changed")
        self.assertIn("Firmware", second["repositoryDrift"]["added"]["Modules"])

    def test_engineering_graph_contains_repository_knowledge_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as store_dir:
            root = Path(repo_dir)
            self._repo(root)
            engine = RepositoryOnboardingEngine(store=RepositorySnapshotStore(store_dir))

            result = engine.buildRepositorySnapshot({"path": str(root), "repositoryId": "LineDefender"})
            graph = result["engineeringGraph"]

        node_names = {node["name"] for node in graph["nodes"]}
        self.assertIn("LineDefender", node_names)
        self.assertIn("Fault Monitoring", node_names)
        self.assertIn("Fault Event Review Flow", node_names)
        self.assertIn("README.md", node_names)

    def test_unknown_languages_are_still_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as store_dir:
            root = Path(repo_dir)
            (root / "custom.foo").write_text("fault telemetry custom syntax", encoding="utf-8")
            engine = RepositoryOnboardingEngine(store=RepositorySnapshotStore(store_dir))

            result = engine.buildRepositorySnapshot({"path": str(root), "repositoryId": "UnknownRepo"})
            files = result["repositorySnapshot"]["files"]

        self.assertEqual(files[0]["language"], "Unknown")
        self.assertEqual(files[0]["path"], "custom.foo")


if __name__ == "__main__":
    unittest.main()
