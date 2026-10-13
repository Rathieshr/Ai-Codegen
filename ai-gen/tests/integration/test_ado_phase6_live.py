"""Opt-in validation against an isolated Azure DevOps test project."""

from __future__ import annotations

import json
import os
import unittest
from urllib.request import Request, urlopen


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").lower() in {"1", "true", "yes", "on"}


@unittest.skipUnless(_enabled("AI_GEN_ADO_LIVE_TESTS"), "Live Azure DevOps Phase 6 tests are opt-in.")
class AzureDevOpsPhase6LiveTests(unittest.TestCase):
    def test_isolated_project_completes_hardening_flow(self):
        backend = os.environ["AI_GEN_ADO_TEST_BACKEND_URL"].rstrip("/")
        project_id = os.environ["AI_GEN_ADO_TEST_PROJECT_ID"]
        allowed = {item.strip() for item in os.environ.get("AI_GEN_ADO_TEST_PROJECT_IDS", "").split(",") if item.strip()}
        production = {item.strip() for item in os.environ.get("AI_GEN_ADO_PRODUCTION_PROJECT_IDS", "").split(",") if item.strip()}
        self.assertIn(project_id, allowed, "Live project must be explicitly allow-listed.")
        self.assertNotIn(project_id, production, "Production projects cannot run hardening tests.")
        payload = {
            "mode": "Live",
            "projectId": project_id,
            "projectConfirmation": project_id,
            "allowWrites": _enabled("AI_GEN_ADO_TEST_WRITES"),
            "connectionId": os.environ["AI_GEN_ADO_TEST_CONNECTION_ID"],
            "repositoryId": os.environ["AI_GEN_ADO_TEST_REPOSITORY_ID"],
            "planningPackId": os.environ["AI_GEN_ADO_TEST_PLANNING_PACK_ID"],
            "epicWorkItemId": os.environ["AI_GEN_ADO_TEST_EPIC_ID"],
            "storyWorkItemId": os.environ["AI_GEN_ADO_TEST_STORY_ID"],
            "pullRequestId": os.environ["AI_GEN_ADO_TEST_PR_ID"],
            "iterationId": os.environ["AI_GEN_ADO_TEST_ITERATION_ID"],
            "staleRecommendationId": os.environ["AI_GEN_ADO_TEST_STALE_RECOMMENDATION_ID"],
            "permissionRecommendationId": os.environ["AI_GEN_ADO_TEST_PERMISSION_RECOMMENDATION_ID"],
            "outageConnectionId": os.environ["AI_GEN_ADO_TEST_OUTAGE_CONNECTION_ID"],
        }
        request = Request(f"{backend}/ado-hardening/run", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=180) as response:
            report = json.loads(response.read().decode("utf-8"))
        self.assertEqual("Command Center Ready", report["readiness"]["status"], report["readiness"]["blockers"])
        self.assertEqual(10, len(report["scenarios"]))


if __name__ == "__main__":
    unittest.main()
