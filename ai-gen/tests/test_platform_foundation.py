import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app import get_platform_health
from backend.platform.foundation import PlatformFoundation
from backend.platform.jobs import JobRunner
from backend.platform.shared import OperationSource, OperationStatus


class RecordingEventHandler:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def handle(self, event: dict) -> None:
        self.events.append(event)


class SuccessJobHandler:
    def handle(self, job: dict) -> dict:
        return {"jobId": job["jobId"], "result": "done"}


class RetryThenFailJobHandler:
    def handle(self, job: dict) -> dict:
        raise RuntimeError("retry me")


class PlatformAgent:
    def execute(self, context: dict) -> dict:
        return {"handled": True, "contextKeys": sorted(context.keys())}


class BlockingPolicy:
    def evaluate(self, profile: dict, trigger_event: dict | None, context: dict) -> dict:
        return {"success": False, "status": OperationStatus.SKIPPED.value, "message": "Blocked by policy"}


class ContextBuilder:
    def build(self, profile: dict, trigger_event: dict | None, context: dict) -> dict:
        return {
            "profile": profile,
            "triggerEvent": trigger_event or {},
            "input": context,
            "built": True,
        }


class PlatformFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.foundation = PlatformFoundation(self.root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_event_bus_publishes_and_dispatches(self) -> None:
        handler = RecordingEventHandler()
        self.foundation.event_handlers.subscribe("RepositoryRegistered", handler)

        event = self.foundation.events.publish(
            {
                "eventType": "RepositoryRegistered",
                "source": OperationSource.API.value,
                "payload": {"repository": "LineDefender"},
            }
        )

        recent = self.foundation.events.list_recent(event_type="RepositoryRegistered")
        self.assertEqual(recent["count"], 1)
        self.assertEqual(handler.events[0]["eventId"], event["eventId"])

    def test_event_handler_receives_correlation_id(self) -> None:
        handler = RecordingEventHandler()
        self.foundation.event_handlers.subscribe("WorkItemCreated", handler)

        self.foundation.events.publish(
            {
                "eventType": "WorkItemCreated",
                "correlationId": "corr-123",
                "payload": {"title": "Epic 0"},
            }
        )

        self.assertEqual(handler.events[0]["correlationId"], "corr-123")

    def test_job_queue_enqueues_and_runs_job(self) -> None:
        self.foundation.job_handlers.register("RepositoryScan", SuccessJobHandler())
        job = self.foundation.jobs.enqueue({"jobType": "RepositoryScan", "payload": {"path": "/repo"}})

        result = self.foundation.job_runner.run_next()
        stored = self.foundation.jobs.get(job["jobId"])

        self.assertTrue(result["success"])
        self.assertEqual(stored["status"], OperationStatus.COMPLETED.value)
        self.assertEqual(stored["result"]["result"], "done")

    def test_failed_job_retries(self) -> None:
        self.foundation.job_handlers.register("RetryJob", RetryThenFailJobHandler())
        job = self.foundation.jobs.enqueue({"jobType": "RetryJob", "maxRetries": 2})

        first = self.foundation.job_runner.run_next()
        stored = self.foundation.jobs.get(job["jobId"])

        self.assertFalse(first["success"])
        self.assertEqual(stored["status"], OperationStatus.QUEUED.value)
        self.assertEqual(stored["retryCount"], 1)

    def test_job_fails_after_max_retries(self) -> None:
        self.foundation.job_handlers.register("RetryJob", RetryThenFailJobHandler())
        job = self.foundation.jobs.enqueue({"jobType": "RetryJob", "maxRetries": 1})

        self.foundation.job_runner.run_next()
        second = self.foundation.job_runner.run_next()
        stored = self.foundation.jobs.get(job["jobId"])

        self.assertFalse(second["success"])
        self.assertEqual(stored["status"], OperationStatus.FAILED.value)
        self.assertEqual(stored["retryCount"], 2)

    def test_agent_runner_executes_policy_context_agent_result_pipeline(self) -> None:
        runner = self.foundation.agent_runner.__class__(
            self.foundation.agent_runs,
            event_bus=self.foundation.events,
            activity_logger=self.foundation.activity,
            context_builder=ContextBuilder(),
        )

        run = runner.run(
            PlatformAgent(),
            {"agentId": "planning-agent", "name": "Planning Agent", "enabled": True},
            trigger_event={"eventId": "evt-1", "correlationId": "corr-agent"},
            source=OperationSource.AGENT.value,
            context={"storyId": 42},
        )

        self.assertEqual(run["status"], OperationStatus.COMPLETED.value)
        self.assertEqual(run["output"]["handled"], True)
        self.assertEqual(run["correlationId"], "corr-agent")

    def test_notification_created_and_marked_read(self) -> None:
        notification = self.foundation.notifications.create(
            {
                "type": "ApprovalRequired",
                "title": "Review Story",
                "message": "Story requires approval.",
            }
        )

        updated = self.foundation.notifications.mark_read(notification["notificationId"])

        self.assertIsNotNone(updated)
        self.assertTrue(updated["readAt"])

    def test_activity_log_records_and_filters(self) -> None:
        self.foundation.activity.add_activity(
            {
                "activityType": "PlatformJobCompleted",
                "title": "Repository Scan",
                "source": OperationSource.API.value,
                "correlationId": "corr-activity",
            }
        )
        self.foundation.activity.add_activity(
            {
                "activityType": "NotificationSent",
                "title": "Review Request",
                "source": OperationSource.API.value,
                "correlationId": "corr-notify",
            }
        )

        filtered = self.foundation.activity.list_recent(activityType="PlatformJobCompleted")
        self.assertEqual(filtered["count"], 1)
        self.assertEqual(filtered["activity"][0]["correlationId"], "corr-activity")

    def test_audit_service_records_target_changes(self) -> None:
        self.foundation.audit.record(
            {
                "action": "ApproveArtifact",
                "actor": "rathiesh",
                "targetType": "Story",
                "targetId": "story-101",
                "before": {"state": "Draft"},
                "after": {"state": "Approved"},
                "correlationId": "corr-audit",
            }
        )

        events = self.foundation.audit.by_target("Story", "story-101")
        self.assertEqual(events["count"], 1)
        self.assertEqual(events["events"][0]["action"], "ApproveArtifact")

    def test_health_endpoint_returns_all_subsystem_statuses(self) -> None:
        with patch("backend.app.platform_foundation", self.foundation):
            response = get_platform_health()

        self.assertEqual(response["eventBusStatus"], "healthy")
        self.assertEqual(response["jobQueueStatus"], "healthy")
        self.assertEqual(response["agentRuntimeStatus"], "healthy")
        self.assertEqual(response["notificationStatus"], "healthy")
        self.assertEqual(response["activityLogStatus"], "healthy")
        self.assertEqual(response["auditStatus"], "healthy")


if __name__ == "__main__":
    unittest.main()
