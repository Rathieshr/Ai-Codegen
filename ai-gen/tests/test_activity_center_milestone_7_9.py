from __future__ import annotations

import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.activity_center import ActivityCenterService, build_activity_center_router


class Collection:
    def __init__(self, key, values=None):
        self.key = key
        self.values = list(values or [])

    def list_recent(self, limit=50, **_filters):
        return {self.key: list(reversed(self.values[-limit:])), "count": len(self.values)}


class Platform:
    def __init__(self, *, activity=None, events=None, audit=None, notifications=None):
        self.activity = Collection("activity", activity)
        self.events = Collection("events", events)
        self.audit = Collection("events", audit)
        self.notifications = Collection("notifications", notifications)


class Traces:
    def __init__(self, values=None): self.values = values or []
    def list_traces(self): return {"traces": self.values, "count": len(self.values)}


class Runtime:
    def __init__(self, values=None): self.values = values or []
    def list(self, limit=100): return {"traces": self.values[:limit], "count": len(self.values)}


def event(index: int, event_type="PlanningPackApproved", correlation="corr-1"):
    return {
        "eventId": f"event-{index}", "eventType": event_type, "source": "API",
        "correlationId": correlation, "createdAt": f"2026-07-14T10:{index // 60:02d}:{index % 60:02d}Z",
        "payload": {"artifactType": "Story", "artifactId": str(index)},
    }


class ActivityCenterTests(unittest.TestCase):
    def test_large_history_is_chronological_paginated_and_bounded(self):
        service = ActivityCenterService(platform=Platform(events=[event(index, correlation=f"corr-{index}") for index in range(600)]))
        page = service.list(offset=100, limit=100)
        self.assertEqual(600, page["total"])
        self.assertEqual(100, page["count"])
        self.assertTrue(page["hasMore"])
        self.assertGreater(page["activity"][0]["occurredAt"], page["activity"][-1]["occurredAt"])
        self.assertEqual(250, service.list(limit=999)["limit"])

    def test_search_category_and_status_filters(self):
        events = [
            event(1, "RepositoryScanCompleted"),
            event(2, "PlanningPackApproved"),
            event(3, "ExecutionFailed"),
            event(4, "AzureDevOpsSyncCompleted"),
        ]
        service = ActivityCenterService(platform=Platform(events=events))
        self.assertEqual(1, service.list(category="Repository Sync")["total"])
        self.assertEqual("Approvals", service.list(search="Planning Pack Approved")["activity"][0]["category"])
        self.assertEqual(1, service.list(status="Failed")["total"])
        self.assertEqual("ADO", service.list(search="Azure Dev Ops Sync")["activity"][0]["category"])

    def test_correlation_trace_combines_sources_in_time_order(self):
        platform = Platform(
            activity=[{"activityId": "a1", "title": "Story planning", "correlationId": "corr-x", "createdAt": "2026-07-14T10:00:00Z"}],
            events=[{"eventId": "e1", "eventType": "ExecutionStarted", "correlationId": "corr-x", "createdAt": "2026-07-14T10:01:00Z"}],
            notifications=[{"notificationId": "n1", "title": "QA complete", "correlationId": "corr-x", "createdAt": "2026-07-14T10:03:00Z"}],
        )
        runtime = Runtime([{"traceId": "rt1", "correlationId": "corr-x", "timeline": [{"stage": "Validation", "status": "Complete", "completedAt": "2026-07-14T10:02:00Z"}], "metrics": {}}])
        trace = ActivityCenterService(platform=platform, runtime_observability=runtime).correlation("corr-x")
        self.assertEqual(4, trace["count"])
        self.assertEqual(sorted(item["occurredAt"] for item in trace["activity"]), [item["occurredAt"] for item in trace["activity"]])
        self.assertIn("Validation", trace["stages"])
        self.assertTrue(any(item["sourceType"] == "RuntimeTrace" for item in trace["activity"]))

    def test_replay_is_view_only_and_redacts_sensitive_details(self):
        platform = Platform(events=[{**event(1), "payload": {"accessToken": "secret", "message": "Prepared"}}])
        service = ActivityCenterService(platform=platform)
        item = service.list()["activity"][0]
        replay = service.replay(item["activityId"])
        self.assertTrue(replay["replayed"])
        self.assertFalse(replay["sideEffects"])
        self.assertEqual("ViewOnly", replay["replayMode"])
        self.assertEqual("[redacted]", replay["activity"]["details"]["payload"]["accessToken"])

    def test_api_supports_list_detail_correlation_and_replay(self):
        service = ActivityCenterService(platform=Platform(events=[event(1)]))
        app = FastAPI(); app.include_router(build_activity_center_router(service))
        client = TestClient(app)
        listed = client.get("/activity").json()
        activity_id = listed["activity"][0]["activityId"]
        self.assertEqual(200, client.get(f"/activity/{activity_id}").status_code)
        self.assertEqual(200, client.get("/activity/correlation/corr-1").status_code)
        replay = client.post(f"/activity/{activity_id}/replay")
        self.assertEqual(200, replay.status_code)
        self.assertFalse(replay.json()["sideEffects"])
        self.assertEqual(404, client.get("/activity/missing").status_code)

    def test_ui_exposes_activity_operations_and_view_only_replay(self):
        source = (Path(__file__).resolve().parents[1] / "azure-devops-extension/src/activityCenter.tsx").read_text()
        for label in ("Search", "Open Details", "Correlation Trace", "Replay View", "View-only replay"):
            self.assertIn(label, source)


if __name__ == "__main__":
    unittest.main()
