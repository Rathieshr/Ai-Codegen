from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.command_center_hardening import CommandCenterHardeningService, build_command_center_hardening_router


class Collection:
    def __init__(self, key, values=None, failure: str = ""):
        self.key = key; self.values = list(values or []); self.failure = failure; self.calls = 0
    def list_recent(self, limit=50, **_filters):
        self.calls += 1
        if self.failure: raise RuntimeError(self.failure)
        return {self.key: list(reversed(self.values[-limit:])), "count": len(self.values)}


class SDK:
    def analyze(self): pass
    def execute(self): pass


class Platform:
    def __init__(self, root: Path, *, jobs=None, events=None, notification_failure=""):
        self.storage_root = root
        self.jobs = Collection("jobs", jobs)
        self.events = Collection("events", events)
        self.notifications = Collection("notifications", failure=notification_failure)
        self.activity = Collection("activity")
        self.audit = Collection("events")
        self.agent_runs = Collection("runs")
        root.mkdir(parents=True, exist_ok=True); (root / "platform.json").write_text("{}")
    def platform_health(self):
        return {"eventBusStatus": "healthy", "jobQueueStatus": "healthy", "contextOrchestratorStatus": "not_registered"}


class CommandCenterHardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        jobs = [{"jobId": f"job-{index}", "jobType": "RepositorySync", "status": "Queued" if index < 300 else "Completed", "createdAt": "2026-07-14T10:00:00Z"} for index in range(1000)]
        events = [{"eventId": f"event-{index}", "eventType": "ExecutionCompleted", "createdAt": "2026-07-14T10:00:00Z"} for index in range(700)]
        self.platform = Platform(root, jobs=jobs, events=events)
        self.service = CommandCenterHardeningService(platform=self.platform, sdk=SDK(), cache_ttl_seconds=30)
    def tearDown(self): self.temp.cleanup()

    def test_large_project_snapshot_is_bounded_and_reports_queues(self):
        value = self.service.snapshot(force=True, include_diagnostics=True)
        self.assertEqual(1000, value["jobs"]["total"])
        self.assertEqual(300, value["queues"]["depth"])
        self.assertEqual(700, value["events"]["total"])
        self.assertLessEqual(len(value["jobs"]["recent"]), 20)
        self.assertLessEqual(len(value["events"]["recent"]), 20)

    def test_cache_avoids_repeated_platform_reads(self):
        first = self.service.snapshot(force=True)
        calls = self.platform.jobs.calls
        second = self.service.snapshot()
        self.assertEqual("Miss", first["cache"]["status"])
        self.assertEqual("Hit", second["cache"]["status"])
        self.assertEqual(calls, self.platform.jobs.calls)

    def test_latency_storage_database_memory_sdk_and_version_are_visible(self):
        value = self.service.snapshot(force=True)
        self.assertEqual("7.10", value["version"])
        self.assertIn("snapshotLatencyMs", value["performance"])
        self.assertEqual("JSON Document Store", value["database"]["type"])
        self.assertTrue(value["storage"]["writable"])
        self.assertGreaterEqual(value["memory"]["processMegabytes"], 0)
        self.assertEqual("Ready", value["sdk"]["status"])

    def test_failed_service_degrades_without_breaking_snapshot(self):
        platform = Platform(Path(self.temp.name) / "degraded", notification_failure="notification store unavailable")
        value = CommandCenterHardeningService(platform=platform).snapshot(force=True, include_diagnostics=True)
        self.assertEqual("Degraded", value["status"])
        self.assertEqual("notification store unavailable", value["diagnostics"]["warnings"][0]["message"])

    def test_healthy_context_source_map_does_not_degrade_platform(self):
        self.platform.platform_health = lambda: {
            "eventBusStatus": "healthy",
            "jobQueueStatus": "healthy",
            "contextOrchestratorStatus": "healthy",
            "contextSourceStatus": {
                "Planning": "healthy",
                "Repository": "healthy",
                "KnowledgeRegistry": "healthy",
            },
        }
        value = self.service.snapshot(force=True, include_diagnostics=True)
        context_source = next(item for item in value["services"] if item["name"] == "Context Source")
        self.assertEqual("Healthy", context_source["status"])
        self.assertEqual("Healthy", value["status"])

    def test_diagnostics_are_admin_only_and_health_is_safe_for_viewers(self):
        app = FastAPI(); app.include_router(build_command_center_hardening_router(self.service)); client = TestClient(app)
        self.assertEqual(200, client.get("/command-center/health").status_code)
        forbidden = client.get("/command-center/diagnostics")
        self.assertEqual(403, forbidden.status_code)
        self.assertEqual("diagnostics_forbidden", forbidden.json()["error"]["code"])
        self.assertEqual(200, client.get("/command-center/diagnostics", headers={"X-HEI-Role": "admin"}).status_code)

    def test_health_endpoint_meets_interactive_performance_baseline(self):
        started = time.perf_counter()
        for _ in range(50): self.service.snapshot()
        self.assertLess(time.perf_counter() - started, 0.5)

    def test_ui_supports_accessibility_offline_background_refresh_and_virtualization(self):
        root = Path(__file__).resolve().parents[1] / "azure-devops-extension/src"
        health = (root / "commandCenterHealth.tsx").read_text()
        activity = (root / "activityCenter.tsx").read_text()
        shell = (root / "engineeringCommandCenterShell.tsx").read_text()
        host = (root / "projectIntelligenceTab.tsx").read_text()
        for marker in ('aria-label="Command Center Health"', 'aria-live="polite"', "visibilitychange", "navigator.onLine", "setInterval"):
            self.assertIn(marker, health)
        self.assertIn("visibleCount", activity)
        self.assertIn("Load More Activity", activity)
        self.assertIn("window.addEventListener('keydown'", shell)
        self.assertIn('aria-label="HEI workspace navigation"', shell)
        self.assertIn("React.lazy(() => import('./commandCenterHealth')", host)
        self.assertIn("React.lazy(() => import('./activityCenter')", host)


if __name__ == "__main__": unittest.main()
