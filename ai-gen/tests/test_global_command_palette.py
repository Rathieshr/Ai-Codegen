from __future__ import annotations

import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.workspace import WorkspaceSearchService, build_workspace_router


class _Planning:
    def list(self, **_kwargs):
        return {"items": [{"id": "story-245", "type": "Story", "title": "Review Fault Service", "status": "Approved", "sourceItemId": 245}]}


class _Execution:
    def list(self, **_kwargs):
        return {"items": [{"id": "package-8", "title": "Fault Monitoring Package", "status": "Ready"}]}


class _Repositories:
    def list_repositories(self):
        return {"repositories": [{"repositoryId": "repo-1", "name": "LineDefender", "defaultBranch": "main"}]}

    def list_symbols(self, _repository_id, **_kwargs):
        return {"symbols": [{"symbolId": "symbol-1", "name": "FaultService", "kind": "Service", "path": "src/services/FaultService.cs"}]}


class _Ado:
    def work_items(self, _project_id, **_kwargs):
        return {"items": [{"workItemId": 245, "title": "Review Critical Fault", "type": "User Story", "state": "Active"}]}

    def pull_requests(self, _project_id, **_kwargs):
        return {"items": [{"pullRequestId": 17, "title": "Add fault details", "status": "Active"}]}


class _Agents:
    def list(self):
        return {"agents": [{"agentId": "repository", "name": "Repository Agent", "status": "Idle"}]}


class _Memory:
    def list_memory(self, **_kwargs):
        return {"memories": [{"id": "memory-1", "title": "Fault review pattern", "summary": "Reusable fault service flow", "category": "Planning Pattern"}]}


class _Activity:
    def list(self, **_kwargs):
        return {"activity": [{"activityId": "activity-1", "title": "Repository synchronized", "category": "Repository"}]}


class GlobalCommandPaletteTests(unittest.TestCase):
    def setUp(self):
        self.search = WorkspaceSearchService(
            planning=_Planning(), execution=_Execution(), repositories=_Repositories(), ado=_Ado(),
            agents=_Agents(), memory=_Memory(), activity=_Activity(),
        )

    def test_search_projects_engineering_categories_and_fuzzy_matches(self):
        result = self.search.search("flt svc", "project-1")
        self.assertTrue(result["results"])
        categories = {item["category"] for item in self.search.search("fault", "project-1", 100)["results"]}
        self.assertTrue({"Stories", "Execution Packages", "Services", "Files", "Azure DevOps Work Items", "Pull Requests", "Memory"} <= categories)

    def test_workspace_search_endpoint_is_bounded(self):
        app = FastAPI()
        app.include_router(build_workspace_router(object(), self.search))
        response = TestClient(app).get("/workspace/search?q=fault&projectId=project-1&limit=3")
        self.assertEqual(200, response.status_code)
        self.assertLessEqual(response.json()["count"], 3)

    def test_shell_supports_keyboard_recents_pins_and_required_actions(self):
        source = (Path(__file__).resolve().parents[1] / "azure-devops-extension/src/engineeringCommandCenterShell.tsx").read_text()
        for marker in ("event.ctrlKey || event.metaKey", "ArrowDown", "ArrowUp", "hei.palette.recent", "hei.palette.pinned"):
            self.assertIn(marker, source)
        for action in ("New Requirement", "Sync Repository", "Open Planning", "Open Execution", "Open Activity", "Refresh Dashboard", "Generate Planning Pack", "Open Repository", "Open Current Sprint", "Open Agent Center"):
            self.assertIn(action, source)


if __name__ == "__main__":
    unittest.main()
