"""Stage runners for template-driven workflows."""

from __future__ import annotations

from typing import Any, Callable

from backend.assistants import (
    run_app_ui_assistant,
    run_ba_assistant,
    run_bug_assistant,
    run_critic_assistant,
    run_dev_assistant,
    run_test_assistant,
)
from .child_task_planner import generate_child_task_preview
from .work_item_drafts import (
    build_child_task_drafts_for_story,
    build_story_drafts_from_epic_or_feature,
)


ApprovedStageGetter = Callable[[str], dict[str, Any]]


def run_stage_output(
    stage: str,
    state: Any,
    approved_stage_context: ApprovedStageGetter,
    effective_context: dict[str, Any] | None = None,
    review_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    review_context = review_context or {}
    work_item = _contextual_work_item(state.work_item, effective_context)
    refinement = state.refinement
    repo_context = state.repo_context

    if stage == "ba":
        # Route Bug work items directly to the bug assistant (C)
        work_item_type = str(work_item.get("type") or "").strip().lower()
        if work_item_type == "bug":
            critic_findings = [
                finding
                for stage_name in (state.stages or {})
                for finding in ((state.stages[stage_name].critic or {}).get("findings") or [])
                if finding.get("severity") in {"blocking", "high"}
            ] if hasattr(state, "stages") else []
            return run_bug_assistant(
                work_item=work_item,
                critic_findings=critic_findings,
                review_context=review_context,
                effective_context=effective_context,
                question_answers=_question_answers_from_context(effective_context),
            )
        return run_ba_assistant(work_item, refinement, review_context=review_context, effective_context=effective_context)
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
        proposed_work_items = build_child_task_drafts_for_story(
            work_item,
            source_stage=stage,
            title_seed=str(ba_like.get("refined_requirement") or work_item.get("title") or "Story Delivery"),
            include_ui=bool(ui_output or _needs_ui(refinement)),
            fields=_field_names(ui_output) or list(refinement.get("fields", [])) or list(refinement.get("refined_fields", [])),
            variants=list(ba_like.get("variants", [])) or list(refinement.get("variants", [])),
        )
        return {
            "assistant": stage,
            "summary": "Generated proposed child work items from the approved story scope.",
            "proposed_child_tasks": child_tasks,
            "proposed_work_items": proposed_work_items,
            "generated_work_items": proposed_work_items,
            "acceptance_criteria": ba_like.get("acceptance_criteria", [])[:6],
            "flows": ba_like.get("flows", []),
            "unknowns": [],
        }
    if stage == "epic_analysis":
        goal = str(work_item.get("title") or "Epic goal").strip()
        description = str(work_item.get("description") or "").strip()
        return {
            "assistant": stage,
            "summary": "Epic analysis completed.",
            "goal": goal,
            "scope": [item for item in [goal, description] if item][:3],
            "business_outcomes": _business_outcomes(work_item, refinement, effective_context),
            "assumptions": _epic_assumptions(work_item, refinement, effective_context),
            "dependencies": _dependencies(work_item, refinement),
            "risks": _risks(work_item, refinement),
            "dependency_notes": _dependencies(work_item, refinement),
            "unknowns": [],
        }
    if stage == "feature_analysis":
        return {
            "assistant": stage,
            "summary": _title_or_default(work_item, "Analyze feature scope and break it into deliverable stories."),
            "acceptance_criteria": _acceptance_from_work_item(work_item, refinement),
            "unknowns": [],
        }
    if stage == "feature_generation":
        proposed_features = _feature_candidates(work_item, refinement)
        return {
            "assistant": stage,
            "summary": "Generated proposed features from the approved epic scope.",
            "proposed_features": proposed_features,
            "generated_features": proposed_features,
            "dependencies": _dependencies(work_item, refinement),
            "risks": _risks(work_item, refinement),
            "unknowns": [],
        }
    if stage == "story_generation":
        analysis = approved_stage_context("feature_generation") or approved_stage_context("epic_analysis") or approved_stage_context("feature_analysis")
        flows = list(refinement.get("base_flows", [])) or list(refinement.get("refined_base_flows", []))
        variants = list(refinement.get("variants", [])) or list(refinement.get("refined_variants", []))
        fields = list(refinement.get("fields", [])) or list(refinement.get("refined_fields", []))
        proposed_work_items = build_story_drafts_from_epic_or_feature(
            work_item,
            source_stage=stage,
            flows=flows,
            variants=variants,
            fields=fields,
            include_ui=_needs_ui(refinement),
            count=4 if approved_stage_context("epic_analysis") else 3,
            feature_seeds=list(analysis.get("proposed_features", [])),
        )
        return {
            "assistant": "story_generator",
            "summary": "Generated proposed work items from the approved planning scope.",
            "proposed_work_items": proposed_work_items,
            "generated_work_items": proposed_work_items,
            "dependencies": analysis.get("dependencies", []),
            "risks": analysis.get("risks", []),
            "unknowns": [],
        }
    if stage == "review":
        analysis = approved_stage_context("story_generation") or approved_stage_context("feature_generation") or approved_stage_context("feature_analysis") or approved_stage_context("epic_analysis")
        drafts = list(analysis.get("generated_work_items") or analysis.get("proposed_work_items", []))
        review_findings = _review_proposed_work_items(drafts)
        return {
            "assistant": stage,
            "summary": "Review the proposed work items before creating them in Azure DevOps.",
            "proposed_work_items": drafts,
            "generated_work_items": drafts,
            "missing_acceptance_criteria": review_findings["missing_acceptance_criteria"],
            "duplicate_titles": review_findings["duplicate_titles"],
            "ownership_gaps": review_findings["ownership_gaps"],
            "dependency_issues": review_findings["dependency_issues"],
            "approval_recommendation": "approve" if not any(review_findings.values()) else "revise",
            "unknowns": [],
        }
    if stage == "task_analysis":
        return _analysis_like_output(work_item, refinement, "Task analysis is ready for implementation planning.", effective_context=effective_context)
    if stage == "bug_analysis":
        output = _analysis_like_output(work_item, refinement, "Bug analysis is ready for fix planning.", effective_context=effective_context)
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
    if stage == "feature_generation" and not output.get("proposed_features"):
        findings.append(_finding("weak_scope", "warning", "Feature generation did not produce proposed features.", stage))
    if stage == "story_generation" and not output.get("proposed_work_items"):
        findings.append(_finding("weak_scope", "warning", "Story generation did not produce proposed work items.", stage))
    if stage == "task_planning" and not output.get("proposed_work_items"):
        findings.append(_finding("weak_scope", "warning", "Task planning did not produce child work items.", stage))
    if stage == "review":
        if not output.get("proposed_work_items"):
            findings.append(_finding("weak_scope", "warning", "Review stage has no proposed work items to inspect.", stage))
        if output.get("missing_acceptance_criteria"):
            findings.append(_finding("missing_acceptance_criteria", "warning", "Some proposed work items are missing acceptance criteria.", stage))
        if output.get("duplicate_titles"):
            findings.append(_finding("duplicate_work_items", "warning", "Duplicate proposed work item titles were detected.", stage))
        if output.get("ownership_gaps"):
            findings.append(_finding("ownership_gap", "warning", "Some proposed tasks do not make ownership clear.", stage))
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


def _analysis_like_output(
    work_item: dict[str, Any],
    refinement: dict[str, Any],
    summary: str,
    effective_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        "acceptance_criteria": _acceptance_from_work_item(work_item, refinement, effective_context=effective_context),
        "unknowns": [],
    }


def _field_names(ui_output: dict[str, Any] | None) -> list[str]:
    if not ui_output:
        return []
    items = ui_output.get("fields", [])
    if not isinstance(items, list):
        return []
    return [str(field.get("name", "")).strip() for field in items if isinstance(field, dict) and str(field.get("name", "")).strip()]


def _needs_ui(refinement: dict[str, Any]) -> bool:
    surfaces = {str(item).strip().lower() for item in list(refinement.get("surfaces", [])) + list(refinement.get("refined_surfaces", [])) if str(item).strip()}
    return "ui_screen" in surfaces or "ui_validation" in surfaces or "ui_state" in surfaces


def _review_proposed_work_items(drafts: list[dict[str, Any]]) -> dict[str, list[str]]:
    missing_acceptance: list[str] = []
    duplicate_titles: list[str] = []
    ownership_gaps: list[str] = []
    dependency_issues: list[str] = []
    seen_titles: set[str] = set()
    for draft in drafts:
        title = str(draft.get("title", "")).strip()
        if title.lower() in seen_titles:
            duplicate_titles.append(title)
        elif title:
            seen_titles.add(title.lower())
        if not draft.get("acceptance_criteria"):
            missing_acceptance.append(title or str(draft.get("draft_id", "")))
        if draft.get("draft_type") == "Task" and not any(keyword in title.lower() for keyword in ["ui:", "dev:", "qa:", "doc"]):
            ownership_gaps.append(title or str(draft.get("draft_id", "")))
        if draft.get("parent_draft_id") and not any(item.get("draft_id") == draft.get("parent_draft_id") for item in drafts):
            dependency_issues.append(title or str(draft.get("draft_id", "")))
    return {
        "missing_acceptance_criteria": missing_acceptance,
        "duplicate_titles": duplicate_titles,
        "ownership_gaps": ownership_gaps,
        "dependency_issues": dependency_issues,
    }


def _business_outcomes(work_item: dict[str, Any], refinement: dict[str, Any], effective_context: dict[str, Any] | None) -> list[str]:
    outputs: list[str] = []
    title = str(work_item.get("title") or "").strip()
    description = str(work_item.get("description") or "").strip()
    if title:
        outputs.append(f"Break down {title.lower()} into implementation-ready features and stories.")
    if any(flow in (refinement or {}).get("base_flows", []) for flow in ("payment", "checkout", "login", "signup")):
        outputs.append("Preserve the core user journey while decomposing delivery scope.")
    if description:
        outputs.append(description[:180])
    return outputs[:3]


def _epic_assumptions(work_item: dict[str, Any], refinement: dict[str, Any], effective_context: dict[str, Any] | None) -> list[str]:
    assumptions: list[str] = []
    if str(work_item.get("areaPath") or work_item.get("area_path") or "").strip():
        assumptions.append("Area path and current team boundaries should remain stable during breakdown.")
    if (refinement or {}).get("surfaces"):
        assumptions.append("Generated work items should reflect the refined engineering surfaces.")
    if not assumptions:
        assumptions.append("Generated features and stories should stay within the current epic scope.")
    return assumptions[:3]


def _feature_candidates(work_item: dict[str, Any], refinement: dict[str, Any]) -> list[dict[str, Any]]:
    title = _title_or_default(work_item, "Feature").rstrip(".")
    flows = list(refinement.get("base_flows", [])) or list(refinement.get("refined_base_flows", [])) or ["core"]
    return [
        {
            "title": f"{title}: Feature Slice {index}",
            "description": f"Organize the {title.lower()} epic into a deliverable feature slice focused on {flow}.",
        }
        for index, flow in enumerate(flows[:3] or ["core"], start=1)
    ]


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


def _acceptance_from_work_item(
    work_item: dict[str, Any],
    refinement: dict[str, Any],
    effective_context: dict[str, Any] | None = None,
) -> list[str]:
    acceptance = str(work_item.get("acceptanceCriteria") or work_item.get("acceptance_criteria") or "").strip()
    if acceptance:
        return [line.strip() for line in acceptance.splitlines() if line.strip()][:6]
    clarifications = [str(item.get("body", "")).strip() for item in (effective_context or {}).get("clarifications", []) if str(item.get("body", "")).strip()]
    if clarifications:
        return [f"Include clarified behavior: {clarifications[-1]}."]
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


def _contextual_work_item(work_item: dict[str, Any], effective_context: dict[str, Any] | None) -> dict[str, Any]:
    if not effective_context:
        return work_item
    contextual = dict(work_item)
    contextual["effective_context_text"] = effective_context.get("effective_text", "")
    contextual["clarifications"] = effective_context.get("clarifications", [])
    contextual["handoff_summaries"] = effective_context.get("handoff_summaries", [])
    # D: Pass epic_context and team_comments to assistants
    contextual["epic_context"] = effective_context.get("epic_context") or {}
    contextual["team_comments"] = effective_context.get("team_comments") or []
    contextual["question_answers"] = effective_context.get("question_answers") or []
    return contextual


def _question_answers_from_context(effective_context: dict[str, Any] | None) -> dict[str, str]:
    """Convert list of {question, answer} dicts to a {question: answer} mapping for bug_assistant."""
    qa_list = (effective_context or {}).get("question_answers") or []
    return {str(item.get("question", "")): str(item.get("answer", "")) for item in qa_list if item.get("question") and item.get("answer")}


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
