"""Build immutable, provider-free diagnostics for an OptimizedExecutionPrompt."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.token_intelligence.models import stable_hash

from .models import PROMPT_DIAGNOSTICS_VERSION, PromptDiagnostics, PromptFileDiagnostic


class PromptDiagnosticsBuilder:
    version = PROMPT_DIAGNOSTICS_VERSION

    def build(
        self,
        optimized_prompt: dict[str, Any],
        execution_manifest: dict[str, Any],
        execution_package: dict[str, Any] | None,
        model_profile: dict[str, Any] | None,
        estimation_profile: dict[str, Any] | None = None,
    ) -> PromptDiagnostics:
        prompt = deepcopy(optimized_prompt) if isinstance(optimized_prompt, dict) else {}
        manifest = deepcopy(execution_manifest) if isinstance(execution_manifest, dict) else {}
        package = deepcopy(execution_package) if isinstance(execution_package, dict) else {}
        model = deepcopy(model_profile) if isinstance(model_profile, dict) else {}
        estimation = deepcopy(estimation_profile) if isinstance(estimation_profile, dict) else {}
        self._validate(prompt, manifest, package)

        source_versions = manifest.get("sourceVersions") if isinstance(manifest.get("sourceVersions"), dict) else {}
        included = _included_files(prompt)
        excluded = _excluded_files(manifest, package, included, prompt)
        prompt_text = str(prompt.get("prompt") or "")
        system_text = str(prompt.get("systemPrompt") or "")
        combined = "\n".join(part for part in (system_text, prompt_text) if part)
        optimized_tokens = int(prompt.get("estimatedTokens") or 0)
        source_tokens = int((prompt.get("diagnostics") or {}).get("sourcePromptTokens") or optimized_tokens)
        ratio = round(optimized_tokens / source_tokens, 4) if source_tokens else 1.0
        reduction = round((1 - ratio) * 100, 2)
        estimated_cost = _estimate_cost(optimized_tokens, estimation)
        estimated_duration = _estimate_duration(optimized_tokens, estimation)
        warnings = _unique([
            *[str(item) for item in manifest.get("warnings", [])],
            *[str(item) for item in prompt.get("warnings", [])],
            *([] if ratio <= 1 else ["Mode-specific optimization increased prompt size while preserving required engineering context."]),
        ])
        model_summary = {
            "id": str(prompt.get("modelId") or model.get("id") or ""),
            "name": str(model.get("name") or prompt.get("modelId") or ""),
            "provider": str(prompt.get("provider") or model.get("provider") or ""),
            "registryVersion": str(model.get("registryVersion") or ""),
            "contextWindow": int(model.get("contextWindow") or 0),
        }
        core = {
            "diagnosticsVersion": self.version,
            "optimizedPromptId": str(prompt.get("optimizedPromptId") or ""),
            "executionPromptId": str(prompt.get("sourceExecutionPromptId") or ""),
            "executionManifestId": str(manifest.get("manifestId") or ""),
            "executionManifestVersion": str(manifest.get("manifestVersion") or ""),
            "executionPackageId": str(manifest.get("sourcePackageId") or ""),
            "executionPackageVersion": str(source_versions.get("executionPackageVersion") or _package_version(package)),
            "repositorySnapshot": str(source_versions.get("repositorySnapshotVersion") or ""),
            "knowledgeVersion": str(source_versions.get("knowledgeVersion") or ""),
            "memoryVersion": str(source_versions.get("engineeringMemoryVersion") or ""),
            "model": model_summary,
            "promptSize": {
                "characters": len(combined),
                "utf8Bytes": len(combined.encode("utf-8")),
                "lines": len(combined.splitlines()),
            },
            "tokenCount": {
                "estimated": optimized_tokens,
                "actual": None,
                "source": "deterministic_estimate",
                "sourcePromptTokens": source_tokens,
            },
            "optimizationRatio": ratio,
            "optimizationReductionPercent": reduction,
            "confidence": float(prompt.get("promptConfidence") or 0),
            "promptQualityScore": int(prompt.get("promptQualityScore") or 0),
            "warnings": warnings,
            "filesIncluded": included,
            "filesExcluded": excluded,
            "estimatedCost": estimated_cost,
            "estimatedDuration": estimated_duration,
        }
        immutable_hash = stable_hash(core)
        return {
            "diagnosticsId": f"promptdiag_{immutable_hash[:12]}",
            **core,
            "immutable": True,
            "immutableHash": immutable_hash,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "diagnostics": {
                "sourceOptimizedPromptHash": prompt.get("immutableHash"),
                "sourceExecutionManifestHash": manifest.get("immutableHash"),
                "includedFileCount": len(included),
                "excludedFileCount": len(excluded),
                "costEstimateAvailable": estimated_cost["status"] == "Available",
                "durationEstimateAvailable": estimated_duration["status"] == "Available",
                "providerInvoked": False,
                "networkCalls": 0,
                "llmUsed": False,
            },
        }

    @staticmethod
    def _validate(prompt: dict[str, Any], manifest: dict[str, Any], package: dict[str, Any]) -> None:
        if not prompt.get("optimizedPromptId") or prompt.get("immutable") is not True:
            raise ValueError("An immutable OptimizedExecutionPrompt is required.")
        if not manifest.get("manifestId") or manifest.get("immutable") is not True:
            raise ValueError("An immutable Execution Manifest is required.")
        prompt_manifest = str(prompt.get("sourceExecutionManifestId") or "")
        if prompt_manifest and prompt_manifest != str(manifest.get("manifestId") or ""):
            raise ValueError("Optimized prompt and Execution Manifest lineage do not match.")
        package_id = str(package.get("packageId") or (package.get("metadata") or {}).get("packageId") or "")
        if package_id and package_id != str(manifest.get("sourcePackageId") or ""):
            raise ValueError("Execution Package and Execution Manifest lineage do not match.")


def _included_files(prompt: dict[str, Any]) -> list[PromptFileDiagnostic]:
    repository = _section_content(prompt, "repository_context")
    files = repository.get("relevantFiles", []) if isinstance(repository, dict) else []
    return _file_diagnostics(files, source="optimized_prompt", default_reason="Included as ranked repository evidence.")


def _excluded_files(
    manifest: dict[str, Any],
    package: dict[str, Any],
    included: list[PromptFileDiagnostic],
    prompt: dict[str, Any],
) -> list[PromptFileDiagnostic]:
    included_paths = {item["path"].casefold() for item in included}
    removed = _removed_context(prompt)
    result: list[PromptFileDiagnostic] = []
    for raw in manifest.get("relevantFiles", []):
        item = _file_diagnostic(raw, "execution_manifest", "Excluded before final prompt assembly.")
        if not item or item["path"].casefold() in included_paths:
            continue
        item["reason"] = removed.get(stable_hash(raw), item["reason"])
        result.append(item)
    package_diagnostics = package.get("diagnostics") if isinstance(package.get("diagnostics"), dict) else {}
    for field in ("excludedContext", "rejectedContext"):
        for raw in package_diagnostics.get(field, []):
            candidate = raw.get("candidate", raw) if isinstance(raw, dict) else raw
            if not _is_file(candidate):
                continue
            reason = str(raw.get("reason") or "Rejected by execution context selection.") if isinstance(raw, dict) else "Rejected by execution context selection."
            item = _file_diagnostic(candidate, f"execution_package.{field}", reason)
            if item and item["path"].casefold() not in included_paths:
                result.append(item)
    return _unique_files(result)


def _file_diagnostics(values: list[Any], *, source: str, default_reason: str) -> list[PromptFileDiagnostic]:
    result = [item for value in values if (item := _file_diagnostic(value, source, default_reason))]
    return _unique_files(result)


def _file_diagnostic(value: Any, source: str, default_reason: str) -> PromptFileDiagnostic | None:
    if isinstance(value, str):
        path, confidence, reason = value.strip(), None, default_reason
    elif isinstance(value, dict):
        path = str(value.get("path") or value.get("file") or value.get("title") or value.get("name") or "").strip()
        confidence_value = value.get("confidence") if value.get("confidence") is not None else value.get("confidenceScore")
        confidence = float(confidence_value) if confidence_value is not None else None
        reason = str(value.get("reason") or value.get("evidence") or default_reason)
    else:
        return None
    if not path:
        return None
    return {"path": path, "confidence": confidence, "reason": reason, "source": source}


def _unique_files(values: list[PromptFileDiagnostic]) -> list[PromptFileDiagnostic]:
    result: list[PromptFileDiagnostic] = []
    seen: set[str] = set()
    for value in values:
        key = value["path"].casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _section_content(prompt: dict[str, Any], section_id: str) -> Any:
    for section in [*prompt.get("sections", []), *prompt.get("appendix", [])]:
        if isinstance(section, dict) and section.get("id") == section_id:
            return section.get("content")
    return None


def _removed_context(prompt: dict[str, Any]) -> dict[str, str]:
    token_diagnostics = (prompt.get("diagnostics") or {}).get("sourceTokenIntelligence") or {}
    return {
        str(item.get("valueHash") or ""): str(item.get("reason") or "Excluded by Token Intelligence.")
        for item in token_diagnostics.get("removedContext", [])
        if isinstance(item, dict) and item.get("valueHash")
    }


def _is_file(value: Any) -> bool:
    if isinstance(value, str):
        return "/" in value or "." in value.rsplit("/", 1)[-1]
    if not isinstance(value, dict):
        return False
    category = str(value.get("category") or value.get("type") or "").casefold()
    return "file" in category or bool(value.get("path") or value.get("file"))


def _package_version(package: dict[str, Any]) -> str:
    diagnostics = package.get("diagnostics") if isinstance(package.get("diagnostics"), dict) else {}
    return str(diagnostics.get("builderVersion") or package.get("version") or "")


def _estimate_cost(input_tokens: int, profile: dict[str, Any]) -> dict[str, Any]:
    input_rate = profile.get("inputCostPerMillionTokens")
    output_rate = profile.get("outputCostPerMillionTokens")
    expected_output = int(profile.get("expectedOutputTokens") or 0)
    if input_rate is None or output_rate is None:
        return {"status": "Unavailable", "currency": str(profile.get("currency") or "USD"), "amount": None, "reason": "Model pricing is not configured."}
    amount = (input_tokens / 1_000_000 * float(input_rate)) + (expected_output / 1_000_000 * float(output_rate))
    return {
        "status": "Available",
        "currency": str(profile.get("currency") or "USD"),
        "amount": round(amount, 6),
        "inputTokens": input_tokens,
        "expectedOutputTokens": expected_output,
        "reason": "Estimated from the supplied pricing profile; provider billing may differ.",
    }


def _estimate_duration(input_tokens: int, profile: dict[str, Any]) -> dict[str, Any]:
    throughput = profile.get("tokensPerSecond")
    expected_output = int(profile.get("expectedOutputTokens") or 0)
    if throughput is None or float(throughput) <= 0:
        return {"status": "Unavailable", "milliseconds": None, "reason": "Model throughput is not configured."}
    milliseconds = round((input_tokens + expected_output) / float(throughput) * 1000)
    return {
        "status": "Available",
        "milliseconds": milliseconds,
        "tokensPerSecond": float(throughput),
        "reason": "Estimated from the supplied throughput profile; runtime conditions may differ.",
    }


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
