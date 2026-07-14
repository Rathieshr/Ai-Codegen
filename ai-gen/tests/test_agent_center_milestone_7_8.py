from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.agent_center import AgentCenterError, AgentCenterService, build_agent_center_router


AGENTS = [
    {"id": "planning", "name": "Planning Agent", "responsibility": "Prepare planning work.", "featureFlag": "planningAgent"},
    {"id": "repository", "name": "Repository Agent", "responsibility": "Refresh repository intelligence.", "featureFlag": "repositoryAgent"},
    {"id": "execution", "name": "Execution Agent", "responsibility": "Prepare implementation work.", "featureFlag": "executionAgent"},
    {"id": "qa", "name": "QA Agent", "responsibility": "Prepare QA analysis.", "featureFlag": "qaAgent"},
    {"id": "memory", "name": "Memory Agent", "responsibility": "Prepare memory candidates.", "featureFlag": "memoryAgent"},
]


class Orchestrator:
    def __init__(self, workflows=None, flags=None):
        self.workflows = workflows or []
        self.flags = flags or {}
        self.retried = []

    def dashboard(self):
        groups = {"runningAgents": [], "waitingAgents": [], "completedWorkflows": [], "failedWorkflows": []}
        mapping = {"Running": "runningAgents", "WaitingApproval": "waitingAgents", "Completed": "completedWorkflows", "Failed": "failedWorkflows"}
        for item in self.workflows:
            groups[mapping[item["state"]]].append(item)
        return {"agents": AGENTS, "featureFlags": self.flags, **groups}

    def retry(self, workflow_id):
        self.retried.append(workflow_id)
        return {"workflow": {"id": workflow_id, "state": "WaitingApproval", "status": "Waiting"}}


class Collection:
    def __init__(self, key, values=None):
        self.key = key
        self.values = values or []

    def list_recent(self, limit=50, **_filters):
        name = "activity" if self.key == "activity" else self.key
        return {name: list(self.values)[:limit], "count": len(self.values)}

    def get(self, item_id):
        id_key = "jobId" if self.key == "jobs" else "runId"
        return next((item for item in self.values if item.get(id_key) == item_id), None)


class Runner:
    def __init__(self): self.retried = []
    def run_job(self, job_id):
        self.retried.append(job_id)
        return {"success": True, "status": "Completed", "metadata": {"job": {"jobId": job_id}}}


class Platform:
    def __init__(self, jobs=None, runs=None, activity=None):
        self.jobs = Collection("jobs", jobs)
        self.agent_runs = Collection("runs", runs)
        self.activity = Collection("activity", activity)
        self.job_runner = Runner()


def workflow(agent_id, state, workflow_id="workflow-1", duration=120):
    return {
        "id": workflow_id, "agentId": agent_id, "agent": f"{agent_id.title()} Agent",
        "trigger": "Manual Trigger", "state": state, "status": state,
        "currentAction": "Working", "nextAction": "Review", "durationMs": duration,
        "timeline": [{"time": "2026-07-14T10:00:00Z"}, {"time": "2026-07-14T10:00:01Z"}],
        "retryCount": 0, "errors": ["Provider timeout"] if state == "Failed" else [],
    }


class AgentCenterTests(unittest.TestCase):
    def test_idle_center_lists_every_requested_agent(self):
        result = AgentCenterService(orchestrator=Orchestrator(), platform=Platform()).list()
        names = {item["name"] for item in result["agents"]}
        self.assertTrue({"Planning Agent", "Repository Agent", "Execution Agent", "Validation Agent", "QA Agent", "Memory Agent", "ADO Agent"}.issubset(names))
        self.assertTrue(all(item["status"] == "Idle" for item in result["agents"]))

    def test_running_agent_reports_runtime_queue_health_and_duration(self):
        service = AgentCenterService(orchestrator=Orchestrator([workflow("execution", "Running")]), platform=Platform())
        agent = service.get("execution")
        self.assertEqual("Running", agent["status"])
        self.assertEqual("Healthy", agent["health"])
        self.assertEqual(120.0, agent["averageDurationMs"])
        self.assertEqual(1, agent["jobCount"])

    def test_failed_agent_is_degraded_and_failed_job_can_retry(self):
        orchestrator = Orchestrator([workflow("qa", "Failed", "failed-workflow")])
        service = AgentCenterService(orchestrator=orchestrator, platform=Platform())
        agent = service.get("qa")
        self.assertEqual("Failed", agent["status"])
        self.assertEqual(1, agent["failures"])
        result = service.retry("failed-workflow")
        self.assertEqual("Workflow", result["sourceType"])
        self.assertEqual(["failed-workflow"], orchestrator.retried)

    def test_disabled_agent_is_explicit_and_not_unhealthy(self):
        service = AgentCenterService(orchestrator=Orchestrator(flags={"repositoryAgent": False}), platform=Platform())
        agent = service.get("repository")
        self.assertFalse(agent["enabled"])
        self.assertEqual("Disabled", agent["status"])
        self.assertEqual("Disabled", agent["health"])
        self.assertIn("disabled by feature flag", agent["warnings"][0])

    def test_failed_platform_job_can_retry_but_non_failed_job_cannot(self):
        jobs = [
            {"jobId": "ado-failed", "jobType": "AzureDevOpsAgent", "status": "Failed", "createdAt": "2026-07-14T10:00:00Z", "error": "ADO timeout"},
            {"jobId": "ado-running", "jobType": "AzureDevOpsAgent", "status": "Running", "createdAt": "2026-07-14T10:01:00Z"},
        ]
        platform = Platform(jobs=jobs)
        service = AgentCenterService(orchestrator=Orchestrator(), platform=platform)
        self.assertEqual("PlatformJob", service.retry("ado-failed")["sourceType"])
        self.assertEqual(["ado-failed"], platform.job_runner.retried)
        with self.assertRaisesRegex(AgentCenterError, "Only failed"):
            service.retry("ado-running")

    def test_jobs_are_paginated_and_health_is_bounded(self):
        workflows = [workflow("planning", "Completed", f"workflow-{index}") for index in range(300)]
        service = AgentCenterService(orchestrator=Orchestrator(workflows), platform=Platform())
        page = service.jobs("planning", offset=50, limit=100)
        self.assertEqual(300, page["pagination"]["total"])
        self.assertEqual(100, page["pagination"]["returned"])
        self.assertTrue(page["pagination"]["hasMore"])
        self.assertEqual(100.0, service.health("planning")["successRate"])

    def test_api_contract_and_structured_not_found(self):
        app = FastAPI(); app.include_router(build_agent_center_router(AgentCenterService(orchestrator=Orchestrator(), platform=Platform())))
        client = TestClient(app)
        for path in ("/agents", "/agents/planning", "/agents/planning/jobs", "/agents/planning/health"):
            with self.subTest(path=path): self.assertEqual(200, client.get(path).status_code)
        missing = client.get("/agents/missing")
        self.assertEqual(404, missing.status_code)
        self.assertEqual("agent_not_found", missing.json()["error"]["code"])

    def test_ui_exposes_required_operations(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "azure-devops-extension/src/agentCenter.tsx").read_text()
        for label in ("View Details", "Retry Failed Job", "Open Activity", "View Logs"):
            self.assertIn(label, source)


if __name__ == "__main__":
    unittest.main()
