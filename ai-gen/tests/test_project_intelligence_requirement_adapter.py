from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.project_intelligence import ProjectIntelligenceService
from backend.platform.shared import JsonMapStore
from backend.requirement_analysis import ProjectIntelligenceRequirementAnalyzer, RequirementAnalysisService
from backend.requirement_intake import RequirementIngestionService


class ProjectIntelligenceFacadeSpy:
    def analyze_requirement_intelligence(self, requirement, engineering_context):
        return {
            "used": True,
            "analysis": {
                "executiveSummary": "Operations needs timely transformer health visibility.",
                "businessGoal": "Reduce the time required to identify unhealthy transformers.",
                "functionalRequirements": [
                    "Operations users monitor current transformer health and communication status."
                ],
                "primaryActor": "Operations User",
                "capabilities": ["Transformer Health Overview", "Unhealthy Transformer Detection"],
                "repositorySearchHints": ["transformer health", "communication status"],
                "markdownSearchHints": ["transformer monitoring", "device health architecture"],
                "confidence": 88,
                "evidence": [{"referenceId": "requirement:transformer-health"}],
            },
            "metadata": {
                "provider_used": "azure_phi",
                "provider_deployment": "phi4-mini-instruct",
                "phi_prompt_tokens": 320,
                "phi_completion_tokens": 180,
            },
        }

    def generate_requirement_acceptance_criteria(self, requirement, engineering_context):
        functional = engineering_context["requirement"]["functionalRequirements"][0]
        return {
            "used": True,
            "acceptanceCriteria": [
                {
                    "text": "Scenario: View Transformer Health\nGiven an operations user\nWhen the user opens transformer health\nThen current health and communication status are visible.",
                    "mappedFunctionalRequirement": functional,
                    "confidence": 91,
                },
                {
                    "text": "Scenario: Identify Unhealthy Transformers\nGiven transformer health is available\nWhen a transformer reports an unhealthy state\nThen the transformer appears in the unhealthy results.",
                    "mappedFunctionalRequirement": functional,
                    "confidence": 87,
                },
                {
                    "text": "Scenario: Refresh Transformer Status\nGiven transformer status has changed\nWhen the user refreshes transformer health\nThen the latest communication status is displayed.",
                    "mappedFunctionalRequirement": functional,
                    "confidence": 84,
                },
                {
                    "text": "Scenario: Enforce Login\nGiven a user\nWhen the user opens the dashboard\nThen authentication and role-based permission are required.",
                    "mappedFunctionalRequirement": functional,
                    "confidence": 70,
                },
                {
                    "text": "Given the stated functional context\nWhen the user monitors transformer health\nThen transformer health can be monitored from the observable result.",
                    "mappedFunctionalRequirement": functional,
                    "confidence": 70,
                },
            ],
            "metadata": {
                "provider_used": "azure_phi",
                "provider_deployment": "phi4-mini-instruct",
                "acceptance_quality_score": 90,
                "quality_gate": "passed",
            },
        }


class DegradedProjectIntelligenceFacade:
    def analyze_requirement_intelligence(self, requirement, engineering_context):
        return {
            "used": False,
            "analysis": {},
            "metadata": {
                "phi_status": "not_configured",
                "fallback_reason": "Azure Phi provider is not configured.",
            },
        }

    def generate_requirement_acceptance_criteria(self, requirement, engineering_context):
        return {
            "used": False,
            "acceptanceCriteria": [],
            "metadata": {
                "phi_status": "timeout",
                "fallback_reason": "Azure Phi timed out.",
            },
        }


class AcceptanceReasoningFallbackSpy:
    def __init__(self):
        self.calls = []

    def analyze(self, workflow_type, engineering_context, **kwargs):
        self.calls.append(workflow_type)
        functional = engineering_context["requirement"]["functionalRequirements"][0]
        return {
            "reasoningMode": "AI",
            "provider": "Phi",
            "model": "phi-fallback",
            "promptVersion": "requirement-ac-fallback-v1",
            "recommendation": {"acceptanceCriteria": [{
                "text": (
                    "Scenario: View Transformer Health\n"
                    "Given an Operations User\n"
                    "When the user opens transformer health\n"
                    "Then current health and communication status are visible."
                ),
                "mappedFunctionalRequirement": functional,
                "confidence": 88,
            }]},
            "reasoning": ["Mapped the criterion to the supplied functional requirement."],
            "alternatives": [],
            "warnings": [],
            "confidence": {"overall": 88},
        }


class TransformerEngineeringIntelligence:
    def recommend_repository(self, requirement, analysis):
        return {"suggestedRepository": {}, "signals": {}, "source": "NoMatch"}

    def analyze_requirement(self, requirement, analysis):
        return dict(transformer_context()["requirement"])

    def build_requirement_context(self, requirement, correlation_id=""):
        context = transformer_context()
        context["requirement"] = {**context["requirement"], **requirement}
        return context

