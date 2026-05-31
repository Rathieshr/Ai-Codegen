"""Stage runners for template-driven workflows."""

from __future__ import annotations

from typing import Any, Callable

from backend.assistants import (
    run_app_ui_assistant,
    run_ba_assistant,
    run_critic_assistant,
    run_dev_assistant,
    run_test_assistant,
)
from .child_task_planner import generate_child_task_preview


ApprovedStageGetter = Callable[[str], dict[str, Any]]


def run_stage_output(
    stage: str,
    state: Any,
    approved_stage_context: ApprovedStageGetter,
    review_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    review_context = review_context or {}
    work_item = state.work_item
    refinement = state.refinement
    repo_context = state.repo_context

    if stage == "ba":
        return run_ba_assistant(work_item, refinement, review_context=review_context)
    if stage in {"ui", "ui_optional", "ui_plan"}:
        ba_output = _ba_like_output(work_item, refinement, approved_stage_context("ba"))
        output = run_app_ui_assistant(ba_output, refinement, review_context=review_context)
        output["assistant"] = stage
        return output
    if stage == "ui_handoff":
        source = approved_stage_context("ui_plan") or approved_stage_context("ui_optional")
        return {
            "assistant": stage,
            "summary": source.get("summary") or source.get("user_goal") or "UI handoff is ready for downstream delivery.",
            "layout": source.get("layout", []),
            "fields": source.get("fields", []),
            "states": source.get("states", []),
            "ux_notes": source.get("ux_notes", []),
            "accessibility_notes": source.get("accessibility_notes", []),
            "unknowns": [],
        }
    if stage in {"dev", "dev_packet", "fix_packet"}:
        ba_like = _ba_like_output(work_item, refinement, approved_stage_context("ba") or approved_stage_context("task_analysis") or approved_stage_context("bug_analysis"))
        ui_output = approved_stage_context("ui_optional") or approved_stage_context("ui_plan") or approved_stage_context("ui")
        output = run_dev_assistant(ba_like, ui_output if ui_output else None, repo_context, refinement, review_context=review_context)
        output["assistant"] = stage
        return output
    if stage in {"test", "test_planning", "test_design", "regression_tests", "test_checklist"}:
        ba_like = _ba_like_output(work_item, refinement, approved_stage_context("ba") or approved_stage_context("task_analysis") or approved_stage_context("bug_analysis"))
        dev_output = approved_stage_context("dev_packet") or approved_stage_context("fix_packet") or approved_stage_context("dev") or {
            "flow": _first(ba_like.get("flows", [])),
            "variants": ba_like.get("variants", []),
        }
        ui_output = approved_stage_context("ui_optional") or approved_stage_context("ui_plan") or approved_stage_context("ui")
        output = run_test_assistant(ba_like, dev_output, ui_output if ui_output else None, review_context=review_context)
        output["assistant"] = stage
        if stage == "test_checklist":
            output["summary"] = "Validation checklist is ready for task execution."
        return output
    if stage == "task_planning":
        ba_like = _ba_like_output(work_item, refinement, approved_stage_context("ba"))
        ui_output = approved_stage_context("ui_optional")
        child_tasks = generate_child_task_preview(work_item, ui_output or ba_like, refinement)
        return {
            "assistant": stage,
            "summary": "Proposed child tasks are ready for downstream execution planning.",
            "proposed_child_tasks": child_tasks,
            "acceptance_criteria": ba_like.get("acceptance_criteria", [])[:6],
            "flows": ba_like.get("flows", []),
            "unknowns": [],
        }
    if stage == "epic_analysis":
        return {
            "assistant": stage,
            "summary": _title_or_default(work_item, "Analyze epic scope, dependencies, and risks."),
            "proposed_stories": _story_candidates(work_item, refinement, 4),
            "dependencies": _dependencies(work_item, refinement),
            "risks": _risks(work_item, refinement),
            "unknowns": [],
        }
    if stage == "feature_analysis":
        return {
            "assistant": stage,
            "summary": _title_or_default(work_item, "Analyze feature scope and break it into deliverable stories."),
            "stories": _story_candidates(work_item, refinement, 3),
            "tasks": generate_child_task_preview(work_item, {"summary": _title_or_default(work_item, "")}, refinement),
            "acceptance_criteria": _acceptance_from_work_item(work_item, refinement),
            "unknowns": [],
        }
    if stage == "story_generation":
        analysis = approved_stage_context("epic_analysis") or approved_stage_context("feature_analysis")
        return {
            "assistant": stage,
            "summary": "Generated story candidates for review and task decomposition.",
            "proposed_stories": analysis.get("proposed_stories") or analysis.get("stories") or _story_candidates(work_item, refinement, 3),
            "dependencies": analysis.get("dependencies", []),
            "risks": analysis.get("risks", []),
            "unknowns": [],
        }
    if stage == "review":
        analysis = approved_stage_context("story_generation") or approved_stage_context("feature_analysis") or approved_stage_context("epic_analysis")
        return {
            "assistant": stage,
            "summary": "Review the generated planning artifacts before downstream execution.",
            "checklist": [
                "Confirm dependencies and sequencing.",
                "Review risks and missing assumptions.",
                "Approve the proposed stories or tasks.",
            ],
            "artifacts": analysis.get("proposed_stories") or analysis.get("stories") or [],
            "unknowns": [],
        }
    if stage == "task_analysis":
        return _analysis_like_output(work_item, refinement, "Task analysis is ready for implementation planning.")
    if stage == "bug_analysis":
        output = _analysis_like_output(work_item, refinement, "Bug analysis is ready for fix planning.")
        output["likely_bug_surface"] = refinement.get("refined_surface") or refinement.get("surface")
        return output
    if stage == "impact_analysis":
        analysis = approved_stage_context("bug_analysis")
        return {
            "assistant": stage,
            "summary": "Captured likely impacted areas and regression risk for the bug fix.",
            "impacted_areas": _impacted_areas(analysis, refinement),
            "regression_risks": _risks(work_item, refinement)[:3],
            "unknowns": [],
        }
    if stage == "automation_draft_optional":
        test_design = approved_stage_context("test_design")
        return {
            "assistant": stage,
            "summary": "Automation candidates were identified from the QA task scope.",
            "automation_candidates": [
                case.get("title", "")
                for case in test_design.get("test_cases", [])
                if case.get("type") in {"positive", "regression", "acceptance"}
            ][:4],
            "unknowns": [],
        }
    if stage == "research_plan":
        return {
            "assistant": stage,
            "summary": _title_or_default(work_item, "Research plan is ready."),
            "research_questions": [
                "What is the current behavior or limitation?",
                "What evidence is needed to compare options?",
                "Which dependencies or systems must be inspected first?",
            ],
            "unknowns": [],
        }
    if stage == "findings":
        return {
            "assistant": stage,
            "summary": "Research findings were captured for the spike.",
            "findings": [
                "Document the current implementation path.",
                "Capture constraints and tradeoffs discovered during investigation.",
                "List open questions that affect the final recommendation.",
            ],
            "unknowns": [],
        }
    if stage == "recommendation":
        return {
            "assistant": stage,
            "summary": "Recommendation is ready for stakeholder review.",
            "recommendation": "Proceed with the lowest-risk approach that satisfies the researched constraints.",
            "next_steps": [
                "Review the findings with the team.",
                "Choose the recommended path or request follow-up research.",
            ],
            "unknowns": [],
        }
    raise ValueError(f"Unknown stage: {stage}")


def run_stage_critic(stage: str, output: dict[str, Any], state: Any, approved_stage_context: ApprovedStageGetter) -> dict[str, Any]:
    if stage == "ba":
        return run_critic_assistant(ba_output=output)
    if stage in {"ui", "ui_optional", "ui_plan"}:
        return run_critic_assistant(ba_output=_ba_like_output(state.work_item, state.refinement, approved_stage_context("ba")), ui_output=output)
    if stage in {"dev", "dev_packet", "fix_packet"}:
        return run_critic_assistant(
            ba_output=_ba_like_output(state.work_item, state.refinement, approved_stage_context("ba") or approved_stage_context("task_analysis") or approved_stage_context("bug_analysis")),
            ui_output=approved_stage_context("ui_optional") or approved_stage_context("ui_plan") or None,
            dev_output=output,
        )
    if stage in {"test", "test_planning", "test_design", "regression_tests", "test_checklist"}:
        return run_critic_assistant(
            ba_output=_ba_like_output(state.work_item, state.refinement, approved_stage_context("ba") or approved_stage_context("task_analysis") or approved_stage_context("bug_analysis")),
            ui_output=approved_stage_context("ui_optional") or approved_stage_context("ui_plan") or None,
            dev_output=approved_stage_context("dev_packet") or approved_stage_context("fix_packet") or approved_stage_context("dev") or None,
            test_output=output,
        )
    findings: list[dict[str, Any]] = []
    if output.get("unknowns"):
        findings.append(_finding("ambiguity", "warning", f"{stage} still has open questions.", stage))
    if stage == "story_generation" and not output.get("proposed_stories"):
        findings.append(_finding("weak_scope", "warning", "Story generation did not produce any stories.", stage))
    if stage == "task_planning" and not output.get("proposed_child_tasks"):
        findings.append(_finding("weak_scope", "warning", "Task planning did not produce child tasks.", stage))
    if stage == "review" and not output.get("artifacts"):
        findings.append(_finding("weak_scope", "warning", "Review stage has no planning artifacts to inspect.", stage))
    has_blocking = any(item["severity"] == "blocking" for item in findings)
    return {
        "assistant": "critic",
        "overall_risk": "high" if has_blocking else ("medium" if findings else "low"),
        "findings": findings,
        "recommended_changes": _recommended_changes(findings),
        "decision": "needs_revision" if has_blocking else "approve_candidate",
        "react": {
            "reason": {
                "known": [stage],
                "missing": [finding["message"] for finding in findings[:4]],
                "goal": "Check the template stage output for missing or inconsistent planning artifacts.",
            },
            "act": {"finding_count": len(findings)},
            "observe": {"overall_risk": "high" if has_blocking else ("medium" if findings else "low")},
            "decision": "needs_revision" if has_blocking else "ready_for_approval",
        },
    }


def _analysis_like_output(work_item: dict[str, Any], refinement: dict[str, Any], summary: str) -> dict[str, Any]:
    title = _title_or_default(work_item, summary)
    flows = _dedupe(list(refinement.get("refined_base_flows", [])) + list(refinement.get("base_flows", [])))
    variants = _dedupe(list(refinement.get("refined_variants", [])) + list(refinement.get("variants", [])))
    return {
        "assistant": "analysis",
        "refined_requirement": title,
        "summary": summary,
        "actors": ["end_user"],
        "flows": flows or ["workflow"],
        "variants": variants,
        "business_rules": _business_rules(refinement),
        "acceptance_criteria": _acceptance_from_work_item(work_item, refinement),
        "unknowns": [],
    }


def _ba_like_output(work_item: dict[str, Any], refinement: dict[str, Any], source: dict[str, Any] | None) -> dict[str, Any]:
    if source:
        return source
    output = _analysis_like_output(work_item, refinement, _title_or_default(work_item, "Requirement is ready for delivery planning."))
    output["assistant"] = "ba"
    return output


def _title_or_default(work_item: dict[str, Any], fallback: str) -> str:
    title = str(work_item.get("title", "")).strip()
    if title:
        return f"{title}."
    return fallback


def _acceptance_from_work_item(work_item: dict[str, Any], refinement: dict[str, Any]) -> list[str]:
    acceptance = str(work_item.get("acceptanceCriteria") or work_item.get("acceptance_criteria") or "").strip()
    if acceptance:
        return [line.strip() for line in acceptance.splitlines() if line.strip()][:6]
    fields = [str(item).strip() for item in refinement.get("refined_fields", []) or refinement.get("fields", []) if str(item).strip()]
    if fields:
        return [f"Support the required fields: {', '.join(fields[:4])}."]
    return ["Capture the approved behavior in implementation-ready acceptance criteria."]


def _story_candidates(work_item: dict[str, Any], refinement: dict[str, Any], max_items: int) -> list[str]:
    title = str(work_item.get("title", "")).strip() or "Work item"
    flows = _dedupe(list(refinement.get("refined_base_flows", [])) + list(refinement.get("base_flows", []))) or ["workflow"]
    candidates = [f"Deliver {title} for {flow} flow." for flow in flows[:max_items]]
    if len(candidates) < max_items:
        candidates.append(f"Validate {title} through QA coverage.")
    return candidates[:max_items]


def _dependencies(work_item: dict[str, Any], refinement: dict[str, Any]) -> list[str]:
    flows = _dedupe(list(refinement.get("refined_base_flows", [])) + list(refinement.get("base_flows", [])))
    dependencies = [f"Coordinate with {flow} related workflow changes." for flow in flows if flow not in {"workflow"}]
    return dependencies[:3]


def _risks(work_item: dict[str, Any], refinement: dict[str, Any]) -> list[str]:
    text = " ".join(str(value).lower() for value in [work_item.get("title", ""), work_item.get("description", "")])
    risks = []
    if "auth" in text or "login" in text:
        risks.append("Authentication changes may affect session or token handling.")
    if "payment" in text:
        risks.append("Payment changes require extra validation before release.")
    if not risks:
        risks.append("Scope and dependency assumptions should be reviewed before execution.")
    return risks


def _impacted_areas(analysis: dict[str, Any], refinement: dict[str, Any]) -> list[str]:
    impacted = _dedupe(list(analysis.get("flows", [])) + list(refinement.get("refined_surfaces", [])) + list(refinement.get("surfaces", [])))
    return impacted[:4] or ["implementation", "validation"]


def _business_rules(refinement: dict[str, Any]) -> list[str]:
    validations = [str(item).strip() for item in refinement.get("refined_validations", []) or refinement.get("validations", []) if str(item).strip()]
    rules = [f"Preserve validation rules for {item}." for item in validations[:3]]
    if not rules:
        rules.append("Preserve the approved workflow and safety rules.")
    return rules


def _recommended_changes(findings: list[dict[str, Any]]) -> list[str]:
    if not findings:
        return []
    return [finding["message"] for finding in findings[:4]]


def _finding(finding_type: str, severity: str, message: str, target_stage: str) -> dict[str, Any]:
    normalized = "".join(character if character.isalnum() else "_" for character in f"{target_stage}_{finding_type}_{message}".lower())
    normalized = "_".join(part for part in normalized.split("_") if part)
    return {
        "id": f"finding_{normalized[:80]}",
        "type": finding_type,
        "severity": severity,
        "message": message,
        "target_stage": target_stage,
        "source_stage": target_stage,
        "status": "open",
    }


def _first(values: list[str]) -> str:
    for value in values:
        normalized = str(value).strip()
        if normalized:
            return normalized
    return ""


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in output:
            output.append(normalized)
    return output
