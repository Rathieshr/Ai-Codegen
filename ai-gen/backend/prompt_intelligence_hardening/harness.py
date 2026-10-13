"""Production-readiness benchmark for the deterministic Prompt Intelligence pipeline."""

from __future__ import annotations

import platform as runtime_platform
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable
from uuid import uuid4

from backend.execution_manifest import ExecutionManifestBuilder
from backend.model_adapters import ModelAdapterCompiler, ModelAdapterRegistry
from backend.model_registry import ModelRegistry
from backend.platform.shared import JsonMapStore
from backend.prompt_cache import PromptCacheService
from backend.prompt_compiler import PromptCompiler
from backend.prompt_diagnostics import PromptDiagnosticsBuilder
from backend.prompt_optimizer import PromptOptimizer
from backend.provider_router import ProviderRouter, ProviderRouterService
from backend.token_intelligence import TokenBudgetEngine
from backend.token_intelligence.models import SUPPORTED_TOKEN_BUDGETS, stable_hash

from .scenarios import REPOSITORY_SCENARIOS, build_execution_package
from .store import PromptHardeningStore


HARDENING_VERSION = "4.10"
PERFORMANCE_TARGETS_MS = {
    "manifest": 100.0,
    "compile": 100.0,
    "tokenBudget": 150.0,
    "adapter": 100.0,
    "optimizer": 100.0,
    "diagnostics": 100.0,
    "routingCold": 250.0,
    "routingCacheHit": 50.0,
}


