"""Deterministic Execution Manifest to CompiledPrompt compiler.

This stage performs sectioning and normalization only. It does not estimate or
optimize tokens, select a model, adapt provider syntax, format a final prompt,
or call an LLM.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Protocol

from .models import (
    COMPILER_VERSION,
    SECTION_ORDER,
    CompiledPrompt,
    CompiledPromptSection,
    clean,
    mapping,
    now_iso,
    sequence,
    stable_hash,
)


class IPromptCompiler(Protocol):
    def compile(self, execution_manifest: dict[str, Any]) -> CompiledPrompt: ...


class PromptCompiler:
    version = COMPILER_VERSION

    def compile(self, execution_manifest: dict[str, Any]) -> CompiledPrompt:
        manifest = mapping(execution_manifest)
        manifest_id = clean(manifest.get("manifestId"))
        if not manifest_id or manifest.get("immutable") is not True:
            raise ValueError("An immutable Execution Manifest is required.")

        duplicate_values_removed = _duplicate_count(manifest)
        repository, repository_warnings = _repository_section(manifest)
        sections: list[CompiledPromptSection] = [
            _section(
                "business_objective",
                "Business Objective",
                {
                    "objective": clean(manifest.get("objective")),
                    "businessGoal": clean(manifest.get("businessGoal")),
                    "confidence": manifest.get("confidence"),
                },
                ["objective", "businessGoal", "confidence"],
            ),
            _section(
                "repository_context",
                "Repository Context",
                repository,
                ["repositoryContext", "relevantFiles"],
            ),
            _section(
                "implementation_guidance",
                "Implementation Guidance",
                _implementation_section(manifest),
                ["implementationGuidance"],
            ),
            _section(
                "validation",
                "Validation",
                {
                    "acceptanceCriteria": _normalize(manifest.get("acceptanceCriteria")),
                    "guidance": _validation_section(manifest),
                },
                ["acceptanceCriteria", "validationGuidance"],
            ),
            _section(
                "qa",
                "QA",
                _normalize(manifest.get("qaGuidance")),
                ["qaGuidance"],
            ),
            _section(
                "constraints",
                "Constraints",
                _constraints_section(manifest),
                ["dependencies", "engineeringStandards", "risks", "warnings"],
            ),
            _section(
                "instructions",
                "Instructions",
                _instructions(manifest, repository),
                ["objective", "acceptanceCriteria", "repositoryContext", "implementationGuidance"],
            ),
        ]
        core = {
            "compilerVersion": self.version,
            "executionManifestId": manifest_id,
            "sourcePackageId": clean(manifest.get("sourcePackageId")),
            "sections": sections,
            "warnings": _unique_strings([*sequence(manifest.get("warnings")), *repository_warnings]),
        }
        immutable_hash = stable_hash(core)
        return {
            "compiledPromptId": f"compiledprompt_{immutable_hash[:12]}",
            **core,
            "immutable": True,
            "immutableHash": immutable_hash,
            "compiledAt": now_iso(),
            "diagnostics": {
                "compilerVersion": self.version,
                "sectionOrder": list(SECTION_ORDER),
                "sectionCount": len(sections),
                "duplicateValuesRemoved": duplicate_values_removed,
                "repositoryMode": repository["repositoryMode"],
                "repositoryEvidenceAvailable": repository["evidenceAvailable"],
                "tokenOptimizationApplied": False,
                "modelAdaptationApplied": False,
                "providerSelected": False,
                "promptFormattingApplied": False,
                "llmUsed": False,
            },
        }


def _section(section_id: str, title: str, content: Any, source_fields: list[str]) -> CompiledPromptSection:
    normalized = _normalize(content)
    if section_id == "repository_context" and isinstance(normalized, dict):
        for field in ("relevantFiles", "relevantModules", "relevantFlows", "relevantAPIs", "relevantServices", "graphReferences"):
            normalized.setdefault(field, [])
    return {
        "id": section_id,
        "order": SECTION_ORDER.index(section_id) + 1,
        "title": title,
        "content": normalized,
        "sourceFields": source_fields,
    }


def _repository_section(manifest: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    source = mapping(manifest.get("repositoryContext"))
    mode = _repository_mode(source.get("repositoryMode"))
    warnings: list[str] = []
    files = sequence(manifest.get("relevantFiles")) or sequence(source.get("relevantFiles"))
    apis = sequence(source.get("relevantAPIs"))
    services = sequence(source.get("relevantServices"))
    modules = sequence(source.get("relevantModules"))
    flows = sequence(source.get("relevantFlows"))

    if mode == "KnowledgeSnapshot":
        files, apis, services = [], [], []
        warnings.append("Repository is using Knowledge Snapshot; code-level file, API, and service evidence is unavailable.")
    elif mode == "Unavailable":
        files, apis, services, modules, flows = [], [], [], [], []
        warnings.append("Repository context is unavailable.")
    elif mode == "CodeIndexed" and not files:
        warnings.append("Repository is code indexed, but no relevant files were ranked for this manifest.")

    return {
        "repositoryMode": mode,
        "snapshot": source.get("snapshot") or mapping(manifest.get("sourceVersions")).get("repositorySnapshotVersion"),
        "evidenceAvailable": mode == "CodeIndexed" and bool(files or apis or services),
        "relevantFiles": files,
        "relevantModules": modules,
        "relevantFlows": flows,
        "relevantAPIs": apis,
        "relevantServices": services,
        "graphReferences": sequence(source.get("engineeringGraphReferences")),
    }, warnings


def _implementation_section(manifest: dict[str, Any]) -> dict[str, Any]:
    guidance = mapping(manifest.get("implementationGuidance"))
    for field in ("blockedModules", "blockedFlows", "constraints"):
        guidance.pop(field, None)
    return _normalize(guidance)


def _repository_mode(value: Any) -> str:
    key = clean(value).replace("_", "").replace("-", "").replace(" ", "").casefold()
    if key == "codeindexed":
        return "CodeIndexed"
    if key == "knowledgesnapshot":
        return "KnowledgeSnapshot"
    return "Unavailable"


def _validation_section(manifest: dict[str, Any]) -> dict[str, Any]:
    guidance = mapping(manifest.get("validationGuidance"))
    for field in ("acceptanceMapping", "architectureConstraints", "permissionRequirements", "riskAreas"):
        guidance.pop(field, None)
    return _normalize(guidance)


def _constraints_section(manifest: dict[str, Any]) -> dict[str, Any]:
    implementation = mapping(manifest.get("implementationGuidance"))
    validation = mapping(manifest.get("validationGuidance"))
    return {
        "dependencies": _unique_values(sequence(manifest.get("dependencies"))),
        "engineeringStandards": _unique_values(sequence(manifest.get("engineeringStandards"))),
        "blockedModules": _unique_values(sequence(implementation.get("blockedModules"))),
        "blockedFlows": _unique_values(sequence(implementation.get("blockedFlows"))),
        "architectureConstraints": _unique_values(sequence(validation.get("architectureConstraints"))),
        "permissionRequirements": _unique_values(sequence(validation.get("permissionRequirements"))),
        "risks": _unique_values(sequence(manifest.get("risks"))),
        "warnings": _unique_strings(sequence(manifest.get("warnings"))),
    }


def _instructions(manifest: dict[str, Any], repository: dict[str, Any]) -> list[str]:
    values = [
        "Implement only the approved objective and implementation boundary.",
        "Map implementation and verification work to every acceptance criterion.",
        "Apply the engineering standards and validation guidance carried by this manifest.",
        "Add the QA coverage required by the manifest before completion.",
    ]
    if repository["repositoryMode"] == "CodeIndexed" and repository["evidenceAvailable"]:
        values.insert(1, "Use only the repository evidence selected in this compiled prompt.")
    else:
        values.insert(1, "Do not invent repository files, APIs, services, or code evidence.")
    if mapping(manifest.get("implementationGuidance")).get("blockedModules"):
        values.append("Do not modify blocked modules or flows.")
    return values


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key in sorted(value):
            normalized = _normalize(value[key])
            if normalized not in (None, "", [], {}):
                result[str(key)] = normalized
        return result
    if isinstance(value, (list, tuple, set)):
        return _unique_values(list(value))
    if isinstance(value, str):
        return clean(value)
    return deepcopy(value)


def _unique_values(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize(value)
        if normalized in (None, "", [], {}):
            continue
        key = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).casefold()
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def _unique_strings(values: list[Any]) -> list[str]:
    return [str(value) for value in _unique_values([clean(value) for value in values])]


def _duplicate_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_duplicate_count(item) for item in value.values())
    if isinstance(value, list):
        raw = [json.dumps(_normalize(item), sort_keys=True, default=str).casefold() for item in value]
        return max(0, len(raw) - len(set(raw)))
    return 0
