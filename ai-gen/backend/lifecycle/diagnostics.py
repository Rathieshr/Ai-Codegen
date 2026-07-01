"""Lifecycle diagnostics."""

from __future__ import annotations

from typing import Any


class LifecycleDiagnostics:
    def build(self, state: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {
            "artifactId": state.get("artifactId"),
            "artifactType": state.get("artifactType"),
            "state": state.get("currentState"),
            "contextSignals": {
                "hasTasks": bool(context.get("has_tasks")),
                "hasExecutionPackage": bool(context.get("has_execution_package")),
                "validationStatus": context.get("validation_status") or "Not Run",
                "qaStatus": context.get("qa_status") or "Not Run",
                "releaseRecommendation": context.get("release_recommendation") or "Not Assessed",
            },
            "ruleVersion": "engineering-lifecycle-v1",
        }