def transformer_context():
    return {
        "contextId": "engineering-context-transformer-v2",
        "contextVersion": "2.0",
        "requirement": {
            "title": "Transformer Health Dashboard",
            "planningRequirement": "Provide operations users with transformer health visibility.",
            "functionalRequirements": [
                "Operations users monitor current transformer health and communication status."
            ],
            "businessGoals": ["Reduce the time required to identify unhealthy transformers."],
        },
        "projectIntelligence": {
            "project": {"projectName": "LineDefender", "domain": "Utilities"},
            "knowledge": {
                "version": "knowledge-v8",
                "modules": ["Transformer Health"],
                "flows": ["Device Health Review"],
                "sourceFiles": ["docs/transformer-health.md"],
            },
            "approvedArtifacts": [{"id": "story-42", "title": "Review Transformer Health"}],
        },
        "repository": {
            "repositorySnapshotVersion": "snapshot-v4",
            "files": [{"path": "src/transformers/health.ts", "evidence": ["snapshot-v4"]}],
        },
        "repository_markdown_context": {
            "selected": [{"path": "docs/transformer-health.md", "summary": "Transformer health states."}],
        },
        "azureDevOps": {"existingPlanning": [{"id": 42, "title": "Review Transformer Health"}]},
        "sourceVersions": {
            "projectKnowledgeVersion": "knowledge-v8",
            "repositorySnapshotVersion": "snapshot-v4",
        },
    }


