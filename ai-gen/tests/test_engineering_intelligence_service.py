from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.engineering_intelligence import EngineeringIntelligenceService
from backend.execution import ExecutionPackageService
from backend.execution.package_models import ExecutionRequest
from backend.platform.shared import JsonMapStore
from backend.planning_context import PlanningContextService
from backend.planning_recommendation import PlanningRecommendationService
from backend.requirement_analysis import RequirementAnalysisService
from backend.requirement_intake import RequirementIngestionService


class RepositoryProvider:
    def __init__(self):
        self.calls = []

    def get_repository(self, repository_id):
        self.calls.append(("repository", repository_id))
        return {
            "repositoryId": repository_id,
            "name": "Device Operations",
            "defaultBranch": "main",
            "status": "Active",
        }

    def get_current_snapshot(self, repository_id):
        self.calls.append(("snapshot", repository_id))
        return {
            "snapshotId": "snapshot-v4",
            "version": 4,
            "modules": ["Device Health", "Telemetry"],
        }

    def get_graph(self, repository_id):
        self.calls.append(("graph", repository_id))
        return {
            "nodes": [
                {"nodeId": "module-device", "nodeType": "Module", "name": "Device Health"},
                {"nodeId": "service-device", "nodeType": "Service", "name": "Device Health Service"},
                {"nodeId": "api-device", "nodeType": "API", "name": "Device Health API"},
                {"nodeId": "test-device", "nodeType": "Test", "name": "Device Health Tests"},
                {"nodeId": "file-device", "nodeType": "File", "name": "DeviceHealth.ts", "path": "src/DeviceHealth.ts"},
            ],
            "relationships": [{
                "fromNodeId": "service-device",
                "toNodeId": "api-device",
                "relationshipType": "depends_on",
            }],
        }


class MemoryProvider:
    def __init__(self):
        self.calls = []

    def find_relevant_memory(self, query):
        self.calls.append(query)
        return {
            "results": [
                {"id": "memory-story", "title": "Device filtering", "artifactType": "Story", "version": 2},
                {"id": "memory-test", "title": "Device permission tests", "artifactType": "Test", "version": 1},
            ]
        }


class PlanningProvider:
    def __init__(self, memory):
        self.memory = memory
        self.build_calls = 0
        self.analyze_calls = 0
        self.recommend_calls = 0

    def build_context(self, summary, repository):
        self.build_calls += 1
        memories = self.memory.find_relevant_memory({"text": summary["title"]})
        return {
            "contextId": "legacy-context",
            "contextVersion": "legacy-version",
            "requirement": {"title": summary["title"]},
            "projectId": summary["projectId"],
            "repository": repository,
            "azureDevOps": {
                "workItems": [{
                    "id": "12",
                    "type": "Feature",
                    "title": "Device Health Dashboard",
                    "state": "Active",
                    "revision": 3,
                    "assignedTo": "Engineer",
                }],
                "currentIterations": [{"id": "sprint-1", "name": "Sprint 1", "timeFrame": "Current"}],
            },
            "engineeringMemory": {"matches": memories["results"]},
        }

    def analyze(self, raw):
        self.analyze_calls += 1
        return {
            "similarWork": [{
                "workItem": raw["azureDevOps"]["workItems"][0],
                "confidence": 0.82,
                "reason": "The synchronized Feature covers device health.",
            }],
            "repositoryMatch": {"confidence": 92},
        }

    def recommend(self, raw, analysis):
        self.recommend_calls += 1
        return {
            "contextId": raw["contextId"],
            "mode": "EXTEND_FEATURE",
            "confidence": 88,
            "reason": ["An existing Feature is a strong match."],
            "recommendedStrategy": {"description": "Extend the existing Feature."},
        }


class RepositoryDetector:
    def __init__(self):
        self.calls = []

    def detect_requirement(self, requirement, analysis):
        self.calls.append((requirement, analysis))
        return {
            "suggestedRepository": {"repositoryId": "repo-1", "name": "Device Operations"},
            "confidence": 91,
            "reason": "Repository metadata matches device health.",
            "source": "RepositoryIntelligence",
            "signals": {},
        }


