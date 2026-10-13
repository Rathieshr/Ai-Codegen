"""Central orchestration for evidence-grounded engineering reasoning."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import replace
from typing import Any

from backend.prompt_budget import estimateTokens

from ..cache import ReasoningCache
from ..models import ReasoningRequest, ReasoningResult, ReasoningTelemetry
from ..providers import (
    ClaudeProvider,
    GeminiProvider,
    LocalProvider,
    OpenAIProvider,
    PhiProvider,
    ReasoningProviderRegistry,
)
from .confidence_calculator import ConfidenceCalculator
from .decision_explainer import DecisionExplainer
from .prompt_builder import PromptBuilder
from .response_validator import ResponseValidation, ResponseValidator
from .telemetry import ReasoningTelemetryStore


class ReasoningEngine:
    """The only public entry point for provider-backed engineering judgment."""

    def __init__(
        self,
        *,
        registry: ReasoningProviderRegistry | None = None,
        prompt_builder: PromptBuilder | None = None,
        validator: ResponseValidator | None = None,
        confidence_calculator: ConfidenceCalculator | None = None,
        explainer: DecisionExplainer | None = None,
        cache: ReasoningCache | None = None,
        telemetry: ReasoningTelemetryStore | None = None,
    ) -> None:
        self.registry = registry or _default_registry()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.validator = validator or ResponseValidator()
        self.confidence_calculator = confidence_calculator or ConfidenceCalculator()
        self.explainer = explainer or DecisionExplainer()
        self.cache = cache or ReasoningCache()
        self.telemetry = telemetry or ReasoningTelemetryStore()

    def reason(
        self,
        workflow_type: str,
        engineering_context: dict[str, Any] | Any,
        user_requirement: str = "",
        *,
        provider: str = "Auto",
        correlation_id: str = "",
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = ReasoningRequest(
            workflowType=workflow_type,
            engineeringContext=_context_dict(engineering_context),
            userRequirement=user_requirement,
            providerPreference=provider,
            correlationId=correlation_id,
            options=options or {},
        )
        return self._execute(request, str((options or {}).get("operation") or "reason"))

    def recommend(self, workflow_type: str, engineering_context: Any, **kwargs: Any) -> dict[str, Any]:
        return self._operation("recommend", workflow_type, engineering_context, kwargs)

    def analyze(self, workflow_type: str, engineering_context: Any, **kwargs: Any) -> dict[str, Any]:
        return self._operation("analyze", workflow_type, engineering_context, kwargs)

    def refine(self, workflow_type: str, engineering_context: Any, **kwargs: Any) -> dict[str, Any]:
        return self._operation("refine", workflow_type, engineering_context, kwargs)

    def summarize(self, workflow_type: str, engineering_context: Any, **kwargs: Any) -> dict[str, Any]:
        return self._operation("summarize", workflow_type, engineering_context, kwargs)

    def explain(self, workflow_type: str, engineering_context: Any, **kwargs: Any) -> dict[str, Any]:
        return self._operation("reason", workflow_type, engineering_context, kwargs)

    def is_provider_available(self, preference: str = "Auto") -> bool:
        selected, _ = self.registry.select(preference)
        return selected is not None

    def _operation(
        self,
        operation: str,
        workflow_type: str,
        engineering_context: Any,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        options = dict(kwargs.pop("options", {}) or {})
        options["operation"] = operation
        return self.reason(workflow_type, engineering_context, options=options, **kwargs)

    def _execute(self, request: ReasoningRequest, operation: str) -> dict[str, Any]:
        started = time.monotonic()
        selected, attempted = self.registry.select(request.providerPreference)
        provider_was_available = selected is not None
        provider_name = selected.name if selected else "Deterministic"
        model = selected.model if selected else ""
        warnings: list[str] = []

        try:
            built = self.prompt_builder.build(request, provider=provider_name, model=model)
        except (TypeError, ValueError) as error:
            raise ValueError(str(error)) from error

        cache_key = _cache_key(request, provider_name, model, built.promptVersion, operation)
        cached = self.cache.get(cache_key)
        if cached is not None:
            cached.setdefault("warnings", []).append("Reasoning result loaded from cache.")
            cached.setdefault("telemetry", {})["cacheHit"] = True
            return cached

        if built.diagnostics.get("blockedByBudgetGuard"):
            warnings.append(
                str(built.diagnostics.get("reason") or "Provider call blocked by prompt budget guard.")
            )
            selected = None

        validation: ResponseValidation | None = None
        retries = 0
        execution_request = replace(
            request,
            options={
                **request.options,
                "_maxOutputTokens": _provider_output_budget(built.diagnostics),
            },
        )
        if selected is not None:
            for attempt in range(2):
                try:
                    response = _invoke(selected, operation, built.prompt, execution_request)
                    validation = self.validator.validate(response, built.evidenceCatalog)
                except Exception as error:
                    validation = ResponseValidation(False, errors=[f"provider_error: {error}"])
                if validation.valid:
                    break
                if attempt == 0:
                    retries = 1

        if selected is None or validation is None or not validation.valid:
            if validation is not None:
                warnings.extend(validation.errors)
                warnings.extend(validation.warnings)
            if selected is None and not provider_was_available:
                warnings.append(
                    "No configured reasoning provider was available; deterministic reasoning used."
                )
            value = _deterministic_result(request, built.evidenceCatalog)
            mode = "Deterministic"
            provider_name = "Deterministic"
            model = ""
            metadata: dict[str, Any] = {}
        else:
            warnings.extend(validation.warnings)
            value = validation.value
            metadata = validation.metadata
            mode = "AI"

        value = self.explainer.complete(
            value,
            context=request.engineeringContext,
            evidence_catalog=built.evidenceCatalog,
        )
        confidence = self.confidence_calculator.calculate(
            value,
            request.engineeringContext,
            built.evidenceCatalog,
        )
        elapsed = int((time.monotonic() - started) * 1000)
        prompt_stored = os.getenv("HEI_REASONING_LOG_PROMPTS") == "1"
        telemetry = ReasoningTelemetry(
            provider=provider_name,
            model=model,
            latencyMs=int(metadata.get("latencyMs") or elapsed),
            promptTokens=int(metadata.get("promptTokens") or estimateTokens(built.prompt)),
            completionTokens=int(metadata.get("completionTokens") or 0),
            estimatedCost=float(metadata.get("estimatedCost") or 0),
            retries=retries,
            workflow=request.workflowType,
            promptVersion=built.promptVersion,
            promptStored=prompt_stored,
        )
        result = ReasoningResult(
            workflowType=request.workflowType,
            recommendation=value.get("recommendation"),
            reasoning=value.get("reasoning") or [],
            alternatives=value.get("alternatives") or [],
            evidence=value.get("evidence") or [],
            risks=value.get("risks") or [],
            tradeOffs=value.get("tradeOffs") or [],
            impact=value.get("impact") or {},
            confidence=confidence,
            reasoningMode=mode,
            promptVersion=built.promptVersion,
            provider=provider_name,
            model=model,
            telemetry=telemetry,
            warnings=_unique(warnings),
            structuredResponse=value,
        ).to_dict()
        result["diagnostics"] = {
            "providerAttempts": attempted,
            "promptBudget": built.diagnostics,
            "evidenceReferences": [item["referenceId"] for item in built.evidenceCatalog],
            "correlationId": request.correlationId,
        }
        telemetry_record = {
            **result["telemetry"],
            "reasoningMode": mode,
            "confidence": confidence,
            "correlationId": request.correlationId,
            "warnings": result["warnings"],
        }
        if prompt_stored:
            telemetry_record["prompt"] = built.prompt
        self.telemetry.record(telemetry_record)
        # A temporary provider, parsing, or budget failure must remain retryable.
        # Cache successful AI output and intentional provider-free deterministic mode only.
        if mode == "AI" or not provider_was_available:
            self.cache.set(cache_key, result)
        return result


def _default_registry() -> ReasoningProviderRegistry:
    return ReasoningProviderRegistry([
        PhiProvider(),
        OpenAIProvider(),
        ClaudeProvider(),
        GeminiProvider(),
        LocalProvider(),
    ])


def _invoke(provider: Any, operation: str, prompt: str, request: ReasoningRequest) -> Any:
    method = getattr(provider, operation, None) or provider.reason
    return method(prompt, request)


def _provider_output_budget(diagnostics: dict[str, Any]) -> int:
    context_limit = int(diagnostics.get("contextLimit") or 0)
    prompt_tokens = int(diagnostics.get("finalPromptTokens") or 0)
    reserved = int(diagnostics.get("reservedOutputTokens") or 0)
    capabilities = diagnostics.get("provider_capabilities") or {}
    provider_limit = int(capabilities.get("max_output_tokens") or reserved or 1)
    remaining = max(1, context_limit - prompt_tokens) if context_limit else provider_limit
    return max(1, min(provider_limit, reserved or provider_limit, remaining))


def _context_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, dict):
            return result
    raise ValueError("Reasoning AI requires a canonical EngineeringContext.")


def _deterministic_result(
    request: ReasoningRequest,
    evidence_catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    context = request.engineeringContext
    requirement = context.get("requirement") or {}
    readiness = context.get("readiness") or {}
    summary = context.get("summary") or {}
    title = (
        requirement.get("title")
        or requirement.get("planningRequirement")
        or request.userRequirement
        or request.workflowType
    )
    status = readiness.get("status") or summary.get("readiness") or "ReadyWithRecommendations"
    evidence = [{
        "referenceId": item["referenceId"],
        "reason": "Selected from canonical Engineering Context.",
    } for item in evidence_catalog[:5]]
    return {
        "recommendation": {
            "title": str(title),
            "status": str(status),
            "action": _deterministic_action(request.workflowType, status),
        },
        "reasoning": [
            "The result uses only facts present in the canonical Engineering Context.",
            f"Workflow readiness is {status}.",
        ],
        "alternatives": [{
            "title": "Review context before continuing",
            "reason": "Choose this when the available evidence is incomplete or stale.",
        }],
        "evidence": evidence,
        "risks": list((context.get("impact") or {}).get("potentialRisks") or []),
        "tradeOffs": [
            "Deterministic mode preserves availability but does not add provider-generated judgment."
        ],
        "impact": dict(context.get("impact") or {}),
        "confidence": readiness.get("confidence") or summary.get("repositoryConfidence") or 50,
    }


def _deterministic_action(workflow: str, status: Any) -> str:
    if "blocked" in str(status).casefold():
        return "Resolve blocking context before continuing."
    return f"Continue {workflow} with human review."


def _cache_key(
    request: ReasoningRequest,
    provider: str,
    model: str,
    prompt_version: str,
    operation: str,
) -> str:
    source = json.dumps({
        "context": request.engineeringContext.get("contextVersion") or request.engineeringContext.get("contextId"),
        "workflow": request.workflowType,
        "requirement": request.userRequirement,
        "provider": provider,
        "model": model,
        "prompt": prompt_version,
        "operation": operation,
    }, sort_keys=True)
    return hashlib.sha256(source.encode()).hexdigest()


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))
