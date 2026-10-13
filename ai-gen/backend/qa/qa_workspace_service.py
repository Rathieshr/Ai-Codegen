"""QA Workspace orchestration service."""

from __future__ import annotations

from typing import Any

from .acceptance_coverage_engine import AcceptanceCoverageEngine
from .qa_artifact_factory import QAArtifactFactory
from .qa_readiness_engine import QAReadinessEngine
from .regression_intelligence_engine import RegressionIntelligenceEngine
from .release_recommendation_engine import ReleaseRecommendationEngine
from .risk_intelligence_engine import RiskIntelligenceEngine
from .test_gap_analyzer import TestGapAnalyzer
from .test_intelligence_engine import TestIntelligenceEngine
from .qa_validation_rules import string_list


class QAWorkspaceService:
    def __init__(self) -> None:
        self.acceptance = AcceptanceCoverageEngine()
        self.tests = TestIntelligenceEngine()
        self.regression = RegressionIntelligenceEngine()
        self.risks = RiskIntelligenceEngine()
        self.gaps = TestGapAnalyzer()
        self.readiness = QAReadinessEngine()
        self.release = ReleaseRecommendationEngine()
        self.factory = QAArtifactFactory()

    def evaluate(
        self,
        *,
        story: dict[str, Any],
        acceptance_criteria: list[str],
        execution_package: dict[str, Any] | None = None,
        execution_plan: dict[str, Any] | str | None = None,
        repository_snapshot: dict[str, Any] | None = None,
        knowledge_registry: dict[str, Any] | None = None,
        engineering_graph: dict[str, Any] | None = None,
        implementation_validation: dict[str, Any] | None = None,
        tests: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        package = execution_package or {}
        acceptance = acceptance_criteria or _acceptance_from_package(package)
        test_intelligence = self.tests.generate(story, acceptance, package, package.get("repositoryContext") if isinstance(package.get("repositoryContext"), dict) else {}, knowledge_registry or {}, tests)
        coverage = self.acceptance.analyze(acceptance, test_intelligence["testCases"], implementation_validation)
        regression = self.regression.analyze(package, repository_snapshot, engineering_graph, implementation_validation)
        gaps = self.gaps.analyze(acceptance, test_intelligence["testCases"], implementation_validation)
        risks = self.risks.calculate(package, coverage, regression, gaps, implementation_validation)
        readiness = self.readiness.calculate(coverage, test_intelligence, regression, risks, gaps, implementation_validation)
        recommendation = self.release.recommend(readiness, risks, gaps)
        return self.factory.build(
            {
                "acceptanceCoverage": coverage,
                "testIntelligence": test_intelligence,
                "regressionIntelligence": regression,
                "riskIntelligence": risks,
                "testGapAnalysis": gaps,
                "qaReadiness": readiness,
                "releaseRecommendation": recommendation,
                "diagnostics": {
                    "consumedExecutionPackage": bool(execution_package),
                    "consumedExecutionPlan": bool(execution_plan),
                    "consumedImplementationValidation": bool(implementation_validation),
                    "repositorySnapshotAvailable": bool(repository_snapshot),
                    "knowledgeRegistryAvailable": bool(knowledge_registry),
                    "engineeringGraphAvailable": bool(engineering_graph),
                },
            }
        )


def _acceptance_from_package(package: dict[str, Any]) -> list[str]:
    mapping = package.get("acceptanceMapping") if isinstance(package.get("acceptanceMapping"), list) else []
    values = [item.get("acceptanceText") for item in mapping if isinstance(item, dict)]
    return string_list(values)
