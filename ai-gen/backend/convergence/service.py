"""Package-only consumer gateway for HEI platform convergence."""

from __future__ import annotations

import time
from typing import Any

from backend.implementation_validation import ImplementationValidationEngine
from backend.execution_manifest import ExecutionManifestBuilder
from backend.prompt_builder import compile_execution_manifest
from backend.prompt_compiler import PromptCompiler
from backend.qa import TestIntelligenceEngine
from backend.token_intelligence import TokenBudgetEngine

from .contracts import ConsumerRequest, trace_diagnostics


class ExecutionPackageConsumerService:
    def __init__(self, platform: Any | None = None, manifest_service: Any | None = None, compiler_service: Any | None = None, token_intelligence_service: Any | None = None) -> None:
        self.platform = platform
        self.manifest_service = manifest_service
        self.compiler_service = compiler_service
        self.token_intelligence_service = token_intelligence_service

    def consume(self, request: ConsumerRequest) -> dict[str, Any]:
        request.validate(); started = time.perf_counter()
        self._event("ConsumerMigrationStarted", request, {})
        package = request.execution_package
        try:
            if request.consumer == "DeveloperPrompt":
                manifest = self.manifest_service.build(package, request.correlation_id) if self.manifest_service else ExecutionManifestBuilder().build(package)
                compiled = self.compiler_service.compile(manifest, request.correlation_id) if self.compiler_service else PromptCompiler().compile(manifest)
                budgeted = self.token_intelligence_service.optimize(
                    compiled,
                    budget_tokens=2048,
                    reserved_output_tokens=384,
                    correlation_id=request.correlation_id,
                ) if self.token_intelligence_service else TokenBudgetEngine().optimize(compiled, budget_tokens=2048, reserved_output_tokens=384)
                result = compile_execution_manifest(manifest, compiled_prompt=compiled, budgeted_prompt=budgeted)
            elif request.consumer == "Validation":
                evidence = request.runtime_evidence
                result = ImplementationValidationEngine().validate(execution_package=package, repository_diff=evidence.get("repositoryDiff"), changed_files=evidence.get("changedFiles"), test_results=evidence.get("testResults"), build_result=evidence.get("buildResult"))
            elif request.consumer == "QA": result = TestIntelligenceEngine().generate_from_execution_package(package)
            elif request.consumer == "MemoryCapture": result = _memory_capture(package, request.runtime_evidence)
            elif request.consumer == "AgentRuntime": result = {"executionPackage": package, "agentContext": request.agent_context, "executionMode": request.execution_mode}
            else: result = _vscode_payload(package)
            duration = round((time.perf_counter() - started) * 1000, 2)
            activity_id = self._activity(request, duration, result)
            result["consumerDiagnostics"] = trace_diagnostics(package, correlation_id=request.correlation_id, activity_id=activity_id, duration_ms=duration, warnings=result.get("warnings", []))
            self._event("ExecutionPackageConsumed", request, {"durationMs": duration, "activityId": activity_id})
            self._event("ConsumerMigrationCompleted", request, {"durationMs": duration})
            return result
        except Exception as exc:
            self._event("ExecutionPackageValidationFailed", request, {"failureReason": str(exc)[:300]})
            raise

    def _event(self, event_type: str, request: ConsumerRequest, payload: dict) -> None:
        if self.platform: self.platform.events.publish({"eventType": event_type, "source": "API", "correlationId": request.correlation_id, "payload": {"consumer": request.consumer, "packageId": request.execution_package.get("packageId"), **payload}})

    def _activity(self, request: ConsumerRequest, duration: float, result: dict) -> str:
        if not self.platform: return ""
        entry = self.platform.activity.add_activity({"activityType": "ExecutionPackageConsumed", "title": f"{request.consumer} consumed Execution Package", "source": "API", "correlationId": request.correlation_id, "metadata": {"consumer": request.consumer, "packageId": request.execution_package.get("packageId"), "durationMs": duration, "warnings": result.get("warnings", [])}})
        self.platform.audit.record({"action": "ExecutionPackageConsumed", "actor": "system", "source": "API", "targetType": request.consumer, "targetId": request.execution_package.get("packageId"), "after": {"durationMs": duration}, "correlationId": request.correlation_id})
        return str(entry.get("activityId") or "")


def _memory_capture(package: dict, evidence: dict) -> dict:
    memory = package.get("engineeringMemory") if isinstance(package.get("engineeringMemory"), dict) else {}
    validation = evidence.get("validationResult") if isinstance(evidence.get("validationResult"), dict) else {}
    qa = evidence.get("qaResult") if isinstance(evidence.get("qaResult"), dict) else {}
    return {"sourcePackageId": package.get("packageId"), "repositorySnapshot": package.get("repositorySnapshotVersion") or (package.get("metadata") or {}).get("repositorySnapshotVersion"), "reusablePatterns": memory.get("reusablePatterns", []), "lessonsLearned": memory.get("lessonsLearned", []), "architectureDecisions": memory.get("architectureDecisions", []), "bugFixes": memory.get("previousBugs", []), "reusableTests": memory.get("reusableTests", []) or qa.get("reusableTests", []), "validationResult": validation, "qaResult": qa, "contextRebuilt": False}


def _vscode_payload(package: dict) -> dict:
    return {"executionPackage": package, "planning": package.get("planningContext", {}), "implementationGuidance": package.get("implementationGuidance", {}), "repositoryContext": package.get("repositoryContext", {}), "suggestedFiles": (package.get("implementationGuidance") or {}).get("suggestedFiles", []), "validation": package.get("validationGuidance", {}), "qa": package.get("qaGuidance", {}), "warnings": (package.get("diagnostics") or {}).get("warnings", []), "confidence": (package.get("metadata") or {}).get("confidence", 0)}