class PromptIntelligenceHardeningHarness:
    def __init__(self, storage_root: Path, *, platform: Any | None = None) -> None:
        self.storage_root = storage_root
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.platform = platform
        self.store = PromptHardeningStore(storage_root)
        self.model_registry = ModelRegistry()
        self.adapter_registry = ModelAdapterRegistry()

    def run(self) -> dict[str, Any]:
        run_id = f"prompt-hardening-{uuid4().hex[:12]}"
        timings: dict[str, list[float]] = {stage: [] for stage in PERFORMANCE_TARGETS_MS}
        repository_results, artifacts = self._repository_scenarios(timings)
        small = artifacts["small-code-indexed"]
        adapters = self._adapter_matrix(small, timings)
        budgets = self._budget_matrix(small, timings)
        cache = self._cache_benchmark(small, timings, run_id)
        routing = self._routing_matrix(small)
        diagnostics = self._diagnostics_check(small, timings)
        regression = self._regression_check(small)
        performance = _performance(timings)
        gates = _quality_gates(repository_results, adapters, budgets, cache, routing, diagnostics, regression, performance)
        blockers = [gate["details"] for gate in gates if not gate["passed"]]
        report = {
            "runId": run_id,
            "hardeningVersion": HARDENING_VERSION,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "environment": {
                "python": runtime_platform.python_version(),
                "platform": runtime_platform.platform(),
                "providerInvoked": False,
                "networkCalls": 0,
            },
            "repositoryScenarios": repository_results,
            "modelAdapters": adapters,
            "tokenBudgets": budgets,
            "cache": cache,
            "diagnostics": diagnostics,
            "routing": routing,
            "regression": regression,
            "performance": performance,
            "qualityGates": gates,
            "readiness": {
                "status": "Production Ready" if not blockers else "Blocked",
                "passedGates": sum(gate["passed"] for gate in gates),
                "totalGates": len(gates),
                "blockers": blockers,
            },
            "limitations": [
                "Benchmarks measure deterministic local processing and exclude provider, network, and repository clone latency.",
                "Large repository coverage uses generated repository metadata rather than a live source checkout.",
                "JSON-backed benchmark persistence is intended for single-process validation, not distributed load testing.",
                "Production Ready applies to the deterministic Prompt Intelligence boundary; full repository regression status is reported separately.",
            ],
        }
        return self.store.save(report)

    def latest(self) -> dict[str, Any] | None:
        return self.store.latest()

    def get(self, run_id: str) -> dict[str, Any] | None:
        return self.store.get(run_id)

    def _repository_scenarios(self, timings: dict[str, list[float]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        results: list[dict[str, Any]] = []
        artifacts: dict[str, dict[str, Any]] = {}
        for scenario in REPOSITORY_SCENARIOS:
            started = time.perf_counter()
            package = build_execution_package(scenario)
            manifest = _timed(timings, "manifest", lambda: ExecutionManifestBuilder().build(package))
            compiled = _timed(timings, "compile", lambda: PromptCompiler().compile(manifest))
            budget = 128000 if scenario["repositorySize"] == "Large" else 4096
            budgeted = _timed(timings, "tokenBudget", lambda: TokenBudgetEngine().optimize(compiled, budget_tokens=budget))
            adapted = _timed(timings, "adapter", lambda: ModelAdapterCompiler(model_registry=self.model_registry).compile(budgeted, "codex"))
            optimized = _timed(timings, "optimizer", lambda: PromptOptimizer().optimize(adapted, "implementation"))
            repository = manifest.get("repositoryContext") if isinstance(manifest.get("repositoryContext"), dict) else {}
            relevant_files = list(manifest.get("relevantFiles") or [])
            evidence_safe = bool(relevant_files) if scenario["repositoryMode"] == "CodeIndexed" else not relevant_files
            status = "Passed" if budgeted["status"] == "Ready" and optimized["status"] != "Blocked" and evidence_safe else "Failed"
            result = {
                "id": scenario["id"],
                "name": scenario["repositorySize"] + " Repository",
                "repositoryMode": scenario["repositoryMode"],
                "fileCount": len(relevant_files),
                "status": status,
                "manifestTokens": manifest["tokenEstimates"]["manifestTokens"],
                "promptTokens": optimized["estimatedTokens"],
                "evidenceSafe": evidence_safe,
                "repositoryModePreserved": repository.get("repositoryMode") == scenario["repositoryMode"],
                "durationMs": round((time.perf_counter() - started) * 1000, 2),
            }
            results.append(result)
            artifacts[scenario["id"]] = {
                "package": package,
                "manifest": manifest,
                "compiled": compiled,
                "budgeted": budgeted,
                "adapted": adapted,
                "optimized": optimized,
            }
        return results, artifacts

    def _adapter_matrix(self, source: dict[str, Any], timings: dict[str, list[float]]) -> list[dict[str, Any]]:
        bounded = TokenBudgetEngine().optimize(source["compiled"], budget_tokens=8192)
        results = []
        compiler = ModelAdapterCompiler(model_registry=self.model_registry, adapter_registry=self.adapter_registry)
        for model_id in self.adapter_registry.list_ids():
            started = time.perf_counter()
            adapted = _timed(timings, "adapter", lambda model_id=model_id: compiler.compile(bounded, model_id))
            optimized = _timed(timings, "optimizer", lambda adapted=adapted: PromptOptimizer().optimize(adapted, "implementation"))
            results.append({
                "modelId": model_id,
                "status": "Passed" if adapted["status"] == "Ready" and optimized["status"] != "Blocked" else "Failed",
                "estimatedTokens": optimized["estimatedTokens"],
                "contextLimitRespected": optimized["diagnostics"]["contextLimitRespected"],
                "durationMs": round((time.perf_counter() - started) * 1000, 2),
            })
        return results

    def _budget_matrix(self, source: dict[str, Any], timings: dict[str, list[float]]) -> list[dict[str, Any]]:
        results = []
        for budget in SUPPORTED_TOKEN_BUDGETS:
            bounded = _timed(timings, "tokenBudget", lambda budget=budget: TokenBudgetEngine().optimize(source["compiled"], budget_tokens=budget))
            diagnostics = bounded["diagnostics"]
            safe = all((
                diagnostics["acceptanceCriteriaPreserved"],
                diagnostics["repositoryEvidencePreserved"],
                diagnostics["validationGuidancePreserved"],
                diagnostics["jsonIntegrityValid"],
                diagnostics["jsonTruncated"] is False,
            ))
            results.append({
                "budgetTokens": budget,
                "status": "Passed" if safe and bounded["status"] in {"Ready", "Blocked"} else "Failed",
                "budgetStatus": bounded["status"],
                "estimatedTokens": diagnostics["estimatedTokens"],
                "remainingBudget": diagnostics["remainingBudget"],
                "protectedContextPreserved": diagnostics["protectedContextPreserved"],
                "jsonIntegrityValid": diagnostics["jsonIntegrityValid"],
            })
        return results

    def _cache_benchmark(self, source: dict[str, Any], timings: dict[str, list[float]], run_id: str) -> dict[str, Any]:
        root = self.storage_root / run_id / "cache"
        cache = PromptCacheService(JsonMapStore(root / "entries.json"), JsonMapStore(root / "metrics.json"), platform=self.platform)
        service = ProviderRouterService(
            JsonMapStore(root / "routes.json"),
            router=ProviderRouter(model_registry=self.model_registry),
            prompt_cache=cache,
            platform=self.platform,
        )
        args = {
            "execution_mode": "Implementation",
            "repository_mode": "CodeIndexed",
            "target_task": {"type": "Coding"},
            "user_preference": "",
            "available_models": None,
            "correlation_id": run_id,
        }
        first = _timed(timings, "routingCold", lambda: service.route(source["manifest"], **args))
        second = _timed(timings, "routingCacheHit", lambda: service.route(source["manifest"], **args))
        return {
            "status": "Passed" if first.get("cache", {}).get("status") == "Miss" and second.get("cache", {}).get("status") == "Hit" else "Failed",
            "firstStatus": first.get("cache", {}).get("status"),
            "secondStatus": second.get("cache", {}).get("status"),
            "sameRoutingId": first.get("routingId") == second.get("routingId"),
            "metrics": cache.metrics(),
        }

    def _routing_matrix(self, source: dict[str, Any]) -> dict[str, Any]:
        expected = {
            "Coding": "codex",
            "Architecture": "gpt",
            "UI": "gemini",
            "Documentation": "gpt",
            "Large Context": "claude",
            "Local": "ollama",
        }
        router = ProviderRouter(model_registry=self.model_registry)
        decisions = []
        for target, model_id in expected.items():
            result = router.route(
                source["manifest"],
                execution_mode="Implementation",
                repository_mode="CodeIndexed",
                target_task={"type": target},
                user_preference="",
                available_models=None,
            )
            decisions.append({
                "target": target,
                "expectedModel": model_id,
                "selectedModel": result["selectedProvider"]["modelId"],
                "passed": result["selectedProvider"]["modelId"] == model_id,
            })
        return {"status": "Passed" if all(item["passed"] for item in decisions) else "Failed", "passed": sum(item["passed"] for item in decisions), "total": len(decisions), "decisions": decisions}

    def _diagnostics_check(self, source: dict[str, Any], timings: dict[str, list[float]]) -> dict[str, Any]:
        profile = self.model_registry.get("codex")
        value = _timed(
            timings,
            "diagnostics",
            lambda: PromptDiagnosticsBuilder().build(source["optimized"], source["manifest"], source["package"], profile),
        )
        required = (
            "executionManifestVersion", "executionPackageVersion", "repositorySnapshot", "knowledgeVersion",
            "memoryVersion", "model", "tokenCount", "confidence",
        )
        complete = all(value.get(field) is not None and value.get(field) != "" for field in required)
        return {"status": "Passed" if complete else "Failed", "diagnosticsId": value["diagnosticsId"], "lineageComplete": complete, "warnings": value["warnings"]}

    def _regression_check(self, source: dict[str, Any]) -> dict[str, Any]:
        def fingerprint() -> str:
            manifest = ExecutionManifestBuilder().build(source["package"])
            compiled = PromptCompiler().compile(manifest)
            budgeted = TokenBudgetEngine().optimize(compiled, budget_tokens=4096)
            adapted = ModelAdapterCompiler(model_registry=self.model_registry).compile(budgeted, "codex")
            optimized = PromptOptimizer().optimize(adapted, "implementation")
            return stable_hash({
                "manifest": manifest["immutableHash"],
                "compiled": compiled["immutableHash"],
                "budgeted": budgeted["immutableHash"],
                "adapted": adapted["immutableHash"],
                "optimized": optimized["immutableHash"],
            })
        first = fingerprint()
        second = fingerprint()
        return {"status": "Passed" if first == second else "Failed", "stable": first == second, "fingerprint": first}


def _timed(timings: dict[str, list[float]], stage: str, action: Callable[[], Any]) -> Any:
    started = time.perf_counter()
    value = action()
    timings[stage].append(round((time.perf_counter() - started) * 1000, 4))
    return value


def _performance(timings: dict[str, list[float]]) -> dict[str, Any]:
    stages = {}
    for stage, target in PERFORMANCE_TARGETS_MS.items():
        values = timings.get(stage) or [0.0]
        stages[stage] = {
            "averageMs": round(mean(values), 2),
            "maximumMs": round(max(values), 2),
            "targetMs": target,
            "withinTarget": max(values) <= target,
            "sampleCount": len(values),
        }
    return {"status": "Passed" if all(value["withinTarget"] for value in stages.values()) else "Failed", "stages": stages}


def _quality_gates(repository, adapters, budgets, cache, routing, diagnostics, regression, performance) -> list[dict[str, Any]]:
    values = (
        ("Repository modes", all(item["status"] == "Passed" and item["repositoryModePreserved"] for item in repository), "Large, small, snapshot, and unavailable modes preserve truthful evidence."),
        ("Model adapters", all(item["status"] == "Passed" for item in adapters), "Every registered deterministic adapter produces a bounded prompt."),
        ("Token safety", all(item["status"] == "Passed" for item in budgets), "Every supported budget preserves protected JSON context."),
        ("Prompt cache", cache["status"] == "Passed" and cache["sameRoutingId"], "Repeated generation is served from cache with immutable routing identity."),
        ("Provider routing", routing["status"] == "Passed", "Every routing rule selects the expected eligible model."),
        ("Prompt diagnostics", diagnostics["status"] == "Passed", "Prompt lineage and model diagnostics are complete."),
        ("Regression stability", regression["status"] == "Passed", "Two identical runs produce the same deterministic fingerprint."),
        ("Performance", performance["status"] == "Passed", "Every deterministic stage remains within its local benchmark target."),
    )
    return [{"name": name, "passed": passed, "details": details} for name, passed, details in values]