class EngineeringIntelligenceServiceTests(unittest.TestCase):
    def setUp(self):
        self.repository = RepositoryProvider()
        self.memory = MemoryProvider()
        self.planning = PlanningProvider(self.memory)
        self.detector = RepositoryDetector()
        self.service = EngineeringIntelligenceService(
            repository_intelligence=self.repository,
            repository_detector=self.detector,
            engineering_memory=self.memory,
            planning_engine=self.planning,
        )
        self.summary = {
            "requirementId": "requirement-1",
            "contextVersion": 3,
            "analysisId": "analysis-1",
            "title": "Filter the device health dashboard",
            "planningRequirement": "Operators filter devices by health status.",
            "functionalRequirements": ["Filter devices by Offline status."],
            "acceptanceCriteria": ["Only offline devices are returned."],
            "projectId": "project-1",
            "repository": {"repositoryId": "repo-1", "name": "Device Operations"},
            "qualityScore": 84,
        }

    def test_generate_planning_context_reuses_existing_providers(self):
        result = self.service.generate_planning_context(self.summary)
        context = result["engineeringContext"]

        self.assertEqual("Device Operations", context["repository"]["repositoryName"])
        self.assertEqual(["Device Health"], context["repository"]["affectedModules"])
        self.assertEqual(["Device Health API"], context["repository"]["apiEndpoints"])
        self.assertEqual("EXTEND_FEATURE", context["planningRecommendationInput"]["mode"])
        self.assertEqual(1, self.planning.build_calls)
        self.assertEqual(1, self.planning.analyze_calls)
        self.assertEqual(1, self.planning.recommend_calls)
        self.assertEqual(
            context["contextId"],
            result["rawContext"]["contextId"],
        )

    def test_similarity_and_reuse_are_projected_from_canonical_context(self):
        context = self.service.generate_planning_context(self.summary)["engineeringContext"]

        self.assertEqual(1, len(self.service.find_similar_features(context)))
        self.assertEqual([], self.service.find_similar_stories(context))
        self.assertEqual("src/DeviceHealth.ts", self.service.find_existing_implementation(context)[0]["path"])
        self.assertEqual("Device Health Tests", self.service.find_reusable_tests(context)[0]["name"])

    def test_execution_and_validation_views_are_bounded(self):
        context = self.service.generate_planning_context(self.summary)["engineeringContext"]

        execution = self.service.execution_context(context)
        validation = self.service.validation_context(context)

        self.assertEqual(["Device Health"], execution["relevantRepositoryModules"])
        self.assertEqual(["Device Health API"], execution["relevantApis"])
        self.assertEqual(["Device Health Tests"], validation["affectedTests"])
        self.assertEqual(["Device Health API"], validation["affectedApis"])
        self.assertNotIn("azureDevOps", execution)

    def test_repository_recommendation_delegates_to_existing_detector(self):
        recommendation = self.service.recommend_repository(
            {"title": "Device health"},
            {"functionalRequirements": ["Filter unhealthy devices"]},
        )

        self.assertEqual("repo-1", recommendation["suggestedRepository"]["repositoryId"])
        self.assertEqual(1, len(self.detector.calls))

    def test_repository_analysis_does_not_invent_files(self):
        repository = RepositoryProvider()
        repository.get_graph = lambda _repository_id: {"nodes": [], "relationships": []}
        service = EngineeringIntelligenceService(repository_intelligence=repository)

        result = service.analyze_repository({
            "title": "Device health",
            "repository": {"repositoryId": "repo-1"},
        })

        self.assertEqual([], result.files)


class RequirementIntegrationTests(unittest.TestCase):
    def test_requirement_analysis_uses_engineering_intelligence_recommendation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ingestion = RequirementIngestionService(JsonMapStore(root / "requirements.json"))
            requirement = ingestion.ingest({
                "sourceType": "PasteRequirement",
                "title": "Device Health",
                "content": "Business Goal: Identify unhealthy devices. Functional Requirement: Filter device health.",
                "projectId": "project-1",
            })
            intelligence = type("Intelligence", (), {
                "calls": 0,
                "recommend_repository": lambda self, _requirement, _analysis: (
                    setattr(self, "calls", self.calls + 1) or {
                        "suggestedRepository": {"repositoryId": "repo-1", "name": "Device Operations"},
                        "confidence": 90,
                        "reason": "Matched by Engineering Intelligence.",
                        "signals": {},
                    }
                ),
            })()
            service = RequirementAnalysisService(
                JsonMapStore(root / "analysis.json"),
                requirement_ingestion=ingestion,
                engineering_intelligence=intelligence,
            )

            result = service.analyze(requirement["requirementId"])

            self.assertEqual(1, intelligence.calls)
            self.assertEqual("repo-1", result["repositorySuggestion"]["suggestedRepository"]["repositoryId"])


