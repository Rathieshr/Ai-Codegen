import tempfile
import unittest
import subprocess
from pathlib import Path

from backend.repository_intelligence import register_repository_intelligence
from backend.repository_intelligence.api.router import build_repository_router


class RepositoryIntelligenceFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = tempfile.TemporaryDirectory()
        self.module = register_repository_intelligence(Path(self.temp_dir.name))
        self._seed_repository_files(Path(self.repo_dir.name))
        self._initialize_git_repository(Path(self.repo_dir.name))

    def tearDown(self) -> None:
        self.repo_dir.cleanup()
        self.temp_dir.cleanup()

    def test_create_and_get_repository(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "LineDefender",
                "url": "https://dev.azure.com/rathiesh91/LineDefender",
                "defaultBranch": "main",
                "repositoryType": "AzureDevOps",
                "authenticationType": "PAT",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )

        fetched = self.module.application.get_repository(created["repositoryId"])

        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["name"], "LineDefender")
        self.assertEqual(fetched["graphStatus"], "NotConnected")
        self.assertEqual(fetched["repositoryType"], "AzureDevOps")
        self.assertEqual(fetched["authenticationType"], "PAT")
        self.assertEqual(fetched["status"], "PendingScan")

    def test_list_repositories_returns_count(self) -> None:
        self.module.application.create_repository(
            {
                "name": "Repo One",
                "url": "https://github.com/org/repo-one",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.create_repository(
            {
                "name": "Repo Two",
                "url": "https://github.com/org/repo-two",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )

        result = self.module.application.list_repositories()

        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["repositories"]), 2)

    def test_status_is_placeholder_without_scanning(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "GridHub",
                "url": "https://github.com/org/gridhub",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )

        status = self.module.application.get_repository_status(created["repositoryId"])

        self.assertEqual(status["status"], "PendingScan")
        self.assertEqual(status["scanStatus"], "PendingScan")
        self.assertEqual(status["snapshotStatus"], "NotAvailable")
        self.assertEqual(status["graphStatus"], "NotConnected")
        self.assertIn("Scanning is not implemented yet", status["message"])

    def test_duplicate_repository_url_is_rejected(self) -> None:
        self.module.application.create_repository(
            {
                "name": "Repo One",
                "url": "https://github.com/org/duplicate",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )

        with self.assertRaises(ValueError):
            self.module.application.create_repository(
                {
                    "name": "Repo Two",
                    "url": "https://github.com/org/duplicate/",
                    "repositoryType": "GitHub",
                    "metadata": {"localPath": self.repo_dir.name},
                }
            )

    def test_invalid_repository_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.module.application.create_repository(
                {"name": "Repo One", "url": "not-a-url", "repositoryType": "GitHub"}
            )

    def test_azure_devops_clone_url_with_organization_user_info_is_valid(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "LineDefender",
                "url": "https://rathiesh91@dev.azure.com/rathiesh91/LineDefender/_git/LineDefender",
                "repositoryType": "AzureDevOps",
                "authenticationType": "PAT",
            }
        )

        self.assertEqual("AzureDevOps", created["repositoryType"])
        self.assertEqual("PendingScan", created["status"])

    def test_azure_devops_remote_scan_creates_metadata_snapshot_without_local_path(self) -> None:
        self.module.scanner._remote_item_provider = lambda repository: [
            {"path": "/src", "isFolder": True, "gitObjectType": "tree", "objectId": "tree-1"},
            {"path": "/src/DeviceHealthService.ts", "isFolder": False, "gitObjectType": "blob", "objectId": "blob-1", "contentMetadata": {"fileLength": 128}},
            {"path": "/src/DeviceHealthController.ts", "isFolder": False, "gitObjectType": "blob", "objectId": "blob-3", "contentMetadata": {"fileLength": 196}},
            {"path": "/src/DeviceHealthController.test.ts", "isFolder": False, "gitObjectType": "blob", "objectId": "blob-4", "contentMetadata": {"fileLength": 96}},
            {"path": "/README.md", "isFolder": False, "gitObjectType": "blob", "objectId": "blob-2", "contentMetadata": {"fileLength": 64}},
        ]
        remote_content = {
            "src/DeviceHealthService.ts": "export class DeviceHealthService { getHealth() { return []; } }",
            "src/DeviceHealthController.ts": 'router.get("/device-health", () => []); export class DeviceHealthController { constructor(private service: DeviceHealthService) {} }',
            "src/DeviceHealthController.test.ts": "describe('DeviceHealthController', () => { it('returns health', () => {}); });",
            "README.md": "# GridHub",
        }
        self.module.parser_service._remote_content_provider = lambda repository, path: remote_content[path]
        created = self.module.application.create_repository(
            {
                "name": "GridHub",
                "url": "https://dev.azure.com/hubbell/GridHub/_git/GridHub",
                "defaultBranch": "main",
                "repositoryType": "AzureDevOps",
                "authenticationType": "PAT",
                "metadata": {"azureDevOpsRepositoryId": "ado-repo-1", "adoProject": "GridHub", "branch": "main"},
            }
        )

        result = self.module.application.scan_repository(created["repositoryId"], mode="Full")

        self.assertEqual("Completed", result["scan"]["status"])
        self.assertEqual(4, result["snapshot"]["totalFiles"])
        self.assertEqual("main", result["snapshot"]["branch"])
        self.assertEqual(["src"], result["snapshot"]["modules"])
        self.assertEqual(["src"], result["snapshot"]["metadata"]["sourceRoots"])
        self.assertEqual(["README.md"], result["snapshot"]["metadata"]["rootFiles"])
        self.assertEqual("blob-1", result["snapshot"]["metadata"]["filesByPath"]["src/DeviceHealthService.ts"]["contentHash"])
        self.assertGreater(result["parsedSymbolCount"], 0)

        health = self.module.application.get_repository_health(created["repositoryId"])
        self.assertEqual(["src"], health["sourceRoots"])
        self.assertIn("src/DeviceHealthController.ts", health["files"])
        self.assertGreater(health["symbolsIndexed"], 0)
        self.assertTrue(any(item["name"] == "DeviceHealthService" for item in health["services"]))
        self.assertTrue(any(item["name"] == "/device-health" for item in health["apis"]))

        self.module.parser_service._store.write([])
        refreshed = self.module.application.scan_repository(created["repositoryId"], mode="Incremental")
        self.assertGreater(refreshed["parsedSymbolCount"], 0)

    def test_update_and_delete_repository(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "Repo One",
                "url": "https://github.com/org/repo-one",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )

        updated = self.module.application.update_repository(
            created["repositoryId"],
            {
                "name": "Repo One Updated",
                "url": "https://github.com/org/repo-one-updated",
                "repositoryType": "GitHub",
                "authenticationType": "OAuth",
                "status": "PendingScan",
                "metadata": {"localPath": self.repo_dir.name},
            },
        )
        deleted = self.module.application.delete_repository(created["repositoryId"])

        self.assertIsNotNone(updated)
        self.assertEqual(updated["name"], "Repo One Updated")
        self.assertEqual(updated["authenticationType"], "OAuth")
        self.assertTrue(deleted)
        self.assertIsNone(self.module.application.get_repository(created["repositoryId"]))

    def test_full_scan_captures_structure(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "Scanner Repo",
                "url": "https://github.com/org/scanner",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name, "commitId": "abc123"},
            }
        )

        result = self.module.application.scan_repository(created["repositoryId"], mode="Full")

        self.assertEqual(result["scan"]["status"], "Completed")
        self.assertEqual(result["snapshot"]["scanMode"], "Full")
        self.assertEqual(result["snapshot"]["branch"], "main")
        self.assertEqual(result["snapshot"]["commitId"], "abc123")
        self.assertEqual(result["snapshot"]["status"], "Completed")
        self.assertEqual(result["snapshot"]["totalFiles"], 3)
        self.assertEqual(result["snapshot"]["metadata"]["totalFiles"], 3)
        self.assertIn("src", result["snapshot"]["modules"])
        self.assertIn("src", result["snapshot"]["metadata"]["folders"])
        self.assertIn("py", result["snapshot"]["metadata"]["extensions"])
        self.assertIn("Python", result["snapshot"]["metadata"]["languages"])

    def test_incremental_scan_reports_changes(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "Scanner Repo",
                "url": "https://github.com/org/scanner-incremental",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.scan_repository(created["repositoryId"], mode="Full")
        Path(self.repo_dir.name, "src", "main.py").write_text("print('updated')\n", encoding="utf-8")
        Path(self.repo_dir.name, "src", "added.py").write_text("print('added')\n", encoding="utf-8")
        Path(self.repo_dir.name, "src", "index.ts").unlink()
        subprocess.run(
            ["git", "-C", self.repo_dir.name, "mv", "docs/readme.md", "docs/guide.md"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "-C", self.repo_dir.name, "add", "-A"],
            check=True,
            capture_output=True,
            text=True,
        )

        result = self.module.application.scan_repository(created["repositoryId"], mode="Incremental")
        diff = result["snapshot"]["metadata"]["diff"]

        self.assertEqual(result["scan"]["status"], "Completed")
        self.assertEqual(result["snapshot"]["metadata"]["changedFileCount"], 4)
        self.assertEqual(result["scan"]["metadata"]["changedFileCount"], 4)
        self.assertIn("src/added.py", diff["added"])
        self.assertIn("src/main.py", diff["changed"])
        self.assertIn("src/index.ts", diff["deleted"])
        self.assertIn(["docs/readme.md", "docs/guide.md"], diff["renamed"])
        self.assertEqual(result["snapshot"]["totalFiles"], 3)

    def test_incremental_scan_api_endpoint_uses_git_diff(self) -> None:
        router = build_repository_router(self.module)
        endpoint = next(
            route.endpoint
            for route in router.routes
            if getattr(route, "path", "") == "/repositories/{repository_id}/incremental-scan"
        )

        created = self.module.application.create_repository(
            {
                "name": "Scanner Repo API",
                "url": "https://github.com/org/scanner-incremental-api",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.scan_repository(created["repositoryId"], mode="Full")
        Path(self.repo_dir.name, "src", "main.py").write_text("print('api update')\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", self.repo_dir.name, "add", "src/main.py"],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = endpoint(created["repositoryId"])

        self.assertEqual(payload["scan"]["status"], "Completed")
        self.assertEqual(payload["snapshot"]["scanMode"], "Incremental")
        self.assertIn("src/main.py", payload["snapshot"]["metadata"]["diff"]["changed"])

    def test_current_snapshot_and_history_are_available(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "Snapshot Repo",
                "url": "https://github.com/org/snapshot-repo",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name, "commitId": "commit-001"},
            }
        )

        first = self.module.application.scan_repository(created["repositoryId"], mode="Full")
        Path(self.repo_dir.name, "src", "feature.ts").write_text("export const feature = 1;\n", encoding="utf-8")
        self.module.application.update_repository(
            created["repositoryId"],
            {
                "name": "Snapshot Repo",
                "url": "https://github.com/org/snapshot-repo",
                "repositoryType": "GitHub",
                "authenticationType": "None",
                "status": "PendingScan",
                "metadata": {"localPath": self.repo_dir.name, "commitId": "commit-002", "branch": "release/demo"},
            },
        )
        second = self.module.application.scan_repository(created["repositoryId"], mode="Incremental")

        current = self.module.application.get_current_snapshot(created["repositoryId"])
        history = self.module.application.list_snapshot_history(created["repositoryId"])

        self.assertIsNotNone(current)
        self.assertEqual(current["snapshotId"], second["snapshot"]["snapshotId"])
        self.assertEqual(current["branch"], "release/demo")
        self.assertEqual(history["count"], 2)
        self.assertEqual(history["currentSnapshotId"], second["snapshot"]["snapshotId"])
        self.assertEqual(history["snapshots"][0]["snapshotId"], first["snapshot"]["snapshotId"])
        self.assertEqual(history["snapshots"][1]["snapshotId"], second["snapshot"]["snapshotId"])

    def test_scan_initializes_engineering_graph_foundation(self) -> None:
        Path(self.repo_dir.name, "src", "DeviceRepository.cs").write_text(
            "namespace Demo.Data;\npublic class DeviceRepository { }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "DeviceService.cs").write_text(
            "using Demo.Data;\nnamespace Demo.Services;\npublic class DeviceService { private readonly DeviceRepository _repository; }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "DeviceController.cs").write_text(
            'using Demo.Services;\nusing Demo.Contracts;\nnamespace Demo.Api;\n[Route("api/device")]\npublic class DeviceController { private readonly DeviceService _service; public DeviceDto GetDevice() { return new DeviceDto(); } }\n',
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "DeviceControllerTests.cs").write_text(
            "using Demo.Services;\npublic class DeviceControllerTests { private readonly DeviceService _service; }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "DeviceDto.cs").write_text(
            "namespace Demo.Contracts;\npublic class DeviceDto { public string Id { get; set; } = string.Empty; }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "DevicePage.xaml").write_text(
            '<ContentPage x:Class="Demo.DevicePage"><Button Command="{Binding Load}" /></ContentPage>\n<!-- api/device -->\n',
            encoding="utf-8",
        )
        created = self.module.application.create_repository(
            {
                "name": "Graph Repo",
                "url": "https://github.com/org/graph-repo",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )

        self.module.application.scan_repository(created["repositoryId"], mode="Full")
        fetched = self.module.application.get_repository(created["repositoryId"])
        graph = self.module.application.get_graph(created["repositoryId"])

        self.assertEqual(fetched["graphStatus"], "Available")
        self.assertIsNotNone(graph)
        self.assertGreater(len(graph["relationships"]), 0)
        node_types = {node["nodeType"] for node in graph["nodes"]}
        self.assertIn("Repository", node_types)
        self.assertIn("Module", node_types)
        self.assertIn("File", node_types)
        self.assertIn("Controller", node_types)
        self.assertIn("Service", node_types)
        self.assertIn("API", node_types)
        self.assertIn("UI", node_types)
        relationship_pairs = {
            (item["relationshipType"], item["fromNodeId"], item["toNodeId"]) for item in graph["relationships"]
        }
        self.assertTrue(
            any(
                pair[0] == "depends_on"
                and "DeviceController" in pair[1]
                and "DeviceService" in pair[2]
                for pair in relationship_pairs
            )
        )
        self.assertTrue(
            any(
                pair[0] == "depends_on"
                and "DeviceService" in pair[1]
                and "DeviceRepository" in pair[2]
                for pair in relationship_pairs
            )
        )
        self.assertTrue(
            any(
                pair[0] == "tests"
                and "DeviceControllerTests" in pair[1]
                and "DeviceService" in pair[2]
                for pair in relationship_pairs
            )
        )
        self.assertTrue(
            any(
                pair[0] == "references"
                and "DeviceDto" in pair[1]
                and "api/device" in pair[2]
                for pair in relationship_pairs
            )
            or any(
                pair[0] == "references"
                and "DeviceDto" in pair[1]
                and "DeviceController" in pair[2]
                for pair in relationship_pairs
            )
        )

    def test_query_graph_nodes_filters_by_type_and_search(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "Graph Query Repo",
                "url": "https://github.com/org/graph-query-repo",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )

        self.module.application.scan_repository(created["repositoryId"], mode="Full")
        query = self.module.application.query_graph_nodes(
            created["repositoryId"],
            node_type="Module",
            search="src",
        )

        self.assertEqual(query["count"], 1)
        self.assertEqual(query["nodes"][0]["nodeType"], "Module")
        self.assertEqual(query["nodes"][0]["name"], "src")

    def test_query_graph_relationships_filters_by_type(self) -> None:
        Path(self.repo_dir.name, "src", "UserRepository.cs").write_text(
            "public class UserRepository { }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "UserService.cs").write_text(
            "public class UserService { private readonly UserRepository _repository; }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "UserController.cs").write_text(
            "public class UserController { private readonly UserService _service; }\n",
            encoding="utf-8",
        )
        created = self.module.application.create_repository(
            {
                "name": "Graph Relationship Repo",
                "url": "https://github.com/org/graph-relationship-repo",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.scan_repository(created["repositoryId"], mode="Full")

        payload = self.module.application.query_graph_relationships(
            created["repositoryId"],
            relationship_type="depends_on",
        )

        self.assertGreaterEqual(payload["count"], 2)
        self.assertTrue(
            any("UserController" in item["fromNodeId"] and "UserService" in item["toNodeId"] for item in payload["relationships"])
        )

    def test_incremental_scan_refreshes_graph_relationships(self) -> None:
        Path(self.repo_dir.name, "src", "AlertRepository.cs").write_text(
            "public class AlertRepository { }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "AlertService.cs").write_text(
            "public class AlertService { private readonly AlertRepository _repository; }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "AlertController.cs").write_text(
            "public class AlertController { private readonly AlertService _service; }\n",
            encoding="utf-8",
        )
        created = self.module.application.create_repository(
            {
                "name": "Graph Incremental Repo",
                "url": "https://github.com/org/graph-incremental-repo",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.scan_repository(created["repositoryId"], mode="Full")
        original = self.module.application.query_graph_relationships(
            created["repositoryId"],
            relationship_type="depends_on",
            search="AlertController",
        )
        Path(self.repo_dir.name, "src", "AlertController.cs").write_text(
            "public class AlertController { }\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "-C", self.repo_dir.name, "add", "src/AlertController.cs"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.module.application.scan_repository(created["repositoryId"], mode="Incremental")
        refreshed = self.module.application.query_graph_relationships(
            created["repositoryId"],
            relationship_type="depends_on",
            search="AlertController",
        )

        self.assertGreater(original["count"], 0)
        self.assertEqual(refreshed["count"], 0)

    def test_compare_snapshots_returns_metadata_only_differences(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "Compare Repo",
                "url": "https://github.com/org/compare-repo",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name, "commitId": "commit-a", "branch": "main"},
            }
        )

        first = self.module.application.scan_repository(created["repositoryId"], mode="Full")
        Path(self.repo_dir.name, "mobile").mkdir(parents=True, exist_ok=True)
        Path(self.repo_dir.name, "mobile", "app.kt").write_text("fun main() = Unit\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", self.repo_dir.name, "add", "mobile/app.kt"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.module.application.update_repository(
            created["repositoryId"],
            {
                "name": "Compare Repo",
                "url": "https://github.com/org/compare-repo",
                "repositoryType": "GitHub",
                "authenticationType": "None",
                "status": "PendingScan",
                "metadata": {"localPath": self.repo_dir.name, "commitId": "commit-b", "branch": "feature/mobile"},
            },
        )
        second = self.module.application.scan_repository(created["repositoryId"], mode="Incremental")

        comparison = self.module.application.compare_snapshots(
            created["repositoryId"],
            first["snapshot"]["snapshotId"],
            second["snapshot"]["snapshotId"],
        )

        self.assertTrue(comparison["comparison"]["branchChanged"])
        self.assertTrue(comparison["comparison"]["commitChanged"])
        self.assertEqual(comparison["comparison"]["totalFilesDelta"], 1)
        self.assertEqual(comparison["comparison"]["languageDelta"]["Kotlin"], 1)
        self.assertIn("mobile", comparison["comparison"]["modulesAdded"])
        self.assertEqual(comparison["comparison"]["modulesRemoved"], [])

    def test_manual_scan_limits_to_selected_paths(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "Scanner Repo",
                "url": "https://github.com/org/scanner-manual",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )

        result = self.module.application.scan_repository(
            created["repositoryId"],
            mode="Manual",
            manual_paths=["docs"],
        )

        self.assertEqual(result["scan"]["status"], "Completed")
        self.assertEqual(result["snapshot"]["metadata"]["totalFiles"], 1)
        files = result["snapshot"]["metadata"]["files"]
        self.assertEqual(files[0]["path"], "docs/readme.md")

    def test_graph_query_api_endpoint_returns_module_nodes(self) -> None:
        router = build_repository_router(self.module)
        endpoint = next(
            route.endpoint
            for route in router.routes
            if getattr(route, "path", "") == "/repositories/{repository_id}/graph/nodes"
        )
        created = self.module.application.create_repository(
            {
                "name": "Graph API Repo",
                "url": "https://github.com/org/graph-api-repo",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.scan_repository(created["repositoryId"], mode="Full")

        payload = endpoint(created["repositoryId"], nodeType="Module", search="")

        self.assertEqual(payload["count"], 2)
        self.assertEqual({item["name"] for item in payload["nodes"]}, {"docs", "src"})

    def test_graph_relationship_query_api_endpoint_returns_relationships(self) -> None:
        Path(self.repo_dir.name, "src", "ReportRepository.cs").write_text(
            "public class ReportRepository { }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "ReportService.cs").write_text(
            "public class ReportService { private readonly ReportRepository _repository; }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "ReportController.cs").write_text(
            "public class ReportController { private readonly ReportService _service; }\n",
            encoding="utf-8",
        )
        router = build_repository_router(self.module)
        endpoint = next(
            route.endpoint
            for route in router.routes
            if getattr(route, "path", "") == "/repositories/{repository_id}/graph/relationships"
        )
        created = self.module.application.create_repository(
            {
                "name": "Graph Relationship API Repo",
                "url": "https://github.com/org/graph-relationship-api-repo",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.scan_repository(created["repositoryId"], mode="Full")

        payload = endpoint(created["repositoryId"], relationshipType="depends_on", fromNodeId="", toNodeId="", search="ReportController")

        self.assertGreaterEqual(payload["count"], 1)
        self.assertTrue(any("ReportController" in item["fromNodeId"] for item in payload["relationships"]))

    def test_rank_repository_files_returns_top_relevant_files(self) -> None:
        Path(self.repo_dir.name, "src", "DeviceRepository.cs").write_text(
            "public class DeviceRepository { }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "DeviceHealthService.cs").write_text(
            "public class DeviceHealthService { private readonly DeviceRepository _repository; }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "DeviceHealthController.cs").write_text(
            'public class DeviceHealthController { private readonly DeviceHealthService _service; [Route("api/device-health")] public string GetHealth() => "ok"; }\n',
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "DeviceHealthPage.xaml").write_text(
            '<ContentPage x:Class="Demo.DeviceHealthPage"><Label Text="api/device-health" /></ContentPage>\n',
            encoding="utf-8",
        )
        created = self.module.application.create_repository(
            {
                "name": "Ranking Repo",
                "url": "https://github.com/org/ranking-repo",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.scan_repository(created["repositoryId"], mode="Full")

        result = self.module.application.rank_repository_files(
            created["repositoryId"],
            artifact_type="Story",
            title="View Device Health Overview",
            description="Show offline device status and device health details in the operations view.",
            acceptance_criteria=["User can view device health details", "Offline device status is shown"],
            selected_modules=["src"],
            limit=5,
        )

        self.assertGreaterEqual(result["count"], 3)
        files = [item["file"] for item in result["files"]]
        self.assertIn("src/DeviceHealthController.cs", files)
        self.assertIn("src/DeviceHealthService.cs", files)
        self.assertIn("src/DeviceHealthPage.xaml", files)
        top_reasons = " ".join(item["reason"] for item in result["files"][:3]).lower()
        self.assertIn("matched", top_reasons)

    def test_rank_repository_files_uses_engineering_memory(self) -> None:
        Path(self.repo_dir.name, "src", "HealthTrendAnalyticsService.cs").write_text(
            "public class HealthTrendAnalyticsService { }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "HealthTrendController.cs").write_text(
            "public class HealthTrendController { private readonly HealthTrendAnalyticsService _service; }\n",
            encoding="utf-8",
        )
        created = self.module.application.create_repository(
            {
                "name": "Memory Ranking Repo",
                "url": "https://github.com/org/memory-ranking-repo",
                "repositoryType": "GitHub",
                "projectId": "line-defender",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.scan_repository(created["repositoryId"], mode="Full")
        self.module.memory_engine.store_memory(
            {
                "projectId": "line-defender",
                "category": "Execution Memory",
                "title": "Health Trend Analytics implementation",
                "summary": "Use the analytics service for device health trend work.",
                "artifactType": "Task",
                "artifactId": "task-1",
                "approvalStatus": "Approved",
                "confidence": 0.93,
                "repositoryEvidence": [{"path": "src/HealthTrendAnalyticsService.cs"}],
                "graphReferences": ["src/HealthTrendController.cs"],
                "index": {
                    "tokens": ["health", "trend", "analytics", "device"],
                    "repository": ["Memory Ranking Repo"],
                    "modules": ["src"],
                },
            },
            actor="tests",
        )

        result = self.module.application.rank_repository_files(
            created["repositoryId"],
            artifact_type="Task",
            title="Add device health trend analytics",
            description="Implement trend analytics for device health summaries.",
            tags=["analytics", "health"],
            limit=3,
        )

        self.assertGreaterEqual(result["count"], 1)
        self.assertEqual(result["files"][0]["file"], "src/HealthTrendAnalyticsService.cs")
        self.assertTrue(
            any(
                item["file"] == "src/HealthTrendAnalyticsService.cs"
                and (
                    "memory matched" in item["reason"].lower()
                    or "Health Trend Analytics implementation" in " ".join(item["dependencies"])
                )
                for item in result["files"]
            )
        )

    def test_file_ranking_api_endpoint_returns_ranked_files(self) -> None:
        Path(self.repo_dir.name, "src", "AlertRepository.cs").write_text(
            "public class AlertRepository { }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "AlertService.cs").write_text(
            "public class AlertService { private readonly AlertRepository _repository; }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "AlertController.cs").write_text(
            'public class AlertController { private readonly AlertService _service; [Route("api/alerts")] public string GetAlerts() => "ok"; }\n',
            encoding="utf-8",
        )
        router = build_repository_router(self.module)
        endpoint = next(
            route.endpoint
            for route in router.routes
            if getattr(route, "path", "") == "/repositories/{repository_id}/file-ranking"
        )
        created = self.module.application.create_repository(
            {
                "name": "Ranking API Repo",
                "url": "https://github.com/org/ranking-api-repo",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.scan_repository(created["repositoryId"], mode="Full")

        request = type(
            "Request",
            (),
            {
                "artifact_type": "Feature",
                "title": "Alert management",
                "description": "Support alert management in the dashboard.",
                "acceptance_criteria": ["User can view alert details"],
                "tags": ["alerts"],
                "selected_modules": ["src"],
                "selected_flows": [],
                "limit": 5,
            },
        )()
        payload = endpoint(created["repositoryId"], request)

        self.assertGreaterEqual(payload["count"], 2)
        self.assertTrue(any(item["file"] == "src/AlertController.cs" for item in payload["files"]))

    def test_build_repository_context_capsule_returns_repository_context(self) -> None:
        Path(self.repo_dir.name, "src", "DeviceRepository.cs").write_text(
            "public class DeviceRepository { }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "DeviceHealthService.cs").write_text(
            "public class DeviceHealthService { private readonly DeviceRepository _repository; }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "DeviceHealthController.cs").write_text(
            'public class DeviceHealthController { private readonly DeviceHealthService _service; [Route("api/device-health")] public string GetHealth() => "ok"; }\n',
            encoding="utf-8",
        )
        created = self.module.application.create_repository(
            {
                "name": "Capsule Repo",
                "url": "https://github.com/org/capsule-repo",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.scan_repository(created["repositoryId"], mode="Full")

        result = self.module.application.build_repository_context_capsule(
            created["repositoryId"],
            story={
                "title": "View device health overview",
                "description": "Operations users review offline device health and status details.",
                "acceptance_criteria": ["User can review device health details."],
            },
            selected_modules=["src"],
            selected_flows=["Device Health Review Flow"],
        )

        self.assertIsNotNone(result)
        capsule = result["capsule"]
        self.assertTrue(capsule["relevantFiles"])
        self.assertTrue(capsule["relevantAPIs"])
        self.assertTrue(capsule["dependencies"])
        self.assertTrue(capsule["architectureRules"])
        self.assertTrue(capsule["suggestedTests"])
        self.assertTrue(capsule["moduleContext"])
        self.assertEqual(capsule["relevantFiles"][0]["source"], "repository_intelligence")
        self.assertTrue(any(item["name"] == "DeviceHealthController" for item in capsule["relevantAPIs"]))

    def test_repository_context_capsule_api_endpoint_returns_capsule(self) -> None:
        Path(self.repo_dir.name, "src", "FaultService.cs").write_text(
            "public class FaultService { }\n",
            encoding="utf-8",
        )
        Path(self.repo_dir.name, "src", "FaultController.cs").write_text(
            'public class FaultController { private readonly FaultService _service; [Route("api/faults")] public string GetFaults() => "ok"; }\n',
            encoding="utf-8",
        )
        router = build_repository_router(self.module)
        endpoint = next(
            route.endpoint
            for route in router.routes
            if getattr(route, "path", "") == "/repositories/{repository_id}/context-capsule"
        )
        created = self.module.application.create_repository(
            {
                "name": "Capsule API Repo",
                "url": "https://github.com/org/capsule-api-repo",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.scan_repository(created["repositoryId"], mode="Full")

        request = type(
            "Request",
            (),
            {
                "story": {
                    "title": "Review fault details",
                    "description": "Operators need fault details and status visibility.",
                    "acceptance_criteria": ["Fault details are visible."],
                },
                "selected_modules": ["src"],
                "selected_flows": ["Fault Event Review Flow"],
                "limit": 5,
            },
        )()
        payload = endpoint(created["repositoryId"], request)

        self.assertTrue(payload["capsule"]["relevantFiles"])
        self.assertTrue(payload["capsule"]["relevantAPIs"])
        self.assertGreaterEqual(payload["rankingCount"], 1)

    def test_repository_parser_extracts_supported_language_symbols(self) -> None:
        (Path(self.repo_dir.name) / "api").mkdir(parents=True, exist_ok=True)
        (Path(self.repo_dir.name) / "web").mkdir(parents=True, exist_ok=True)
        (Path(self.repo_dir.name) / "app").mkdir(parents=True, exist_ok=True)
        (Path(self.repo_dir.name) / "backend").mkdir(parents=True, exist_ok=True)
        (Path(self.repo_dir.name) / "mobile").mkdir(parents=True, exist_ok=True)
        (Path(self.repo_dir.name) / "ui").mkdir(parents=True, exist_ok=True)
        (Path(self.repo_dir.name) / "config").mkdir(parents=True, exist_ok=True)

        (Path(self.repo_dir.name) / "api" / "AuthController.cs").write_text(
            'namespace Demo.Api;\nusing Microsoft.AspNetCore.Mvc;\n[Route("api/auth")]\npublic class AuthController { [HttpGet("login")] public string Login() { return "ok"; } }\n',
            encoding="utf-8",
        )
        (Path(self.repo_dir.name) / "web" / "UserService.ts").write_text(
            'import { Injectable } from "@nestjs/common";\n@Injectable()\nexport class UserService { getUsers() {} }\n',
            encoding="utf-8",
        )
        (Path(self.repo_dir.name) / "web" / "DashboardRepository.js").write_text(
            "const express = require('express');\nconst router = express.Router();\nclass DashboardRepository {}\nrouter.get('/dash', () => true);\n",
            encoding="utf-8",
        )
        (Path(self.repo_dir.name) / "app" / "MainActivity.kt").write_text(
            "package com.demo.app\nimport kotlin.collections.*\nclass MainActivity { fun loadData() {} }\n",
            encoding="utf-8",
        )
        (Path(self.repo_dir.name) / "backend" / "OrderService.java").write_text(
            "package com.demo.backend;\nimport java.util.*;\npublic class OrderService { public void processOrder() {} }\n",
            encoding="utf-8",
        )
        (Path(self.repo_dir.name) / "mobile" / "app.dart").write_text(
            "import 'package:flutter/widgets.dart';\nclass DeviceRepository { void fetchDevice() {} }\n",
            encoding="utf-8",
        )
        (Path(self.repo_dir.name) / "ui" / "MainPage.xaml").write_text(
            '<ContentPage x:Class="Demo.MainPage" xmlns="http://schemas.microsoft.com/dotnet/2021/maui"><Grid RowDefinitions="*"></Grid></ContentPage>\n',
            encoding="utf-8",
        )
        (Path(self.repo_dir.name) / "config" / "openapi.json").write_text(
            '{"route":"/health","dto":"HealthDto"}\n',
            encoding="utf-8",
        )
        (Path(self.repo_dir.name) / "config" / "app.yaml").write_text(
            "path: /status\nservice: status-check\n",
            encoding="utf-8",
        )

        created = self.module.application.create_repository(
            {
                "name": "Parser Repo",
                "url": "https://github.com/org/parser-repo",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )

        result = self.module.application.scan_repository(created["repositoryId"], mode="Full")
        symbols = self.module.application.list_symbols(created["repositoryId"])
        by_name = {item["name"]: item for item in symbols["symbols"]}

        self.assertGreater(result["parsedSymbolCount"], 0)
        self.assertIn("AuthController", by_name)
        self.assertEqual(by_name["AuthController"]["kind"], "Controller")
        self.assertIn("UserService", by_name)
        self.assertEqual(by_name["UserService"]["kind"], "Service")
        self.assertIn("/dash", by_name)
        self.assertEqual(by_name["/dash"]["kind"], "Route")
        self.assertIn("MainActivity", by_name)
        self.assertIn("OrderService", by_name)
        self.assertIn("DeviceRepository", by_name)
        self.assertEqual(by_name["DeviceRepository"]["kind"], "Repository")
        self.assertIn("Demo.MainPage", by_name)
        self.assertIn("/health", by_name)
        self.assertIn("path", by_name)

    def test_repository_symbols_api_filters_language_and_kind(self) -> None:
        Path(self.repo_dir.name, "api").mkdir(parents=True, exist_ok=True)
        Path(self.repo_dir.name, "api", "AuthController.cs").write_text(
            'namespace Demo.Api;\n[Route("api/auth")]\npublic class AuthController { public string Login() { return "ok"; } }\n',
            encoding="utf-8",
        )
        created = self.module.application.create_repository(
            {
                "name": "Parser API Repo",
                "url": "https://github.com/org/parser-api-repo",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.scan_repository(created["repositoryId"], mode="Full")

        router = build_repository_router(self.module)
        endpoint = next(
            route.endpoint
            for route in router.routes
            if getattr(route, "path", "") == "/repositories/{repository_id}/symbols"
        )
        payload = endpoint(created["repositoryId"], snapshotId="", language="C#", kind="Controller", path="", search="")

        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["symbols"][0]["name"], "AuthController")
        self.assertEqual(payload["symbols"][0]["kind"], "Controller")

    def test_scan_fails_without_valid_local_path(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "Broken Repo",
                "url": "https://github.com/org/broken",
                "repositoryType": "GitHub",
            }
        )

        result = self.module.application.scan_repository(created["repositoryId"], mode="Full")

        self.assertEqual(result["scan"]["status"], "Failed")
        self.assertIn("local path", result["scan"]["message"])

    def test_repository_registration_queues_agent_scan(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "Agent Registration Repo",
                "url": "https://github.com/org/agent-registration",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )

        status = self.module.application.get_repository_agent_status(created["repositoryId"])

        self.assertEqual(status["status"], "Queued")
        self.assertEqual(status["pendingJobs"], 1)
        self.assertEqual(status["activeJob"]["payload"]["trigger"], "RepositoryRegistration")

    def test_git_push_agent_trigger_runs_incremental_pipeline(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "Agent Git Push Repo",
                "url": "https://github.com/org/agent-git-push",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.scan_repository(created["repositoryId"], mode="Full")
        Path(self.repo_dir.name, "src", "agent_added.py").write_text("print('agent')\n", encoding="utf-8")

        job = self.module.application.trigger_repository_agent(
            created["repositoryId"],
            trigger="GitPush",
            run_immediately=True,
        )

        self.assertEqual(job["status"], "Completed")
        self.assertEqual(job["result"]["snapshot"]["scanMode"], "Incremental")
        self.assertGreater(job["result"]["graphNodeCount"], 0)

    def test_repository_agent_retries_failed_scan(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "Agent Retry Repo",
                "url": "https://github.com/org/agent-retry",
                "repositoryType": "GitHub",
            }
        )

        job = self.module.application.trigger_repository_agent(
            created["repositoryId"],
            trigger="NightlyHealthCheck",
            max_retries=2,
            run_immediately=True,
        )

        self.assertEqual(job["status"], "Queued")
        self.assertEqual(job["retryCount"], 1)
        self.assertIn("local path", job["error"])

    def test_repository_monitoring_reports_scan_snapshot_graph_and_agent(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "Agent Monitoring Repo",
                "url": "https://github.com/org/agent-monitoring",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.scan_repository(created["repositoryId"], mode="Full")

        dashboard = self.module.application.get_repository_monitoring(created["repositoryId"])

        self.assertEqual(dashboard["health"], "Healthy")
        self.assertEqual(dashboard["filesIndexed"], 3)
        self.assertGreater(dashboard["modulesIndexed"], 0)
        self.assertGreater(dashboard["graphNodesIndexed"], 0)
        self.assertEqual(dashboard["agentStatus"]["status"], "Idle")

    def test_repository_agent_notifies_subscribers_after_refresh(self) -> None:
        received = []
        self.module.agent.subscribe(received.append)
        created = self.module.application.create_repository(
            {
                "name": "Agent Subscriber Repo",
                "url": "https://github.com/org/agent-subscriber",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )

        self.module.application.scan_repository(created["repositoryId"], mode="Full")

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["eventType"], "RepositoryIntelligenceUpdated")
        self.assertEqual(received[0]["repositoryId"], created["repositoryId"])

    def test_repository_agent_and_monitoring_api_endpoints(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "Agent API Repo",
                "url": "https://github.com/org/agent-api",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        router = build_repository_router(self.module)
        status_endpoint = next(
            route.endpoint
            for route in router.routes
            if getattr(route, "path", "") == "/repositories/{repository_id}/agent/status"
        )
        monitoring_endpoint = next(
            route.endpoint
            for route in router.routes
            if getattr(route, "path", "") == "/repositories/{repository_id}/monitoring"
        )

        queued = status_endpoint(created["repositoryId"])
        self.module.application.scan_repository(created["repositoryId"], mode="Full")
        monitoring = monitoring_endpoint(created["repositoryId"])

        self.assertEqual(queued["status"], "Queued")
        self.assertEqual(monitoring["health"], "Healthy")
        self.assertEqual(monitoring["agentStatus"]["status"], "Idle")

    def test_repository_agent_queues_supported_platform_events(self) -> None:
        created = self.module.application.create_repository(
            {
                "name": "Agent Event Repo",
                "url": "https://github.com/org/agent-event",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.agent.event_bus.publish(
            {
                "eventType": "PullRequestMerged",
                "source": "API",
                "repositoryId": created["repositoryId"],
                "payload": {},
            }
        )

        jobs = self.module.application.list_repository_agent_jobs(created["repositoryId"], limit=10)

        self.assertEqual(jobs["jobs"][0]["payload"]["trigger"], "PRMerged")
        self.assertEqual(jobs["jobs"][0]["payload"]["mode"], "Incremental")

    def test_repository_monitoring_dashboard_aggregates_repositories(self) -> None:
        first = self.module.application.create_repository(
            {
                "name": "Monitoring One",
                "url": "https://github.com/org/monitoring-one",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.create_repository(
            {
                "name": "Monitoring Two",
                "url": "https://github.com/org/monitoring-two",
                "repositoryType": "GitHub",
                "metadata": {"localPath": self.repo_dir.name},
            }
        )
        self.module.application.scan_repository(first["repositoryId"], mode="Full")
        router = build_repository_router(self.module)
        endpoint = next(
            route.endpoint
            for route in router.routes
            if getattr(route, "path", "") == "/repositories/dashboard/monitoring"
        )

        dashboard = endpoint()

        self.assertEqual(dashboard["repositoryCount"], 2)
        self.assertEqual(dashboard["healthyCount"], 1)
        self.assertEqual(dashboard["pendingCount"], 1)
        self.assertEqual(dashboard["filesIndexed"], 3)
        self.assertEqual(len(dashboard["repositories"]), 2)

    def test_repository_scan_indexes_and_persists_markdown_registry(self) -> None:
        root = Path(self.repo_dir.name)
        (root / "docs" / "architecture.md").write_text(
            "# Architecture\nThe Device Service must use repository interfaces.\n",
            encoding="utf-8",
        )
        (root / "node_modules" / "package").mkdir(parents=True)
        (root / "node_modules" / "package" / "README.md").write_text(
            "# Dependency internals\nThis content must not enter HEI knowledge.\n",
            encoding="utf-8",
        )
        created = self.module.application.create_repository({
            "name": "Documentation Registry",
            "url": "https://github.com/org/documentation-registry",
            "repositoryType": "GitHub",
            "projectId": "project-docs",
            "metadata": {"localPath": self.repo_dir.name},
        })

        result = self.module.application.scan_repository(created["repositoryId"], mode="Full")
        registry = self.module.application.get_markdown_registry(created["repositoryId"])
        snapshot = result["snapshot"]

        self.assertEqual("Available", registry["status"])
        self.assertIn("docs/architecture.md", registry["sourceFiles"])
        self.assertNotIn("node_modules/package/README.md", registry["sourceFiles"])
        self.assertGreater(registry["sectionsIndexed"], 0)
        self.assertGreater(registry["statementsIndexed"], 0)
        self.assertEqual(
            registry["documentsIndexed"],
            snapshot["metadata"]["documentationRegistry"]["documentsIndexed"],
        )
        health = self.module.application.get_repository_health(created["repositoryId"])
        self.assertEqual(registry["sourceFiles"], health["documentation"]["sourceFiles"])

        documentation_endpoint = next(
            route.endpoint for route in build_repository_router(self.module).routes
            if getattr(route, "path", "") == "/repositories/{repository_id}/documentation"
        )
        self.assertEqual(
            registry["sectionsIndexed"],
            documentation_endpoint(created["repositoryId"])["sectionsIndexed"],
        )

        reloaded = register_repository_intelligence(Path(self.temp_dir.name))
        persisted = reloaded.application.get_markdown_registry(created["repositoryId"])
        self.assertEqual(registry["sourceFiles"], persisted["sourceFiles"])
        self.assertEqual(registry["sectionsIndexed"], persisted["sectionsIndexed"])

    def test_incremental_scan_replaces_stale_markdown_registry_entries(self) -> None:
        root = Path(self.repo_dir.name)
        created = self.module.application.create_repository({
            "name": "Incremental Documentation",
            "url": "https://github.com/org/incremental-documentation",
            "repositoryType": "GitHub",
            "metadata": {"localPath": self.repo_dir.name},
        })
        self.module.application.scan_repository(created["repositoryId"], mode="Full")
        self.assertIn(
            "docs/readme.md",
            self.module.application.get_markdown_registry(created["repositoryId"])["sourceFiles"],
        )

        (root / "docs" / "readme.md").unlink()
        (root / "docs" / "device-health.mdx").write_text(
            "# Device Health\nThe dashboard must display current device health.\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", "update documentation"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.module.application.scan_repository(created["repositoryId"], mode="Incremental")
        registry = self.module.application.get_markdown_registry(created["repositoryId"])

        self.assertNotIn("docs/readme.md", registry["sourceFiles"])
        self.assertIn("docs/device-health.mdx", registry["sourceFiles"])

    def _seed_repository_files(self, root: Path) -> None:
        (root / "src").mkdir(parents=True, exist_ok=True)
        (root / "docs").mkdir(parents=True, exist_ok=True)
        (root / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
        (root / "src" / "index.ts").write_text("export const app = true;\n", encoding="utf-8")
        (root / "docs" / "readme.md").write_text(
            "# Repo\nRepository guidance for the sample application.\n",
            encoding="utf-8",
        )

    def _initialize_git_repository(self, root: Path) -> None:
        commands = [
            ["git", "-C", str(root), "init", "-b", "main"],
            ["git", "-C", str(root), "config", "user.email", "hei@example.com"],
            ["git", "-C", str(root), "config", "user.name", "HEI Tests"],
            ["git", "-C", str(root), "add", "."],
            ["git", "-C", str(root), "commit", "-m", "initial snapshot"],
        ]
        for command in commands:
            subprocess.run(command, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
