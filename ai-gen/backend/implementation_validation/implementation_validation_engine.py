"""Implementation Validation V1 orchestration."""

from __future__ import annotations

from typing import Any

from .acceptance_coverage_validator import AcceptanceCoverageValidator
from .diff_collector import DiffCollector
from .implementation_validation_report import build_report
from .repository_alignment_validator import RepositoryAlignmentValidator
from .scope_compliance_validator import ScopeComplianceValidator
from .standards_compliance_validator import StandardsComplianceValidator
from .test_coverage_validator import TestCoverageValidator


class ImplementationValidationEngine:
    def __init__(self) -> None:
        self.diff_collector = DiffCollector()
        self.acceptance_validator = AcceptanceCoverageValidator()
        self.scope_validator = ScopeComplianceValidator()
        self.repository_validator = RepositoryAlignmentValidator()
        self.standards_validator = StandardsComplianceValidator()
        self.test_validator = TestCoverageValidator()

    def validate(
        self,
        *,
        execution_package: dict[str, Any],
        developer_prompt: dict[str, Any] | None = None,
        task_dna: dict[str, Any] | None = None,
        story_dna: dict[str, Any] | None = None,
        repository_diff: dict[str, Any] | None = None,
        changed_files: list[Any] | None = None,
        test_results: dict[str, Any] | None = None,
        build_result: dict[str, Any] | None = None,
        repo_path: str | None = None,
    ) -> dict[str, Any]:
        package = execution_package or {}
        diff = self.diff_collector.collect(repository_diff, changed_files, repo_path=repo_path)
        files = diff["changedFiles"]
        acceptance = self.acceptance_validator.validate(package, files)
        scope = self.scope_validator.validate(package, files)
        repository = self.repository_validator.validate(package, files)
        standards = self.standards_validator.validate(package, files)
        tests = self.test_validator.validate(package, files, test_results)
        report = build_report(
            execution_package=package,
            changed_files=files,
            acceptance=acceptance,
            scope=scope,
            repository=repository,
            standards=standards,
            tests=tests,
            build_result=build_result,
        )
        report["inputs"] = {
            "developerPromptProvided": bool(developer_prompt),
            "taskDNAProvided": bool(task_dna),
            "storyDNAProvided": bool(story_dna),
            "diffSource": diff["source"],
        }
        return report


def validate_implementation(**kwargs: Any) -> dict[str, Any]:
    return ImplementationValidationEngine().validate(**kwargs)
