"""Execution Package application service and platform integration."""

from __future__ import annotations

import time
from typing import Any

from backend.platform.shared import JsonMapStore

from .package_builder import ExecutionPackageBuilder
from .package_models import ExecutionRequest


class ExecutionPackageService:
    def __init__(
        self,
        store: JsonMapStore,
        *,
        builder: ExecutionPackageBuilder | None = None,
        engineering_intelligence: Any | None = None,
        platform: Any | None = None,
    ) -> None:
        self.store = store
        self.builder = builder or ExecutionPackageBuilder()
        self.engineering_intelligence = engineering_intelligence
        self.platform = platform

    def build(self, capsule: dict[str, Any], request: ExecutionRequest, correlation_id: str = "") -> dict[str, Any]:
        started = time.perf_counter()
        correlation_id = correlation_id or str(capsule.get("correlationId") or "")
        self._event("ExecutionPackageRequested", correlation_id, {"capsuleId": capsule.get("capsuleId") or capsule.get("requestId")})
        try:
            capsule = dict(capsule)
            canonical = capsule.get("engineeringContext")
            if self.engineering_intelligence and isinstance(canonical, dict):
                capsule["engineeringExecutionContext"] = self.engineering_intelligence.execution_context(canonical)
            package = self.builder.build(capsule, request)
            if isinstance(canonical, dict):
                package["engineeringContext"] = {
                    "contextId": canonical.get("contextId"),
                    "contextVersion": canonical.get("contextVersion"),
                }
                if "engineeringExecutionContext" in capsule:
                    package["engineeringExecutionContext"] = capsule["engineeringExecutionContext"]
            package["diagnostics"]["durationMs"] = round((time.perf_counter() - started) * 1000, 2)
            packages = self.store.read(); packages[package["packageId"]] = package; self.store.write(packages)
            payload = {"packageId": package["packageId"], "status": package["metadata"]["status"], "confidence": package["metadata"]["confidence"], "repositorySnapshotVersion": package["metadata"]["repositorySnapshotVersion"], "capsuleVersion": package["metadata"]["capsuleVersion"], "warnings": package["diagnostics"]["warnings"], "durationMs": package["diagnostics"]["durationMs"]}
            self._event("ExecutionPackageBuilt", correlation_id, payload)
            if package["metadata"]["status"] == "Ready": self._event("ExecutionPackageReady", correlation_id, payload)
            if self.platform:
                self.platform.activity.add_activity({"activityType": "ExecutionPackageGeneration", "title": "Execution package generated", "description": f"Execution Package {package['packageId']} is {package['metadata']['status']}.", "source": "API", "correlationId": correlation_id, "metadata": payload})
            return package
        except Exception as exc:
            self._event("ExecutionPackageFailed", correlation_id, {"failureReason": str(exc)[:300]})
            raise

    def get(self, package_id: str) -> dict[str, Any] | None: return self.store.read().get(package_id)

    def summary(self, package_id: str) -> dict[str, Any] | None:
        package = self.get(package_id)
        if not package: return None
        return {"metadata": package["metadata"], "implementationObjective": package["implementationGuidance"]["implementationObjective"], "repositoryMode": package["repositoryContext"]["repositoryMode"], "acceptanceCriteriaCount": len(package["planningContext"]["acceptanceCriteria"]), "suggestedTestCount": len(package["qaGuidance"]["suggestedTests"])}

    def diagnostics(self, package_id: str) -> dict[str, Any] | None:
        package = self.get(package_id)
        return {"packageId": package_id, **package["diagnostics"], "tokenGuidance": package["tokenGuidance"]} if package else None

    def _event(self, event_type: str, correlation_id: str, payload: dict) -> None:
        if self.platform: self.platform.events.publish({"eventType": event_type, "source": "API", "correlationId": correlation_id, "payload": payload})