class ExecutionIntegrationTests(unittest.TestCase):
    def test_execution_package_receives_only_projected_engineering_context(self):
        with tempfile.TemporaryDirectory() as temp:
            captured = {}

            class Builder:
                def build(self, capsule, _request):
                    captured.update(capsule)
                    return {
                        "packageId": "package-1",
                        "metadata": {
                            "status": "Ready",
                            "confidence": 90,
                            "repositorySnapshotVersion": "4",
                            "capsuleVersion": "1",
                        },
                        "diagnostics": {"warnings": []},
                    }

            intelligence = type("Intelligence", (), {
                "execution_context": lambda self, context: {
                    "engineeringContextId": context["contextId"],
                    "relevantFiles": [],
                },
            })()
            service = ExecutionPackageService(
                JsonMapStore(Path(temp) / "packages.json"),
                builder=Builder(),
                engineering_intelligence=intelligence,
            )
            result = service.build(
                {
                    "capsuleId": "capsule-1",
                    "engineeringContext": {
                        "contextId": "engineering-context-1",
                        "contextVersion": "1",
                    },
                },
                ExecutionRequest(purpose="ImplementationPackage"),
            )

            self.assertEqual("engineering-context-1", captured["engineeringExecutionContext"]["engineeringContextId"])
            self.assertEqual("engineering-context-1", result["engineeringContext"]["contextId"])


class CanonicalPlanningIntegrationTests(unittest.TestCase):
    def test_planning_context_and_recommendation_share_engineering_context(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            requirement = {
                "requirementId": "requirement-1",
                "contextVersion": "3",
                "contentHash": "hash-1",
                "title": "Filter the device health dashboard",
                "normalizedRequirement": "Operators filter devices by health status.",
                "sourceType": "PasteRequirement",
                "metadata": {
                    "projectId": "project-1",
                    "projectName": "GridHub",
                    "repositoryId": "repo-1",
                    "branch": "main",
                },
            }
            analysis = {
                "analysisId": "analysis-1",
                "reviewStatus": "Approved",
                "planningRequirement": requirement["normalizedRequirement"],
                "businessGoals": ["Find unhealthy devices faster."],
                "functionalRequirements": ["Filter devices by Offline status."],
                "acceptanceCriteria": ["Only offline devices are returned."],
                "requirementQualityScore": 84,
                "planningReadiness": {"status": "Ready", "blockers": [], "warnings": []},
            }
            ingestion = type("Ingestion", (), {"get": lambda _self, _identifier: requirement})()
            analysis_service = type("Analysis", (), {
                "assert_approved": lambda _self, _identifier: analysis,
            })()
            repository = RepositoryProvider()
            memory = MemoryProvider()
            engine = PlanningProvider(memory)
            intelligence = EngineeringIntelligenceService(
                repository_intelligence=repository,
                engineering_memory=memory,
                planning_engine=engine,
            )
            context_service = PlanningContextService(
                JsonMapStore(root / "contexts.json"),
                requirement_ingestion=ingestion,
                requirement_analysis=analysis_service,
                intelligence_engine=engine,
                repository_intelligence=repository,
                engineering_intelligence=intelligence,
            )
            recommendation_service = PlanningRecommendationService(
                JsonMapStore(root / "recommendations.json"),
                planning_context_service=context_service,
                engineering_intelligence=intelligence,
            )

            context = context_service.build({"requirementId": "requirement-1"})
            context_service.analyze({
                "contextId": context["contextId"],
                "decision": "Approve",
                "actor": "Product Owner",
            })
            recommendation = recommendation_service.build({"contextId": context["contextId"]})

            self.assertEqual(context["contextId"], context["engineeringContext"]["contextId"])
            self.assertEqual(context["contextId"], recommendation["contextId"])
            self.assertEqual("EXTEND_EXISTING_FEATURE", recommendation["strategy"])
            self.assertEqual(92, recommendation["confidence"]["repository"])


if __name__ == "__main__":
    unittest.main()
