"""Shared deterministic rendering for model-specific prompt adapters."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.token_intelligence.models import estimate_tokens, stable_hash

from .models import MODEL_ADAPTER_VERSION, AdaptedPromptSection, ExecutionPrompt


class BaseModelAdapter:
    model_id = ""
    prompt_version = MODEL_ADAPTER_VERSION
    wording_profile = "standard"
    system_role = "You are a senior software engineer working inside the existing codebase."
    preamble = "Implement the approved engineering objective using only the supplied context."
    section_order = (
        "business_objective",
        "repository_context",
        "implementation_guidance",
        "validation",
        "qa",
        "constraints",
        "instructions",
    )
    title_overrides: dict[str, str] = {}

    def compile(self, budgeted_prompt: dict[str, Any], model_profile: dict[str, Any]) -> ExecutionPrompt:
        budgeted = deepcopy(budgeted_prompt) if isinstance(budgeted_prompt, dict) else {}
        profile = deepcopy(model_profile) if isinstance(model_profile, dict) else {}
        self._validate(budgeted, profile)
        sections = self._adapt_sections(budgeted.get("sections") or [])
        system_prompt = self.system_role if profile.get("systemPromptSupport") else None
        model_instructions = self._capability_instructions(profile)
        prompt = self._render_prompt(
            sections,
            model_instructions=model_instructions,
            include_role=not bool(system_prompt),
        )
        estimated = estimate_tokens({"systemPrompt": system_prompt or "", "prompt": prompt})
        context_window = int(profile.get("contextWindow") or 0)
        requested_reserve = int(budgeted.get("reservedOutputTokens") or 0)
        max_output = int(profile.get("maxOutput") or 0)
        effective_output_reserve = min(requested_reserve, max_output)
        profile_input_limit = max(0, context_window - effective_output_reserve)
        budget_input_limit = int(budgeted.get("inputBudgetTokens") or 0)
        max_input = min(profile_input_limit, budget_input_limit)
        budget_compatible = int(budgeted.get("requestedBudgetTokens") or 0) <= context_window
        fits = budgeted.get("status") == "Ready" and budget_compatible and estimated <= max_input
        warnings = list(dict.fromkeys([
            *[str(item) for item in budgeted.get("warnings", []) if str(item)],
            *(self._capability_warnings(profile, requested_reserve, max_output)),
            *([] if budget_compatible else ["The BudgetedPrompt context budget exceeds this model profile's context window."]),
            *([] if estimated <= max_input else ["The rendered ExecutionPrompt exceeds this model profile's available input budget. Rerun Token Intelligence with a smaller supported budget."]),
            *([] if budgeted.get("status") == "Ready" else ["Token Intelligence blocked the source BudgetedPrompt."]),
        ]))
        core = {
            "promptVersion": f"{self.model_id}-{self.prompt_version}",
            "modelId": self.model_id,
            "provider": str(profile.get("provider") or ""),
            "sourceBudgetedPromptId": str(budgeted.get("budgetedPromptId") or ""),
            "sourceCompiledPromptId": str(budgeted.get("compiledPromptId") or ""),
            "sourceExecutionManifestId": str(budgeted.get("executionManifestId") or ""),
            "systemPrompt": system_prompt,
            "adapterObjective": self.preamble,
            "modelInstructions": model_instructions,
            "prompt": prompt,
            "sections": sections,
            "estimatedTokens": estimated,
            "maxInputTokens": max_input,
            "status": "Ready" if fits else "Blocked",
            "warnings": warnings,
        }
        immutable_hash = stable_hash(core)
        return {
            "executionPromptId": f"executionprompt_{self.model_id}_{immutable_hash[:12]}",
            **core,
            "immutable": True,
            "immutableHash": immutable_hash,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "diagnostics": {
                "adapter": type(self).__name__,
                "adapterVersion": self.prompt_version,
                "wordingProfile": self.wording_profile,
                "modelProfileVersion": profile.get("registryVersion"),
                "sectionOrder": [section["id"] for section in sections],
                "sectionTokens": {section["id"]: estimate_tokens(section["rendered"]) for section in sections},
                "estimatedTokens": estimated,
                "contextWindow": context_window,
                "requestedBudgetTokens": budgeted.get("requestedBudgetTokens"),
                "reservedOutputTokens": requested_reserve,
                "effectiveOutputReserveTokens": effective_output_reserve,
                "maxOutputTokens": max_output,
                "maxInputTokens": max_input,
                "remainingInputTokens": max_input - estimated,
                "capabilities": {
                    "reasoning": bool(profile.get("reasoning")),
                    "tools": bool(profile.get("toolSupport")),
                    "vision": bool(profile.get("vision")),
                    "streaming": bool(profile.get("streaming")),
                    "temperature": bool(profile.get("temperatureSupport")),
                    "json": bool(profile.get("jsonSupport")),
                    "systemPrompt": bool(profile.get("systemPromptSupport")),
                },
                "contextLimitRespected": fits,
                "sourceTokenIntelligence": deepcopy(budgeted.get("diagnostics") or {}),
                "modelAdaptationApplied": True,
                "providerInvoked": False,
                "networkCalls": 0,
                "llmUsed": False,
            },
        }

    def _adapt_sections(self, raw_sections: list[Any]) -> list[AdaptedPromptSection]:
        by_id = {
            str(section.get("id") or ""): deepcopy(section)
            for section in raw_sections
            if isinstance(section, dict) and section.get("id")
        }
        result: list[AdaptedPromptSection] = []
        for index, section_id in enumerate(self.section_order, start=1):
            section = by_id.get(section_id)
            if not section:
                continue
            title = self.title_overrides.get(section_id) or str(section.get("title") or section_id.replace("_", " ").title())
            content = deepcopy(section.get("content"))
            result.append({"id": section_id, "order": index, "title": title, "content": content, "rendered": render_prompt_content(content)})
        return result

    def _render_prompt(
        self,
        sections: list[AdaptedPromptSection],
        *,
        model_instructions: list[str],
        include_role: bool,
    ) -> str:
        blocks = ["# Execution Prompt"]
        if include_role:
            blocks.extend(["## Role", self.system_role])
        blocks.extend(["## Objective", self.preamble])
        for section in sections:
            if section["rendered"]:
                blocks.extend([f"## {section['title']}", section["rendered"]])
        if model_instructions:
            blocks.extend(["## Model-Specific Instructions", *[f"- {item}" for item in model_instructions]])
        return "\n\n".join(block for block in blocks if block).strip() + "\n"

    def _capability_instructions(self, profile: dict[str, Any]) -> list[str]:
        instructions: list[str] = []
        if profile.get("reasoning"):
            instructions.append("Reason through dependencies and validation before editing, but keep the final response concise.")
        if profile.get("toolSupport"):
            instructions.append("Use repository tools only to verify the supplied evidence and locate the closest existing implementation.")
        if not profile.get("jsonSupport"):
            instructions.append("Return a concise human-readable implementation summary; structured JSON output is not required.")
        return instructions

    @staticmethod
    def _capability_warnings(profile: dict[str, Any], requested_reserve: int, max_output: int) -> list[str]:
        if requested_reserve > max_output:
            return ["The requested output reserve exceeds the model profile maximum and was capped for context validation."]
        return []

    def _validate(self, budgeted: dict[str, Any], profile: dict[str, Any]) -> None:
        if not budgeted.get("budgetedPromptId") or budgeted.get("immutable") is not True:
            raise ValueError("An immutable BudgetedPrompt is required.")
        if str(profile.get("id") or "").casefold() != self.model_id:
            raise ValueError(f"Model profile {profile.get('id') or '<missing>'} does not match adapter {self.model_id}.")


def render_prompt_content(value: Any, depth: int = 0) -> str:
    if value in (None, "", [], {}):
        return ""
    indent = "  " * depth
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            label = _label(str(key))
            if isinstance(item, (dict, list)):
                rendered = render_prompt_content(item, depth + 1)
                if rendered:
                    lines.append(f"{indent}- **{label}:**")
                    lines.append(rendered)
            else:
                lines.append(f"{indent}- **{label}:** {item}")
        return "\n".join(lines)
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                rendered = render_prompt_content(item, depth + 1)
                if rendered:
                    child_lines = rendered.splitlines()
                    first = child_lines[0].strip()
                    if first.startswith("- "):
                        first = first[2:]
                    lines.append(f"{indent}- {first}")
                    lines.extend(child_lines[1:])
            else:
                lines.append(f"{indent}- {item}")
        return "\n".join(lines)
    return f"{indent}{value}"


def _label(value: str) -> str:
    result = []
    for index, character in enumerate(value.replace("_", " ")):
        if index and character.isupper() and value[index - 1].islower():
            result.append(" ")
        result.append(character)
    words = " ".join("".join(result).split()).strip().title().split()
    acronyms = {"Api": "API", "Apis": "APIs", "Id": "ID", "Ids": "IDs", "Json": "JSON", "Qa": "QA", "Ui": "UI"}
    return " ".join(acronyms.get(word, word) for word in words)
