"""Deterministic end-to-end hardening harness for the converged HEI pipeline."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from backend.context_orchestration import ContextOrchestrator
from backend.context_orchestration.models import ContextRequest, ContextSourceResult, ContextSourceType
from backend.convergence import ConsumerRequest, ExecutionPackageConsumerService
from backend.execution import ExecutionPackageBuilder, ExecutionRequest
from backend.platform import PlatformFoundation
from backend.platform.shared import JsonMapStore

from .scenarios import SCENARIOS, scenario_by_id
from .store import HardeningRunStore


class InstrumentedSource:
    def __init__(self, source_type: ContextSourceType, version: str, items: list[dict[str, Any]], tracker: dict[str, int], *, available: bool = True, freshness: str = "Fresh") -> None:
        self.source_type = source_type
        self.version = version
        self.items = items
        self.tracker = tracker
        self.available = available
        self.freshness = freshness

    def retrieve(self, request: ContextRequest) -> ContextSourceResult:
        key = {
            ContextSourceType.REPOSITORY: "repositoryQueries",
            ContextSourceType.ENGINEERING_MEMORY: "memoryQueries",
            ContextSourceType.KNOWLEDGE_REGISTRY: "knowledgeQueries",
            ContextSourceType.PLANNING: "planningQueries",
        }.get(self.source_type, f"{self.source_type.value}Queries")
        self.tracker[key] = self.tracker.get(key, 0) + 1
        warning = [] if self.available else [f"{self.source_type.value} source unavailable."]
        return ContextSourceResult(self.source_type, self.available, self.freshness if self.available else "Unavailable", version=self.version, items=self.items if self.available else [], warnings=warning, diagnostics={"instrumented": True})


class HEIEndToEndHarness:
    def __init__(self, storage_root: Path, platform: PlatformFoundation | None = None) -> None:
        self.storage_root = storage_root
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.platform = platform or PlatformFoundation(storage_root / "platform")
        self.store = HardeningRunStore(storage_root)
        self.consumer = ExecutionPackageConsumerService(self.platform)

    def run_all(self, repository_mode: str = "KnowledgeSnapshot", token_budget: int = 4000, repository_freshness: str = "Fresh") -> dict[str, Any]:
        runs = [self.run_scenario(item["scenarioId"], repository_mode=repository_mode, token_budget=token_budget, repository_freshness=repository_freshness) for item in SCENARIOS]
        return {"runs": runs, "summary": self.summary()}

    def run_scenario(self, scenario_id: str, *, repository_mode: str = "KnowledgeSnapshot", token_budget: int = 4000, failure_stage: str = "", repository_freshness: str = "Fresh") -> dict[str, Any]:
        scenario = scenario_by_id(scenario_id)
        if not scenario:
            raise ValueError(f"Unknown hardening scenario '{scenario_id}'.")
        run_id = f"run_{uuid4().hex[:12]}"
        correlation_id = f"corr_{uuid4().hex[:12]}"
        started_at = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()
        tracker = {"contextOrchestrationRequests": 0, "repositoryQueries": 0, "graphQueries": 0, "memoryQueries": 0, "knowledgeQueries": 0, "planningQueries": 0}
        artifacts: dict[str, Any] = {}
        timings: dict[str, float] = {}
        warnings: list[str] = []
        blockers: list[str] = []
        assertions: list[dict[str, Any]] = []

        def stage(name: str, action: Callable[[], Any]) -> Any:
            sequence = len(self.store.trace(correlation_id)) + 1
            stage_started = time.perf_counter()
            self._trace(correlation_id, run_id, sequence, name, "Started", {})
            try:
                if failure_stage == name:
                    raise RuntimeError(f"Injected {name} failure")
                value = action()
                duration = round((time.perf_counter() - stage_started) * 1000, 2)
                timings[name] = duration
                self._trace(correlation_id, run_id, sequence + 1, name, "Completed", {"durationMs": duration, **self._lineage_details(value)})
                return value
            except Exception as exc:
                duration = round((time.perf_counter() - stage_started) * 1000, 2)
                timings[name] = duration
                message = f"{name} failed ({type(exc).__name__}). Retry the operation using correlation ID {correlation_id}."
                blockers.append(message)
                self._trace(correlation_id, run_id, sequence + 1, name, "Failed", {"durationMs": duration, "errorType": type(exc).__name__, "message": message})
                self.platform.activity.add_activity({"activityType": "HardeningFailure", "title": name, "description": message, "source": "API", "correlationId": correlation_id, "metadata": {"runId": run_id}})
                self.platform.audit.record({"action": "HardeningStageFailed", "actor": "system", "source": "API", "targetType": "HardeningRun", "targetId": run_id, "after": {"stage": name, "message": message}, "correlationId": correlation_id})
                raise

        try:
            lineage = stage("Planning", lambda: self._planning_lineage(scenario))
            artifacts.update(lineage)
            sources = self._sources(scenario, repository_mode, tracker, repository_freshness=repository_freshness)
            orchestrator = ContextOrchestrator(sources=sources, store=JsonMapStore(self.storage_root / f"contexts_{run_id}.json"), platform=self.platform)
            request = ContextRequest(
                request_id=f"ctx_{run_id}", correlation_id=correlation_id, purpose="ImplementationPackage",
                project_id="hei-hardening", repository_id="repository-hardening",
                repository_snapshot_version="snapshot-v3" if repository_mode != "Unavailable" else "",
                artifact=lineage["story"], options={"maxTokens": token_budget, "reservedTokens": min(800, token_budget // 2)},
            )
            tracker["contextOrchestrationRequests"] += 1
            capsule = stage("ContextOrchestration", lambda: orchestrator.orchestrate(request))
            warnings.extend(capsule.get("warnings") or [])
            capsule.update({
                "capsuleVersion": "3.5", "knowledgeVersion": "knowledge-v5",
                "engineeringMemoryVersion": "memory-v2", "planningVersion": "planning-v1",
                "artifact": lineage["story"], "businessGoal": scenario["requirement"], "acceptanceCriteria": scenario["acceptanceCriteria"],
                "selectedCapabilities": scenario["domains"], "selectedStandards": ["Input validation", "Authorization", "Audit logging"],
                "suggestedTests": ["Acceptance-mapped unit tests", "Permission tests"],
                "diagnostics": {**capsule.get("diagnostics", {}), "repositoryMode": repository_mode, "retrievalCounts": tracker},
            })
            artifacts["contextCapsule"] = stage("ContextCapsule", lambda: dict(capsule))
            package = stage("ExecutionPackage", lambda: ExecutionPackageBuilder().build(capsule, ExecutionRequest("ImplementationPackage", story_id=lineage["story"]["id"], task_id=lineage["task"]["id"], repository_snapshot_version=request.repository_snapshot_version)))
            artifacts["executionPackage"] = package
            prompt = stage("DeveloperPrompt", lambda: self.consumer.consume(ConsumerRequest("DeveloperPrompt", package, correlation_id=correlation_id)))
            artifacts["developerPrompt"] = prompt
            changed_files = package.get("repositoryContext", {}).get("relevantFiles", [])
            validation = stage("Validation", lambda: self.consumer.consume(ConsumerRequest("Validation", package, runtime_evidence={"changedFiles": changed_files, "testResults": {"passed": True}}, correlation_id=correlation_id)))
            artifacts["validation"] = validation
            qa = stage("QA", lambda: self.consumer.consume(ConsumerRequest("QA", package, correlation_id=correlation_id)))
            artifacts["qa"] = qa
            memory = stage("MemoryCaptureDraft", lambda: self.consumer.consume(ConsumerRequest("MemoryCapture", package, runtime_evidence={"validationResult": validation, "qaResult": qa}, correlation_id=correlation_id)))
            memory["approvalStatus"] = "Draft"
            artifacts["memoryCaptureDraft"] = memory
            assertions = self._assertions(scenario, repository_mode, token_budget, correlation_id, capsule, package, prompt, tracker)
            failed_assertions = [item for item in assertions if not item["passed"]]
            if failed_assertions:
                blockers.extend(item["message"] for item in failed_assertions)
            status = "Blocked" if package.get("metadata", {}).get("status") == "Blocked" else "Failed" if failed_assertions else "Passed"
        except Exception:
            status = "Blocked"

        duration = round((time.perf_counter() - started) * 1000, 2)
        package = artifacts.get("executionPackage") or {}
        run = {
            "runId": run_id, "correlationId": correlation_id, "scenarioId": scenario_id, "scenarioName": scenario["name"],
            "projectId": "hei-hardening", "repositoryId": "repository-hardening", "repositoryMode": repository_mode,
            "repositoryFreshness": repository_freshness,
            "status": status, "readiness": (package.get("metadata") or {}).get("executionReadiness", 0), "durationMs": duration,
            "tokenBudget": token_budget, "tokenUsage": (artifacts.get("contextCapsule") or {}).get("tokenBudget", {}),
            "artifactLineage": {key: value.get("id") for key, value in artifacts.items() if key in {"epic", "capability", "feature", "story", "task"}},
            "capsuleVersion": (artifacts.get("contextCapsule") or {}).get("capsuleVersion"),
            "executionPackageVersion": (package.get("diagnostics") or {}).get("builderVersion"),
            "repositorySnapshot": (package.get("metadata") or {}).get("repositorySnapshotVersion"),
            "knowledgeVersion": (package.get("metadata") or {}).get("knowledgeVersion"),
            "memoryVersion": (package.get("metadata") or {}).get("engineeringMemoryVersion"),
            "provider": "deterministic", "stageTimings": timings, "retrievalCounts": tracker,
            "warnings": warnings, "blockers": blockers, "assertions": assertions, "artifacts": artifacts,
            "startedAt": started_at, "completedAt": datetime.now(timezone.utc).isoformat(),
        }
        self.store.save_run(run)
        self._trace(
            correlation_id,
            run_id,
            len(self.store.trace(correlation_id)) + 1,
            "Lifecycle",
            status,
            {
                "projectId": run["projectId"], "repositoryId": run["repositoryId"],
                "artifactLineage": run["artifactLineage"], "capsuleVersion": run["capsuleVersion"],
                "executionPackageVersion": run["executionPackageVersion"], "repositorySnapshot": run["repositorySnapshot"],
                "knowledgeVersion": run["knowledgeVersion"], "memoryVersion": run["memoryVersion"],
                "provider": run["provider"], "tokenUsage": run["tokenUsage"], "stageTimings": timings,
                "warnings": warnings, "blockers": blockers, "durationMs": duration,
            },
        )
        return run

    def summary(self) -> dict[str, Any]:
        runs = self.store.list_runs(limit=1000)
        durations = [float(item.get("durationMs") or 0) for item in runs]
        readiness = [float(item.get("readiness") or 0) for item in runs]
        passed = [item for item in runs if item.get("status") == "Passed"]
        stage_targets = {
            "ContextOrchestration": 2000, "ContextCapsule": 1000, "ExecutionPackage": 2000,
            "DeveloperPrompt": 2000, "Validation": 5000, "QA": 5000,
        }
        stage_timings: dict[str, list[float]] = {}
        for run in runs:
            for stage, duration in dict(run.get("stageTimings") or {}).items():
                stage_timings.setdefault(stage, []).append(float(duration or 0))
        performance = {
            stage: {
                "averageMs": round(sum(values) / len(values), 2),
                "maximumMs": round(max(values), 2),
                "targetMs": stage_targets.get(stage),
                "withinTarget": not stage_targets.get(stage) or max(values) <= stage_targets[stage],
                "sampleCount": len(values),
            }
            for stage, values in stage_timings.items()
        }
        return {
            "totalScenarios": len(runs), "passed": len(passed),
            "failed": sum(item.get("status") == "Failed" for item in runs),
            "blocked": sum(item.get("status") == "Blocked" for item in runs),
            "averageReadiness": round(sum(readiness) / len(readiness), 2) if readiness else 0,
            "averageDurationMs": round(sum(durations) / len(durations), 2) if durations else 0,
            "tokenBudgetFailures": self._failure_count(runs, "token"),
            "repositoryEvidenceFailures": self._failure_count(runs, "repository"),
            "contextLeakageFailures": self._failure_count(runs, "leakage"),
            "lastSuccessfulRun": passed[0].get("completedAt") if passed else None,
            "performanceBaseline": performance,
        }

    def _sources(self, scenario: dict[str, Any], mode: str, tracker: dict[str, int], *, repository_freshness: str = "Fresh") -> list[InstrumentedSource]:
        planning = [{"id": f"story-{scenario['scenarioId']}", "artifactType": "Story", "title": scenario["name"], "description": scenario["requirement"], "acceptanceCriteria": scenario["acceptanceCriteria"], "category": "Planning", "confidenceScore": 0.95}]
        knowledge = [{"id": f"knowledge-{index}", "title": domain, "content": f"Approved project knowledge for {domain}", "category": "Knowledge", "confidenceScore": 0.9} for index, domain in enumerate(scenario["domains"])]
        repository: list[dict[str, Any]] = []
        if mode == "CodeIndexed":
            repository = [{"path": f"src/{_slug(domain)}/OverviewService.cs", "title": f"src/{_slug(domain)}/OverviewService.cs", "content": f"Repository evidence for {domain}", "category": "File", "confidenceScore": 0.9, "directEvidence": True} for domain in scenario["domains"][:3]]
        elif mode == "KnowledgeSnapshot":
            repository = [{"title": domain, "content": f"Module {domain}", "category": "Module", "confidenceScore": 0.75} for domain in scenario["domains"]]
        memory = [{"id": f"memory-{scenario['scenarioId']}", "title": f"Validated {scenario['name']} pattern", "content": "Previously validated implementation pattern", "category": "Memory", "confidenceScore": 0.8}]
        return [
            InstrumentedSource(ContextSourceType.PLANNING, "planning-v1", planning, tracker),
            InstrumentedSource(ContextSourceType.REPOSITORY, "snapshot-v3", repository, tracker, available=mode != "Unavailable", freshness=repository_freshness),
            InstrumentedSource(ContextSourceType.KNOWLEDGE_REGISTRY, "knowledge-v5", knowledge, tracker),
            InstrumentedSource(ContextSourceType.ENGINEERING_MEMORY, "memory-v2", memory, tracker),
        ]

    @staticmethod
    def _planning_lineage(scenario: dict[str, Any]) -> dict[str, dict[str, Any]]:
        slug = scenario["scenarioId"]
        epic = {"id": f"epic-{slug}", "title": scenario["name"], "description": scenario["requirement"], "status": "Approved"}
        capability = {"id": f"capability-{slug}", "title": scenario["domains"][0], "parentId": epic["id"], "status": "Approved"}
        feature = {"id": f"feature-{slug}", "title": scenario["name"], "parentId": capability["id"], "status": "Approved"}
        story = {"id": f"story-{slug}", "artifactType": "Story", "title": scenario["name"], "description": scenario["requirement"], "parentId": feature["id"], "acceptanceCriteria": scenario["acceptanceCriteria"], "status": "Approved"}
        task = {"id": f"task-{slug}", "title": f"Implement {scenario['name']}", "parentId": story["id"], "status": "Approved"}
        return {"epic": epic, "capability": capability, "feature": feature, "story": story, "task": task}

    @staticmethod
    def _assertions(scenario: dict[str, Any], mode: str, budget: int, correlation_id: str, capsule: dict, package: dict, prompt: dict, tracker: dict[str, int]) -> list[dict[str, Any]]:
        selected_titles = [str(item.get("title") or "") for item in capsule.get("selectedContext", [])]
        package_repo = package.get("repositoryContext") or {}
        checks = [
            (capsule.get("correlationId") == correlation_id, "Correlation ID changed during orchestration."),
            (package.get("metadata", {}).get("capsuleVersion") == capsule.get("capsuleVersion"), "Execution Package lost capsule version."),
            (package.get("metadata", {}).get("knowledgeVersion") == "knowledge-v5", "Knowledge version was not preserved."),
            (package.get("metadata", {}).get("engineeringMemoryVersion") == "memory-v2", "Memory version was not preserved."),
            (tracker.get("contextOrchestrationRequests") == 1, "Context was orchestrated more than once."),
            (all(value <= 1 for key, value in tracker.items() if key.endswith("Queries")), "Duplicate context retrieval was detected."),
            (not set(scenario.get("excludedDomains", [])) & set(selected_titles), "Rejected context leaked into the capsule."),
            (prompt.get("consumerDiagnostics", {}).get("correlationId") == correlation_id, "Developer Prompt lost correlation ID."),
            (int(prompt.get("estimatedTokens") or 0) <= budget, "Developer Prompt exceeded its target token budget."),
        ]
        if mode == "KnowledgeSnapshot":
            checks.append((not package_repo.get("relevantFiles") and not package_repo.get("relevantAPIs"), "KnowledgeSnapshot invented code evidence."))
        if mode == "Unavailable":
            checks.extend([(package_repo.get("repositoryMode") == "Unavailable", "Unavailable repository mode was not preserved."), (not package_repo.get("relevantFiles"), "Unavailable repository invented files.")])
        if mode == "CodeIndexed":
            checks.append((bool(package_repo.get("relevantFiles")), "CodeIndexed mode did not preserve file evidence."))
        return [{"passed": passed, "message": message} for passed, message in checks]

    def _trace(self, correlation_id: str, run_id: str, sequence: int, stage: str, status: str, details: dict[str, Any]) -> None:
        event = {"correlationId": correlation_id, "runId": run_id, "sequence": sequence, "stage": stage, "status": status, "timestamp": datetime.now(timezone.utc).isoformat(), "details": details}
        self.store.append_trace(event)

    @staticmethod
    def _lineage_details(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        consumer = value.get("consumerDiagnostics") if isinstance(value.get("consumerDiagnostics"), dict) else {}
        details = {
            "capsuleId": value.get("capsuleId") or metadata.get("capsuleId") or (value.get("diagnostics") or {}).get("capsuleId") or consumer.get("contextCapsuleId"),
            "capsuleVersion": value.get("capsuleVersion") or metadata.get("capsuleVersion") or consumer.get("contextCapsuleVersion"),
            "packageId": value.get("packageId") or value.get("sourcePackageId") or metadata.get("packageId") or consumer.get("packageId"),
            "repositorySnapshotVersion": value.get("repositorySnapshotVersion") or metadata.get("repositorySnapshotVersion") or consumer.get("repositorySnapshotVersion"),
        }
        return {key: item for key, item in details.items() if item}

    @staticmethod
    def _failure_count(runs: list[dict[str, Any]], term: str) -> int:
        return sum(any(term in str(assertion.get("message") or "").casefold() and not assertion.get("passed") for assertion in item.get("assertions", [])) for item in runs)


def _slug(value: str) -> str:
    return "-".join(str(value).casefold().split())
