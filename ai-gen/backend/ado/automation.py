"""Stage-approval → ADO action mapping.

When a pipeline stage is approved, ``AdoAutomation.run_for_stage()`` decides
which ADO operations to execute automatically.

Stage → Action mapping
----------------------
ba          → Update work item State to "Active", post clarification comment
ui          → Post UI spec summary as work item comment
dev_packet  → Create PR (source branch from pipeline context)
fix_packet  → Create PR, link work item
critic      → Post quality summary comment, update State to "Resolved"
test_*      → Post test checklist comment, update State to "Testing"

All results are returned as ``AutomationResult`` so the caller can decide
whether to surface them in the API response or store them for audit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .client import AdoClient, AdoClientError

logger = logging.getLogger("ai_gen.ado.automation")

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ActionRecord:
    action: str
    status: str          # "success" | "skipped" | "failed"
    detail: str = ""
    ado_resource: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "status": self.status,
            "detail": self.detail,
            "ado_resource": self.ado_resource,
        }


@dataclass
class AutomationResult:
    pipeline_id: str
    stage: str
    work_item_id: str | int | None
    actions: list[ActionRecord] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return any(a.status == "failed" for a in self.actions)

    @property
    def summary(self) -> str:
        counts = {"success": 0, "skipped": 0, "failed": 0}
        for a in self.actions:
            counts[a.status] = counts.get(a.status, 0) + 1
        return (
            f"stage={self.stage} "
            f"actions={len(self.actions)} "
            f"ok={counts['success']} skip={counts['skipped']} fail={counts['failed']}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "stage": self.stage,
            "work_item_id": self.work_item_id,
            "actions": [a.to_dict() for a in self.actions],
            "has_failures": self.has_failures,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# Automation engine
# ---------------------------------------------------------------------------

# Map each stage to the state it should move the work item into on approval.
_STAGE_STATE_TRANSITIONS: dict[str, str] = {
    "ba": "Active",
    "ui": "Active",
    "ui_optional": "Active",
    "dev_packet": "Active",
    "fix_packet": "Active",
    "task_planning": "Active",
    "test_checklist": "Testing",
    "test_planning": "Testing",
    "test_design": "Testing",
    "regression_tests": "Testing",
    "critic": "Resolved",
    "epic_analysis": "Active",
    "feature_generation": "Active",
    "story_generation": "Active",
}

# Stages that trigger PR creation (need source branch in pipeline context)
_PR_STAGES: frozenset[str] = frozenset({"dev_packet", "fix_packet"})

# Stages that post their output summary as a work item comment
_COMMENT_STAGES: frozenset[str] = frozenset({
    "ba", "ui", "ui_optional", "dev_packet", "fix_packet",
    "test_checklist", "test_planning", "critic", "epic_analysis",
})


class AdoAutomation:
    """Executes ADO side effects for an approved pipeline stage."""

    def __init__(self, client: AdoClient | None = None) -> None:
        self._client = client or AdoClient()

    @property
    def is_available(self) -> bool:
        return self._client.is_configured

    def run_for_stage(
        self,
        pipeline_id: str,
        stage: str,
        pipeline_state: dict[str, Any],
    ) -> AutomationResult:
        """Execute all ADO side effects for an approved stage.

        Parameters
        ----------
        pipeline_id:
            The ai-gen pipeline ID (for logging / result tracking).
        stage:
            The name of the just-approved stage.
        pipeline_state:
            The full pipeline state dict (contains work_item, repo_context,
            stage outputs, etc.).
        """
        work_item = pipeline_state.get("work_item") or {}
        work_item_id = (
            work_item.get("id")
            or work_item.get("work_item_id")
            or pipeline_state.get("work_item_id")
        )
        stage_data = (pipeline_state.get("stages") or {}).get(stage, {})
        stage_output = stage_data.get("output") or {}
        repo_ctx = pipeline_state.get("repo_context") or {}

        result = AutomationResult(
            pipeline_id=pipeline_id,
            stage=stage,
            work_item_id=work_item_id,
        )

        if not self.is_available:
            result.actions.append(ActionRecord(
                action="ado_automation",
                status="skipped",
                detail="ADO credentials not configured (ADO_PAT / ADO_ORG_URL / ADO_PROJECT missing).",
            ))
            return result

        # 1. Work item state transition
        self._maybe_update_state(result, stage, work_item_id)

        # 2. Post a structured comment to the work item
        if stage in _COMMENT_STAGES and work_item_id:
            self._post_stage_comment(result, stage, work_item_id, stage_output, pipeline_id)

        # 3. Create PR for DEV stages
        if stage in _PR_STAGES:
            self._maybe_create_pr(result, stage, work_item_id, stage_output, repo_ctx)

        logger.info("ai-gen ADO automation: %s", result.summary)
        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    def _maybe_update_state(
        self,
        result: AutomationResult,
        stage: str,
        work_item_id: str | int | None,
    ) -> None:
        target_state = _STAGE_STATE_TRANSITIONS.get(stage)
        if not target_state or not work_item_id:
            result.actions.append(ActionRecord(
                action="update_work_item_state",
                status="skipped",
                detail=f"No state transition defined for stage '{stage}' or missing work_item_id.",
            ))
            return
        try:
            updated = self._client.patch_work_item(
                work_item_id,
                {"System.State": target_state},
            )
            result.actions.append(ActionRecord(
                action="update_work_item_state",
                status="success",
                detail=f"State → '{target_state}'",
                ado_resource={"id": updated.get("id"), "rev": updated.get("rev")},
            ))
        except AdoClientError as exc:
            result.actions.append(ActionRecord(
                action="update_work_item_state",
                status="failed",
                detail=f"HTTP {exc.status}: {str(exc)[:200]}",
            ))

    def _post_stage_comment(
        self,
        result: AutomationResult,
        stage: str,
        work_item_id: str | int,
        stage_output: dict[str, Any],
        pipeline_id: str,
    ) -> None:
        comment_text = self._build_comment(stage, stage_output, pipeline_id)
        try:
            posted = self._client.add_work_item_comment(work_item_id, comment_text)
            result.actions.append(ActionRecord(
                action="post_work_item_comment",
                status="success",
                detail=f"Comment posted (id={posted.get('id')})",
                ado_resource={"id": posted.get("id")},
            ))
        except AdoClientError as exc:
            result.actions.append(ActionRecord(
                action="post_work_item_comment",
                status="failed",
                detail=f"HTTP {exc.status}: {str(exc)[:200]}",
            ))

    def _maybe_create_pr(
        self,
        result: AutomationResult,
        stage: str,
        work_item_id: str | int | None,
        stage_output: dict[str, Any],
        repo_ctx: dict[str, Any],
    ) -> None:
        repo_id = (
            str(repo_ctx.get("resolved_repo_id") or "").strip()
            or self._client._cfg.default_repo_id
        )
        source_branch = str(
            repo_ctx.get("resolved_branch_name")
            or stage_output.get("target_branch")
            or ""
        ).strip()

        if not repo_id or not source_branch:
            result.actions.append(ActionRecord(
                action="create_pull_request",
                status="skipped",
                detail=(
                    "Missing repo_id or source branch. Set ADO_DEFAULT_REPO_ID or ensure "
                    "pipeline repo_context contains resolved_repo_id and resolved_branch_name."
                ),
            ))
            return

        title = str(
            stage_output.get("pr_title")
            or stage_output.get("summary")
            or f"[ai-gen] {stage.replace('_', ' ').title()} changes"
        )[:200]

        description = _build_pr_description(stage, stage_output)

        try:
            pr = self._client.create_pull_request(
                repo_id=repo_id,
                source_branch=source_branch,
                target_branch="main",
                title=title,
                description=description,
                work_item_ids=[int(work_item_id)] if work_item_id else None,
                draft=True,   # always create as draft — human approves merge
            )
            pr_id = pr.get("pullRequestId")
            result.actions.append(ActionRecord(
                action="create_pull_request",
                status="success",
                detail=f"Draft PR #{pr_id} created from '{source_branch}' → main",
                ado_resource={"pullRequestId": pr_id, "isDraft": True},
            ))
        except AdoClientError as exc:
            result.actions.append(ActionRecord(
                action="create_pull_request",
                status="failed",
                detail=f"HTTP {exc.status}: {str(exc)[:200]}",
            ))

    @staticmethod
    def _build_comment(stage: str, output: dict[str, Any], pipeline_id: str) -> str:
        """Build a structured ADO comment from stage output."""
        lines = [f"[ai-gen Approval] Stage: {stage}", f"Pipeline: {pipeline_id}"]

        # Add key output fields as bullet points
        interesting_keys = [
            ("summary", "Summary"),
            ("goal", "Goal"),
            ("scope", "Scope"),
            ("acceptance_criteria", "Acceptance Criteria"),
            ("gaps", "Gaps"),
            ("risks", "Risks"),
            ("unknowns", "Open Questions"),
            ("ac_gaps", "AC Gaps"),
            ("base_flows", "Flows"),
        ]
        for key, label in interesting_keys:
            value = output.get(key)
            if not value:
                continue
            if isinstance(value, list):
                if value:
                    lines.append(f"\n**{label}:**")
                    lines.extend(f"- {item}" for item in value[:8])
            elif isinstance(value, str) and value.strip():
                lines.append(f"\n**{label}:** {value[:300]}")

        lines.append("\n*Posted automatically by ai-gen pipeline automation.*")
        return "\n".join(lines)


def _build_pr_description(stage: str, output: dict[str, Any]) -> str:
    """Build a PR description from dev stage output."""
    parts = [f"## ai-gen {stage.replace('_', ' ').title()}", ""]
    for key in ("summary", "goal", "scope"):
        value = output.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
            parts.append("")
        elif isinstance(value, list) and value:
            parts.extend(f"- {item}" for item in value[:6])
            parts.append("")
    parts.append("---")
    parts.append("*This PR was drafted automatically by [ai-gen](https://github.com/rathiesh/ai-gen).*")
    return "\n".join(parts)
