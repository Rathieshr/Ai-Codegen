"""Application service for evidence-backed AI response interpretation."""

from __future__ import annotations

import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.token_intelligence.models import stable_hash

from ..events import RuntimeEventPublisher
from ..interpreter import ResponseInterpreter
from .interpretation_repository import ResponseInterpretationRepository


class ResponseInterpretationService:
    def __init__(
        self,
        repository: ResponseInterpretationRepository,
        *,
        runtime: Any | None = None,
        interpreter: ResponseInterpreter | None = None,
        platform: Any | None = None,
    ) -> None:
        self.repository = repository
        self.runtime = runtime
        self.interpreter = interpreter or ResponseInterpreter()
        self.publisher = RuntimeEventPublisher(platform)

    def interpret(self, request: dict[str, Any]) -> dict[str, Any]:
        session = self._session(request)
        manifest = request.get("executionManifest")
        if not isinstance(manifest, dict):
            raise ValueError("executionManifest is required.")
        if "providerResponse" not in request:
            raise ValueError("providerResponse is required.")
        snapshot = request.get("repositorySnapshot") if isinstance(request.get("repositorySnapshot"), dict) else None
        started = time.perf_counter()
        try:
            interpreted = self.interpreter.interpret(
                request["providerResponse"],
                session_id=session["sessionId"],
                execution_manifest=manifest,
                repository_snapshot=snapshot,
            )
            core = {
                "sessionId": session["sessionId"],
                "manifestId": manifest.get("manifestId"),
                "snapshotId": (snapshot or {}).get("snapshotId"),
                "response": interpreted["structuredResponse"],
            }
            warnings = list(interpreted["warnings"])
            status = "NeedsReview" if interpreted["responseType"] == "Unknown" or not interpreted["engineeringArtifacts"] else "Interpreted"
            result = {
                "interpretationId": f"response_interpretation_{stable_hash(core)[:12]}",
                "interpretationVersion": "5.2",
                "sessionId": session["sessionId"],
                "executionManifestId": str(manifest.get("manifestId") or ""),
                "repositorySnapshotId": str((snapshot or {}).get("snapshotId") or ""),
                "repositorySnapshotVersion": str((snapshot or {}).get("version") or ""),
                "provider": str(session.get("provider") or "Unknown"),
                "model": str(session.get("model") or "Unknown"),
                "status": status,
                "responseType": interpreted["responseType"],
                "structuredExecutionResult": deepcopy(interpreted["structuredResponse"]),
                "rawResponse": deepcopy(interpreted["rawResponse"]),
                "summary": interpreted["summary"],
                "engineeringArtifacts": deepcopy(interpreted["engineeringArtifacts"]),
                "extraction": deepcopy(interpreted["extraction"]),
                "warnings": warnings,
                "risks": list(interpreted["risks"]),
                "architectureNotes": list(interpreted["architectureNotes"]),
                "implementationNotes": list(interpreted["implementationNotes"]),
                "unknownItems": list(interpreted["unknownItems"]),
                "confidence": interpreted["confidence"],
                "repositoryEvidenceStatus": interpreted["repositoryEvidenceStatus"],
                "lineage": deepcopy(interpreted["lineage"]),
                "safety": deepcopy(interpreted["safety"]),
                "diagnostics": {
                    "durationMs": round((time.perf_counter() - started) * 1000, 2),
                    "artifactCount": len(interpreted["engineeringArtifacts"]),
                    "categoryCounts": {key: len(value) for key, value in interpreted["extraction"].items()},
                    "warningCount": len(warnings),
                    "repositorySnapshotAvailable": snapshot is not None,
                    "manifestSupplied": True,
                    "providerCalls": 0,
                    "repositoryWrites": 0,
                    "validationInvoked": False,
                    "qaInvoked": False,
                    "correlationId": str(session.get("correlationId") or ""),
                },
                "interpretedAt": datetime.now(timezone.utc).isoformat(),
            }
            saved = self.repository.save(result)
            event_session = _event_session(session, status)
            self.publisher.publish("ResponseInterpreted", event_session, {"interpretationId": result["interpretationId"], "responseType": result["responseType"], "confidence": result["confidence"]})
            self.publisher.publish("ArtifactsExtracted", event_session, {"interpretationId": result["interpretationId"], "artifactCount": len(result["engineeringArtifacts"]), "categoryCounts": result["diagnostics"]["categoryCounts"]})
            self.publisher.activity(event_session, "AI response interpreted", f"Extracted {len(result['engineeringArtifacts'])} evidence-backed engineering artifacts.", {"interpretationId": result["interpretationId"]})
            return saved
        except Exception as exc:
            event_session = _event_session(session, "Failed")
            self.publisher.publish("ResponseInterpretationFailed", event_session, {"reason": str(exc)})
            self.publisher.activity(event_session, "AI response interpretation failed", str(exc))
            raise

    def get(self, session_id: str) -> dict[str, Any] | None:
        return self.repository.get(session_id)

    def _session(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise ValueError("Interpretation request must be an object.")
        supplied = request.get("executionSession")
        if isinstance(supplied, dict) and str(supplied.get("sessionId") or ""):
            return deepcopy(supplied)
        session_id = str(request.get("sessionId") or "")
        if session_id and self.runtime:
            loaded = self.runtime.get(session_id)
            if loaded:
                return loaded
            raise KeyError(session_id)
        raise ValueError("executionSession or a known sessionId is required.")


def _event_session(session: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        **session,
        "sessionId": str(session.get("sessionId") or ""),
        "status": status,
        "correlationId": str(session.get("correlationId") or ""),
        "runtimeContext": deepcopy(session.get("runtimeContext") or {}),
    }
