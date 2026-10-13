"""Workflow scheduler utilities."""

from __future__ import annotations

from typing import Any

from .types import workflow_event


class AgentScheduler:
    def running(self, workflows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [workflow for workflow in workflows if workflow.get("state") == "Running"]

    def waiting(self, workflows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [workflow for workflow in workflows if workflow.get("state") == "WaitingApproval"]

    def completed(self, workflows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [workflow for workflow in workflows if workflow.get("state") == "Completed"]

    def failed(self, workflows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [workflow for workflow in workflows if workflow.get("state") == "Failed"]

    def retry(self, workflow: dict[str, Any]) -> dict[str, Any]:
        workflow["retryCount"] = int(workflow.get("retryCount") or 0) + 1
        workflow["state"] = "WaitingApproval"
        workflow["status"] = "Waiting"
        workflow["errors"] = []
        workflow["timeline"].append(workflow_event("Workflow retry prepared", "Waiting", {"retryCount": workflow["retryCount"]}))
        return workflow
