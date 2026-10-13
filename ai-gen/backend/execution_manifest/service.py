"""Immutable Execution Manifest application service."""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from backend.platform.shared import JsonMapStore

from .builder import ExecutionManifestBuilder


class ExecutionManifestService:
    def __init__(self, store: JsonMapStore, *, builder: ExecutionManifestBuilder | None = None, platform: Any | None = None) -> None:
        self.store = store
        self.builder = builder or ExecutionManifestBuilder()
        self.platform = platform

    def build(self, execution_package: dict[str, Any], correlation_id: str = "") -> dict[str, Any]:
        started = time.perf_counter()
        package_id = str(execution_package.get("packageId") or (execution_package.get("metadata") or {}).get("packageId") or "")
        self._event("ExecutionManifestRequested", correlation_id, {"packageId": package_id})
        manifest = self.builder.build(execution_package)
        values = self.store.read()
        existing = values.get(manifest["manifestId"])
        if existing:
            if existing.get("immutableHash") != manifest.get("immutableHash"):
                raise ValueError("Execution Manifest identity collision detected.")
            self._event("ExecutionManifestReused", correlation_id, {"manifestId": manifest["manifestId"], "packageId": package_id})
            return deepcopy(existing)

        manifest["diagnostics"]["durationMs"] = round((time.perf_counter() - started) * 1000, 2)
        values[manifest["manifestId"]] = manifest
        self.store.write(values)
        payload = {
            "manifestId": manifest["manifestId"],
            "packageId": package_id,
            "confidence": manifest["confidence"],
            "warnings": manifest["warnings"],
            "durationMs": manifest["diagnostics"]["durationMs"],
        }
        self._event("ExecutionManifestBuilt", correlation_id, payload)
        if self.platform:
            self.platform.activity.add_activity({
                "activityType": "ExecutionManifestGeneration",
                "title": "Execution Manifest generated",
                "description": f"Execution Manifest {manifest['manifestId']} was built from {package_id}.",
                "source": "API",
                "correlationId": correlation_id,
                "metadata": payload,
            })
        return deepcopy(manifest)

    def get(self, manifest_id: str) -> dict[str, Any] | None:
        value = self.store.read().get(manifest_id)
        return deepcopy(value) if isinstance(value, dict) else None

    def summary(self, manifest_id: str) -> dict[str, Any] | None:
        manifest = self.get(manifest_id)
        if not manifest:
            return None
        return {
            "manifestId": manifest["manifestId"],
            "manifestVersion": manifest["manifestVersion"],
            "sourcePackageId": manifest["sourcePackageId"],
            "objective": manifest["objective"],
            "acceptanceCriteriaCount": len(manifest["acceptanceCriteria"]),
            "relevantFileCount": len(manifest["relevantFiles"]),
            "dependencyCount": len(manifest["dependencies"]),
            "confidence": manifest["confidence"],
            "warningCount": len(manifest["warnings"]),
            "immutable": manifest["immutable"],
            "generatedAt": manifest["generatedAt"],
        }

    def diagnostics(self, manifest_id: str) -> dict[str, Any] | None:
        manifest = self.get(manifest_id)
        if not manifest:
            return None
        source_versions = manifest["sourceVersions"]
        return {
            "manifestId": manifest_id,
            "manifestVersion": manifest["manifestVersion"],
            "sourcePackageId": manifest["sourcePackageId"],
            "sourceVersions": source_versions,
            "contextCapsuleId": source_versions.get("contextCapsuleId"),
            "contextCapsuleVersion": source_versions.get("contextCapsuleVersion"),
            "repositorySnapshotVersion": source_versions.get("repositorySnapshotVersion"),
            "knowledgeVersion": source_versions.get("knowledgeVersion"),
            "planningVersion": source_versions.get("planningVersion"),
            "engineeringMemoryVersion": source_versions.get("engineeringMemoryVersion"),
            "immutable": manifest["immutable"],
            "immutableHash": manifest["immutableHash"],
            "tokenEstimates": manifest["tokenEstimates"],
            **manifest["diagnostics"],
        }

    def _event(self, event_type: str, correlation_id: str, payload: dict[str, Any]) -> None:
        if self.platform:
            self.platform.events.publish({"eventType": event_type, "source": "API", "correlationId": correlation_id, "payload": payload})
