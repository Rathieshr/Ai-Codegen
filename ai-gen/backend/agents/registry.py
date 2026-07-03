"""Agent registry and trigger mapping."""

from __future__ import annotations

from typing import Any


class AgentRegistry:
    def __init__(self) -> None:
        self._agents = {
            "planning": {
                "name": "Planning Agent",
                "responsibility": "Analyze planning changes, prepare stories, generate tasks, suggest acceptance criteria, and prepare execution context.",
                "triggers": ["Story Created", "Story Approved", "Feature Updated", "Capability Approved"],
                "actions": ["Analyze", "Prepare Story", "Generate Tasks", "Suggest Acceptance Criteria", "Prepare Execution"],
                "checkpoint": "Approve Planning Output",
                "featureFlag": "planningAgent",
            },
            "execution": {
                "name": "Execution Agent",
                "responsibility": "Build execution package, generate execution plan, prepare context capsule, and notify VS Code.",
                "triggers": ["Task Approved", "Story Execution Started"],
                "actions": ["Build Execution Package", "Generate Execution Plan", "Prepare Context Capsule", "Notify VS Code"],
                "checkpoint": "Developer Starts Work",
                "featureFlag": "executionAgent",
            },
            "qa": {
                "name": "QA Agent",
                "responsibility": "Prepare QA analysis, missing tests, regression analysis, and readiness.",
                "triggers": ["Implementation Validation Passed"],
                "actions": ["Generate QA Analysis", "Generate Missing Tests", "Regression Analysis", "QA Readiness"],
                "checkpoint": "Approve QA Recommendation",
                "featureFlag": "qaAgent",
            },
            "review": {
                "name": "Review Agent",
                "responsibility": "Run PR review, compare against Execution Package, check acceptance coverage, and report findings.",
                "triggers": ["PR Created", "Pull Request Created"],
                "actions": ["Run PR Review", "Compare Against Execution Package", "Check Acceptance Coverage", "Report Findings"],
                "checkpoint": "Human Merge Decision",
                "featureFlag": "reviewAgent",
            },
            "memory": {
                "name": "Memory Agent",
                "responsibility": "Extract reusable knowledge, store validated patterns, update Engineering Memory, and archive obsolete memory.",
                "triggers": ["Story Completed", "PR Merged", "QA Passed", "Release Completed", "Artifact Approved", "Work Item Approved"],
                "actions": ["Extract Reusable Knowledge", "Store Validated Patterns", "Update Engineering Memory", "Archive Obsolete Memory"],
                "checkpoint": "Memory Curator Review",
                "featureFlag": "memoryAgent",
            },
            "repository": {
                "name": "Repository Agent",
                "responsibility": "Refresh Repository Intelligence, refresh Engineering Graph, and update Knowledge Registry.",
                "triggers": ["Repository Scan", "Branch Change", "Module Change"],
                "actions": ["Refresh Repository Intelligence", "Refresh Engineering Graph", "Update Knowledge Registry"],
                "checkpoint": "Review Repository Refresh",
                "featureFlag": "repositoryAgent",
            },
        }

    def list_agents(self) -> list[dict[str, Any]]:
        return [{"id": agent_id, **agent} for agent_id, agent in self._agents.items()]

    def resolve(self, event_type: str) -> dict[str, Any] | None:
        for agent_id, agent in self._agents.items():
            if event_type in agent.get("triggers", []):
                return {"id": agent_id, **agent}
        return None
