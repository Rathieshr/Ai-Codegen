"""PR Review V1 orchestration."""

from __future__ import annotations

from typing import Any

from backend.implementation_validation import ImplementationValidationEngine

from .pr_diff_resolver import PRDiffResolver
from .pr_review_comment_builder import PRReviewCommentBuilder
from .pr_review_diagnostics import pr_review_diagnostics
from .pr_review_policy import PRReviewPolicy, pr_review_flags
from .pr_review_report import build_pr_review_report
from .work_item_link_resolver import WorkItemLinkResolver


class PRReviewEngine:
    def __init__(self) -> None:
        self.diff_resolver = PRDiffResolver()
        self.link_resolver = WorkItemLinkResolver()
        self.implementation_validator = ImplementationValidationEngine()
        self.comment_builder = PRReviewCommentBuilder()

    def review(
        self,
        *,
        pull_request: dict[str, Any] | None = None,
        linked_work_items: list[Any] | None = None,
        execution_package: dict[str, Any] | None = None,
        developer_prompt: dict[str, Any] | None = None,
        task_dna: dict[str, Any] | None = None,
        story_dna: dict[str, Any] | None = None,
        repository_diff: dict[str, Any] | None = None,
        changed_files: list[Any] | None = None,
        test_results: dict[str, Any] | None = None,
        build_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pull_request = pull_request or {}
        package = execution_package or {}
        links = self.link_resolver.resolve(pull_request, linked_work_items)
        diff = self.diff_resolver.resolve(pull_request, repository_diff, changed_files)
        implementation = self.implementation_validator.validate(
            execution_package=package,
            developer_prompt=developer_prompt or {},
            task_dna=task_dna or {},
            story_dna=story_dna or {},
            repository_diff={"changed_files": diff.get("changedFiles") or [], "diff": diff.get("diffText") or ""},
            changed_files=diff.get("changedFiles") or [],
            test_results=test_results or {},
            build_result=build_result or {},
        )
        flags = pr_review_flags()
        policy = PRReviewPolicy(flags)
        status = policy.status_for(implementation, links, package)
        diagnostics = pr_review_diagnostics(
            flags=flags,
            linked_items=links,
            diff=diff,
            execution_package=package,
            implementation_report=implementation,
        )
        report = build_pr_review_report(
            status=status,
            pull_request=pull_request,
            linked_work_items=links,
            implementation_report=implementation,
            diagnostics=diagnostics,
            posting_enabled=policy.posting_enabled(),
        )
        report["generatedReviewComment"] = self.comment_builder.build(report)
        return report

    def post_comment(self, report: dict[str, Any]) -> dict[str, Any]:
        flags = pr_review_flags()
        if not flags["ENABLE_PR_COMMENT_POSTING"]:
            return {
                "posted": False,
                "disabled": True,
                "message": "PR comment posting is disabled. Set ENABLE_PR_COMMENT_POSTING=true to enable posting.",
                "comment": report.get("generatedReviewComment") or "",
            }
        return {
            "posted": False,
            "disabled": False,
            "message": "PR comment posting transport is not configured in this preview.",
            "comment": report.get("generatedReviewComment") or "",
        }


def review_pr(**kwargs: Any) -> dict[str, Any]:
    return PRReviewEngine().review(**kwargs)
