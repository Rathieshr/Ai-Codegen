"""Provider-free model routing and deterministic prompt generation."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.model_adapters import ModelAdapterCompiler, ModelAdapterRegistry
from backend.prompt_compiler import PromptCompiler
from backend.prompt_optimizer import PromptOptimizer
from backend.token_intelligence import TokenBudgetEngine
from backend.token_intelligence.models import SUPPORTED_TOKEN_BUDGETS, stable_hash

from .models import PROVIDER_ROUTER_VERSION, ProviderRoutingResult
from .rules import ROUTING_PRIORITIES, ROUTING_RULES, normalize_model_id, optimizer_mode, resolve_target


class ProviderRouter:
    version = PROVIDER_ROUTER_VERSION

    def __init__(self, *, model_registry: Any) -> None:
        self.model_registry = model_registry
        self.adapter_registry = ModelAdapterRegistry()
        self.adapter_compiler = ModelAdapterCompiler(model_registry=model_registry, adapter_registry=self.adapter_registry)
        self.prompt_compiler = PromptCompiler()
        self.token_engine = TokenBudgetEngine()
        self.prompt_optimizer = PromptOptimizer()

    def route(
        self,
        execution_manifest: dict[str, Any],
        *,
        execution_mode: str,
        repository_mode: str,
        target_task: Any,
        user_preference: Any,
        available_models: list[Any] | None,
    ) -> ProviderRoutingResult:
        manifest = deepcopy(execution_manifest) if isinstance(execution_manifest, dict) else {}
        self._validate_manifest(manifest)
        compiled = self.prompt_compiler.compile(manifest)
        target, target_reason = resolve_target(target_task, execution_mode)
        mode = optimizer_mode(execution_mode, target)
        available, source = self._available_models(available_models)
        preference = _preference_model(user_preference)
        candidates = _candidate_order(target, preference, available, self.adapter_registry.list_ids())
        manifest_repository_mode = _manifest_repository_mode(manifest)
        effective_repository_mode = manifest_repository_mode or str(repository_mode or "Unavailable")
        reasons = [target_reason]
        warnings: list[str] = []
        if repository_mode and manifest_repository_mode and _mode_key(repository_mode) != _mode_key(manifest_repository_mode):
            warnings.append("Requested repository mode differs from the Execution Manifest; manifest repository mode was retained as source of truth.")
        rejected: list[dict[str, str]] = []
        attempts: list[dict[str, Any]] = []
        selected: tuple[dict[str, Any], dict[str, Any], int] | None = None

        if preference and preference not in available:
            reasons.append(f"User preference {preference} was unavailable and could not be applied.")
        for model_id in candidates:
            profile = self.model_registry.get(model_id)
            rejection = _eligibility_rejection(model_id, profile, available, self.adapter_registry.list_ids())
            if rejection:
                rejected.append({"modelId": model_id, "reason": rejection})
                continue
            result = self._build_prompt(compiled, profile, mode, attempts)
            if result:
                selected = (profile, result[0], result[1])
                break
            rejected.append({"modelId": model_id, "reason": "Prompt could not fit any supported budget for this model profile."})

        if not selected:
            detail = "; ".join(f"{item['modelId']}: {item['reason']}" for item in rejected) or "No eligible model candidates."
            raise ValueError(f"No provider route is available. {detail}")

        profile, prompt, budget = selected
        preferred_applied = bool(preference and profile["id"] == preference)
        fallback_used = profile["id"] != ROUTING_PRIORITIES[target][0]
        if preferred_applied:
            reasons.append(f"User preference selected {profile['name']} after eligibility and context checks.")
        else:
            reasons.append(f"Selected {profile['name']} using the {target.replace('_', ' ')} routing priority.")
        if fallback_used:
            reasons.append("A lower-priority model was selected because earlier routing candidates were unavailable or ineligible.")
        reasons.append(f"The prompt fits the {budget}-token budget and the {profile['name']} context window.")
        if effective_repository_mode == "Unavailable":
            warnings.append("Repository context is unavailable; the selected prompt carries reduced grounding confidence.")

        core = {
            "routerVersion": self.version,
            "executionManifestId": str(manifest.get("manifestId") or ""),
            "selectedProvider": {
                "modelId": profile["id"],
                "modelName": profile["name"],
                "provider": profile["provider"],
                "contextWindow": profile["contextWindow"],
            },
            "routingDecision": {
                "status": "Selected",
                "target": target,
                "executionMode": mode,
                "repositoryMode": effective_repository_mode,
                "userPreference": preference,
                "userPreferenceApplied": preferred_applied,
                "fallbackUsed": fallback_used,
                "selectedBudgetTokens": budget,
            },
            "prompt": prompt,
            "reasons": reasons,
            "routingRules": [deepcopy(rule) for rule in ROUTING_RULES],
            "warnings": list(dict.fromkeys(warnings)),
        }
        identity_core = {key: value for key, value in core.items() if key != "prompt"}
        identity_core["promptImmutableHash"] = prompt["immutableHash"]
        immutable_hash = stable_hash(identity_core)
        return {
            "routingId": f"providerroute_{immutable_hash[:12]}",
            **core,
            "immutable": True,
            "immutableHash": immutable_hash,
            "routedAt": datetime.now(timezone.utc).isoformat(),
            "diagnostics": {
                "availableModels": available,
                "availableModelsSource": source,
                "candidateOrder": candidates,
                "rejectedModels": rejected,
                "routingAttempts": attempts,
                "appliedRule": target,
                "manifestRepositoryMode": manifest_repository_mode,
                "requestedRepositoryMode": str(repository_mode or ""),
                "manifestTokenEstimate": int((manifest.get("tokenEstimates") or {}).get("manifestTokens") or 0),
                "compiledPromptId": compiled["compiledPromptId"],
                "budgetedPromptId": prompt["sourceBudgetedPromptId"],
                "executionPromptId": prompt["sourceExecutionPromptId"],
                "optimizedPromptId": prompt["optimizedPromptId"],
                "providerInvoked": False,
                "networkCalls": 0,
                "llmUsed": False,
            },
        }

    def cache_lookup_context(
        self,
        execution_manifest: dict[str, Any],
        *,
        execution_mode: str,
        repository_mode: str,
        target_task: Any,
        user_preference: Any,
        available_models: list[Any] | None,
    ) -> dict[str, Any]:
        """Resolve the first eligible route without compiling a prompt."""
        manifest = deepcopy(execution_manifest) if isinstance(execution_manifest, dict) else {}
        self._validate_manifest(manifest)
        target, _ = resolve_target(target_task, execution_mode)
        mode = optimizer_mode(execution_mode, target)
        available, source = self._available_models(available_models)
        preference = _preference_model(user_preference)
        candidates = _candidate_order(target, preference, available, self.adapter_registry.list_ids())
        eligible = [
            model_id
            for model_id in candidates
            if not _eligibility_rejection(
                model_id,
                self.model_registry.get(model_id),
                available,
                self.adapter_registry.list_ids(),
            )
        ]
        manifest_repository_mode = _manifest_repository_mode(manifest)
        return {
            "target": target,
            "executionMode": mode,
            "repositoryMode": manifest_repository_mode or str(repository_mode or "Unavailable"),
            "candidateModels": candidates,
            "eligibleModels": eligible,
            "firstEligibleModel": eligible[0] if eligible else "",
            "availableModels": available,
            "availableModelsSource": source,
        }

    def _build_prompt(
        self,
        compiled: dict[str, Any],
        profile: dict[str, Any],
        mode: str,
        attempts: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], int] | None:
        for budget in (value for value in SUPPORTED_TOKEN_BUDGETS if value <= int(profile["contextWindow"])):
            bounded = self.token_engine.optimize(compiled, budget_tokens=budget)
            attempt = {"modelId": profile["id"], "budgetTokens": budget, "budgetStatus": bounded["status"]}
            if bounded["status"] != "Ready":
                attempts.append(attempt)
                continue
            execution = self.adapter_compiler.compile(bounded, profile["id"])
            attempt["adapterStatus"] = execution["status"]
            if execution["status"] != "Ready":
                attempts.append(attempt)
                continue
            optimized = self.prompt_optimizer.optimize(execution, mode)
            attempt["optimizerStatus"] = optimized["status"]
            attempts.append(attempt)
            if optimized["status"] != "Blocked":
                return optimized, budget
        return None

    def _available_models(self, values: list[Any] | None) -> tuple[list[str], str]:
        if values is not None:
            normalized = list(dict.fromkeys(normalize_model_id(value.get("id") if isinstance(value, dict) else value) for value in values))
            return [value for value in normalized if value], "request"
        return [profile["id"] for profile in self.model_registry.list() if profile.get("enabled")], "model_registry"

    @staticmethod
    def _validate_manifest(manifest: dict[str, Any]) -> None:
        if not manifest.get("manifestId") or manifest.get("immutable") is not True:
            raise ValueError("An immutable Execution Manifest is required.")


def _candidate_order(target: str, preference: str, available: list[str], adapters: list[str]) -> list[str]:
    values = [preference] if preference else []
    values.extend(ROUTING_PRIORITIES[target])
    values.extend(model_id for model_id in available if model_id in adapters)
    return list(dict.fromkeys(value for value in values if value))


def _eligibility_rejection(model_id: str, profile: dict[str, Any] | None, available: list[str], adapters: list[str]) -> str:
    if model_id not in available:
        return "Model is not in the available-model set."
    if not profile:
        return "Model is not registered."
    if not profile.get("enabled"):
        return "Model profile is disabled."
    if model_id not in adapters:
        return "No deterministic Model Adapter is registered."
    return ""


def _preference_model(value: Any) -> str:
    if isinstance(value, dict):
        if value.get("localOnly") is True or str(value.get("providerMode") or "").casefold() == "local":
            return "ollama"
        value = value.get("modelId") or value.get("model") or value.get("provider")
    return normalize_model_id(value)


def _manifest_repository_mode(manifest: dict[str, Any]) -> str:
    repository = manifest.get("repositoryContext") if isinstance(manifest.get("repositoryContext"), dict) else {}
    return str(repository.get("repositoryMode") or "")


def _mode_key(value: Any) -> str:
    return "".join(character for character in str(value or "").casefold() if character.isalnum())