class ProjectIntelligenceRequirementAdapterTests(unittest.TestCase):
    def test_requirement_analysis_and_refinement_attempt_phi_before_fallback(self):
        class ProviderAwareFacade:
            def __init__(self):
                self.calls = []

            def analyze_requirement_intelligence(self, requirement, engineering_context, options=None):
                self.calls.append(("analyze", options))
                return {"used": False, "analysis": {}, "metadata": {"fallback_reason": "test"}}

            def refine_requirement_intelligence(self, requirement, engineering_context, options=None):
                self.calls.append(("refine", options))
                return {"used": False, "analysis": {}, "metadata": {"fallback_reason": "test"}}

        facade = ProviderAwareFacade()
        adapter = ProjectIntelligenceRequirementAnalyzer(facade)
        adapter.analyze({}, transformer_context())
        adapter.refine({}, transformer_context())

        self.assertEqual(["analyze", "refine"], [call[0] for call in facade.calls])
        self.assertTrue(all(call[1]["force_provider"] == "azure_phi" for call in facade.calls))
        self.assertTrue(all(call[1]["allow_fallback"] for call in facade.calls))

    def test_transformer_health_criteria_are_specific_and_traceable(self):
        adapter = ProjectIntelligenceRequirementAnalyzer(ProjectIntelligenceFacadeSpy())
        context = transformer_context()
        analysis = {"functionalRequirements": context["requirement"]["functionalRequirements"]}

        result = adapter.generate_acceptance_criteria({}, analysis, context)
        criteria = result["recommendation"]["acceptanceCriteria"]

        self.assertEqual(3, len(criteria))
        self.assertTrue(all(item["origin"] == "Project Intelligence Generated" for item in criteria))
        self.assertTrue(all(item["knowledgeVersion"] == "knowledge-v8" for item in criteria))
        self.assertTrue(all(item["repositoryRevision"] == "snapshot-v4" for item in criteria))
        self.assertNotIn("authentication", " ".join(item["text"] for item in criteria).lower())
        self.assertNotIn("observable result", " ".join(item["text"] for item in criteria).lower())
        self.assertEqual("Project Intelligence", result["provider"])

    def test_transformer_requirement_analysis_has_distinct_goal_capabilities_and_hints(self):
        adapter = ProjectIntelligenceRequirementAnalyzer(ProjectIntelligenceFacadeSpy())
        result = adapter.analyze({"title": "Transformer Health"}, transformer_context())
        analysis = result["recommendation"]

        self.assertNotEqual(
            analysis["businessGoal"], analysis["functionalRequirements"][0],
        )
        self.assertEqual("Operations User", analysis["primaryActor"])
        self.assertGreaterEqual(len(analysis["capabilities"]), 2)
        self.assertTrue(analysis["repositorySearchHints"])
        self.assertTrue(analysis["markdownSearchHints"])

    def test_provider_degradation_is_visible_and_retryable(self):
        adapter = ProjectIntelligenceRequirementAnalyzer(DegradedProjectIntelligenceFacade())
        result = adapter.generate_acceptance_criteria(
            {}, {"functionalRequirements": ["Monitor transformer health."]}, transformer_context(),
        )
        self.assertEqual("Degraded", result["status"])
        self.assertEqual("Deterministic", result["provider"])
        self.assertTrue(result["diagnostics"]["degraded"])
        self.assertTrue(result["diagnostics"]["retryAvailable"])
        self.assertIn("timed out", result["warnings"][0])

    def test_current_requirement_workflow_consumes_project_intelligence_output(self):
        with tempfile.TemporaryDirectory() as root:
            ingestion = RequirementIngestionService(JsonMapStore(Path(root) / "requirements.json"))
            context = ingestion.ingest({
                "sourceType": "PasteRequirement",
                "projectId": "linedefender",
                "title": "Transformer Health",
                "content": "Need a dashboard to monitor transformer health.",
            })
            service = RequirementAnalysisService(
                JsonMapStore(Path(root) / "analysis.json"),
                requirement_ingestion=ingestion,
                engineering_intelligence=TransformerEngineeringIntelligence(),
                project_intelligence_analyzer=ProjectIntelligenceRequirementAnalyzer(
                    ProjectIntelligenceFacadeSpy()
                ),
            )

            analyzed = service.analyze(context["requirementId"])
            generated = service.suggest_acceptance_criteria(context["requirementId"])

        self.assertEqual(
            "Reduce the time required to identify unhealthy transformers.",
            analyzed["businessGoals"][0],
        )
        self.assertGreaterEqual(len(analyzed["requirementIntent"]["capabilities"]), 2)
        self.assertEqual(
            "Project Intelligence Generated",
            generated["acceptanceCriteriaState"]["origin"],
        )
        self.assertEqual(3, len(generated["acceptanceCriteriaSuggestions"]))
        self.assertTrue(generated["acceptanceDiagnostics"]["projectIntelligencePrimary"])

    def test_central_reasoning_provider_is_tried_before_deterministic_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            ingestion = RequirementIngestionService(JsonMapStore(Path(root) / "requirements.json"))
            context = ingestion.ingest({
                "sourceType": "PasteRequirement",
                "projectId": "linedefender",
                "title": "Transformer Health",
                "content": "Operations users monitor current transformer health and communication status.",
            })
            reasoning = AcceptanceReasoningFallbackSpy()
            service = RequirementAnalysisService(
                JsonMapStore(Path(root) / "analysis.json"),
                requirement_ingestion=ingestion,
                engineering_intelligence=TransformerEngineeringIntelligence(),
                project_intelligence_analyzer=ProjectIntelligenceRequirementAnalyzer(
                    DegradedProjectIntelligenceFacade()
                ),
                reasoning_engine=reasoning,
            )

            service.analyze(context["requirementId"])
            generated = service.suggest_acceptance_criteria(context["requirementId"])

        self.assertIn("Acceptance Criteria Generation", reasoning.calls)
        self.assertEqual("AI", generated["acceptanceDiagnostics"]["generationMode"])
        self.assertEqual("Phi", generated["acceptanceDiagnostics"]["provider"])
        self.assertFalse(generated["acceptanceDiagnostics"]["degraded"])
        self.assertTrue(generated["acceptanceCriteriaSuggestions"])

    def test_public_facade_uses_stabilized_project_phi_pipeline(self):
        context = transformer_context()
        with tempfile.TemporaryDirectory() as data_dir, patch.dict(
            "os.environ", {"AI_GEN_DATA_DIR": data_dir}, clear=False,
        ), patch("backend.project_intelligence._project_phi_json") as probe:
            probe.return_value = {
                "used": True,
                "parsed": {"acceptanceCriteria": [{
                    "text": "Given transformer health, when it is opened, then current status is displayed."
                }]},
                "metadata": {},
            }
            result = ProjectIntelligenceService().generate_requirement_acceptance_criteria(
                {"title": "Transformer Health"}, context,
            )

        self.assertTrue(result["used"])
        self.assertEqual("generate_requirement_acceptance_criteria", probe.call_args.args[0])
        self.assertTrue(probe.call_args.args[1]["_active_context_capsule"]["payload"])
        evidence_catalog = probe.call_args.args[3]["evidenceCatalog"]
        self.assertEqual(["Transformer Health"], evidence_catalog["knowledgeModules"])
        self.assertTrue(evidence_catalog["selectedMarkdown"])
        self.assertTrue(evidence_catalog["repositoryFiles"])
        self.assertTrue(evidence_catalog["approvedProjectKnowledge"])
        self.assertTrue(evidence_catalog["azureDevOpsWork"])
        self.assertTrue(probe.call_args.args[4]["allow_fallback"])
        self.assertEqual("azure_phi", probe.call_args.args[4]["force_provider"])


if __name__ == "__main__":
    unittest.main()
