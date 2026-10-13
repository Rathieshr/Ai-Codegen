from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.platform.shared import JsonMapStore
from backend.reasoning.models import ReasoningRequest
from backend.reasoning.services import PromptBuilder
from backend.requirement_analysis import RequirementAnalysisService
from backend.requirement_intake import RequirementIngestionService
from backend.requirement_refinement import RequirementRefinementService, build_requirement_refinement_router


class RefinementReasoningSpy:
    def __init__(self, *, unsafe: bool = False) -> None:
        self.calls: list[tuple[str, dict, dict]] = []
        self.unsafe = unsafe

    def refine(self, workflow_type, context, **kwargs):
        self.calls.append((workflow_type, context, kwargs))
        refined = (
            "Implement device search with authentication and audit logging."
            if self.unsafe else
            "Allow Operations Users to search registered field devices from a centralized inventory."
        )
        return {
            "reasoningMode": "AI",
            "provider": "Phi",
            "model": "phi-test",
            "promptVersion": "requirement-refinement-v2:test",
            "recommendation": {"refinement": {
                "refinedRequirement": refined,
                "executiveSummary": "Operations Users need a reliable way to locate registered devices.",
                "requirementSummary": "Search registered devices",
                "businessGoal": "Reduce the effort required to locate registered devices.",
                "businessObjective": "Help Operations Users locate registered devices.",
                "problemStatement": "Registered devices are difficult to locate.",
                "userIntent": "Search registered field devices.",
                "primaryActor": "Operations User",
                "coreCapability": "Device Search",
                "coreCapabilities": ["Device Search", "Device Inventory Discovery"],
                "expectedOutcome": "The requested registered device can be located.",
                "businessEntities": ["Registered Device", "Device Inventory"],
                "engineeringConcepts": ["Device Search", "Inventory Discovery"],
                "domainTerminology": ["field device", "registered device"],
                "repositorySearchHints": ["device search", "device inventory"],
                "markdownSearchHints": ["device inventory", "registered devices"],
                "azureDevOpsSearchHints": ["device search", "inventory discovery"],
                "possibleModuleNames": ["Device Inventory"],
                "possibleFeatureNames": ["Device Search"],
                "potentialDomainTerms": ["field device"],
                "potentialSearchKeywords": ["device", "search", "inventory"],
                "potentialRepositoryTerms": ["device inventory"],
                "potentialAzureDevOpsTerms": ["device search"],
                "potentialMarkdownTerms": ["device inventory"],
                "changes": [{"change": "Clarified the actor and action.", "reason": "Improved wording without adding scope."}],
                "ambiguities": ["Search fields are not specified."],
                "clarificationCandidates": ["Which device fields should be searchable?"],
                "requirementIntent": {
                    "businessGoal": "Help Operations Users locate registered devices.",
                    "functionalIntent": ["Search registered field devices."],
                    "entities": ["Operations User", "Device"],
                    "actions": ["search"],
                    "concepts": ["device inventory"],
                    "keywords": ["device", "search", "inventory"],
                    "repositoryHints": ["device inventory"],
                    "markdownHints": ["device inventory"],
                    "azureDevOpsHints": ["device search"],
                    "clarificationCandidates": ["Which device fields should be searchable?"],
                    "confidence": 0.88,
                },
                "confidence": 0.88,
            }},
            "reasoning": ["The source explicitly requests device search."],
            "warnings": [],
            "confidence": {"overall": 88},
        }


class RequirementRefinementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.ingestion = RequirementIngestionService(JsonMapStore(root / "requirements.json"))
        self.reasoning = RefinementReasoningSpy()
        self.service = RequirementRefinementService(
            JsonMapStore(root / "refinements.json"),
            requirement_ingestion=self.ingestion,
            reasoning_engine=self.reasoning,
        )
        self.requirement = self.ingestion.ingest({
            "sourceType": "PasteRequirement",
            "projectId": "linedefender",
            "projectName": "LineDefender",
            "title": "Device search",
            "content": "Need device search.",
        })

    def tearDown(self):
        self.temp.cleanup()

    def test_refinement_uses_bounded_input_and_persists_lineage(self):
        result = self.service.refine(self.requirement["requirementId"])
        self.assertEqual("PendingReview", result["status"])
        self.assertEqual("Need device search.", result["originalRequirement"])
        self.assertIn("Operations Users", result["refinedRequirement"])
        self.assertEqual("Phi", result["provider"])
        self.assertEqual("requirement-refinement-v2:test", result["promptVersion"])
        self.assertEqual(["device inventory"], result["requirementIntent"]["repositoryHints"])
        self.assertNotEqual(result["businessGoal"], result["userIntent"])
        self.assertEqual(["Registered Device", "Device Inventory"], result["businessEntities"])
        self.assertTrue(result["coreCapabilities"])
        self.assertTrue(result["repositorySearchHints"])
        self.assertEqual("Need device search.", result["originalRequirement"])
        workflow, context, kwargs = self.reasoning.calls[0]
        self.assertEqual("Requirement Refinement", workflow)
        self.assertEqual("Auto", kwargs["provider"])
        self.assertEqual("RequirementRefinementInput", context["contextType"])
        self.assertNotIn("repository", context)
        self.assertNotIn("azureDevOps", context)

    def test_project_intelligence_refinement_is_preferred_and_clarifications_are_persisted(self):
        project_refiner = RefinementReasoningSpy()

        class UnexpectedGenericReasoning:
            def refine(self, *_args, **_kwargs):
                raise AssertionError("Generic reasoning should not run after Project Intelligence succeeds.")

        service = RequirementRefinementService(
            JsonMapStore(Path(self.temp.name) / "project-refinement.json"),
            requirement_ingestion=self.ingestion,
            reasoning_engine=UnexpectedGenericReasoning(),
            project_intelligence_refiner=project_refiner,
        )
        initial = service.refine(self.requirement["requirementId"])
        clarified = service.answer_clarifications(
            self.requirement["requirementId"],
            [{"question": "Which device fields should be searchable?", "answer": "Device ID and device name."}],
            "Product Owner",
        )

        self.assertEqual("Phi", initial["provider"])
        self.assertEqual(2, len(project_refiner.calls))
        self.assertEqual(
            "Device ID and device name.",
            project_refiner.calls[-1][1]["clarificationResponses"][0]["answer"],
        )
        self.assertEqual([], clarified["clarificationCandidates"])
        self.assertEqual("Product Owner", clarified["clarifiedBy"])
        canonical, _ = service.canonical_requirement(self.requirement["requirementId"])
        self.assertEqual("Device ID and device name.", canonical["clarificationResponses"][0]["answer"])

    def test_deterministic_v2_fallback_still_improves_and_extracts_source_terms(self):
        requirement = self.ingestion.ingest({
            "sourceType": "PasteRequirement",
            "projectId": "linedefender",
            "projectName": "LineDefender",
            "title": "Device Health Operations",
            "content": (
                "Provide Operations Users with a real-time view of device health, communication status, "
                "and operational alerts so that unhealthy devices can be identified and acted on before failures occur."
            ),
        })
        service = RequirementRefinementService(
            JsonMapStore(Path(self.temp.name) / "deterministic-v2.json"),
            requirement_ingestion=self.ingestion,
        )
        result = service.refine(requirement["requirementId"])
        self.assertNotEqual(result["originalRequirement"], result["refinedRequirement"])
        self.assertIn("Enable Operations Users", result["refinedRequirement"])
        self.assertIn("device health", [item.casefold() for item in result["businessEntities"]])
        self.assertTrue(result["coreCapabilities"])
        self.assertTrue(result["repositorySearchHints"])
        self.assertNotEqual(result["businessGoal"].casefold(), result["userIntent"].casefold())
        self.assertIn("not configured", result["fallbackReason"].casefold())
        self.assertEqual([], result["providerAttempts"])

    def test_unchanged_provider_wording_is_safely_refined_for_notification_intent(self):
        requirement = self.ingestion.ingest({
            "sourceType": "PasteRequirement",
            "projectId": "linedefender",
            "projectName": "LineDefender",
            "title": "Critical condition notification",
            "content": (
                "Notify maintenance engineers when a LineDefender device reports "
                "a critical condition or stops transmitting telemetry."
            ),
        })

        class UnchangedRefinementReasoning:
            def refine(self, *_args, **_kwargs):
                return {
                    "reasoningMode": "AI",
                    "provider": "Phi",
                    "model": "phi-test",
                    "recommendation": {"refinement": {
                        "refinedRequirement": requirement["normalizedRequirement"],
                        "primaryActor": "Maintenance Engineer",
                        "coreCapabilities": ["Critical Condition Notification"],
                        "confidence": 0.84,
                    }},
                }

        service = RequirementRefinementService(
            JsonMapStore(Path(self.temp.name) / "unchanged-refinement.json"),
            requirement_ingestion=self.ingestion,
            reasoning_engine=UnchangedRefinementReasoning(),
        )
        result = service.refine(requirement["requirementId"])

        self.assertNotEqual(result["originalRequirement"], result["refinedRequirement"])
        self.assertEqual(
            "Enable maintenance engineers to receive a notification when a LineDefender "
            "device reports a critical condition or stops transmitting telemetry.",
            result["refinedRequirement"],
        )
        self.assertTrue(result["changes"])
        self.assertEqual("Phi", result["provider"])

    def test_v2_prompt_is_provider_neutral_and_requests_complete_refinement(self):
        request = ReasoningRequest(
            workflowType="Requirement Refinement",
            engineeringContext={
                "contextType": "RequirementRefinementInput",
                "contextId": "refinement-test",
                "contextVersion": "1.0",
                "requirement": {"title": "Device search", "normalizedRequirement": "Need device search."},
                "metadata": {"projectName": "LineDefender"},
            },
            userRequirement="Need device search.",
        )
        built = PromptBuilder().build(request, provider="Phi", model="phi-test")
        self.assertTrue(built.promptVersion.startswith("requirement-refinement-v2:"))
        self.assertIn("coreCapabilities", built.prompt)
        self.assertIn("businessEntities", built.prompt)
        self.assertIn("repositorySearchHints", built.prompt)
        self.assertNotIn("repositoryDump", built.prompt)

    def test_accept_edit_skip_and_regenerate_are_versioned(self):
        initial = self.service.refine(self.requirement["requirementId"])
        accepted = self.service.accept(self.requirement["requirementId"], "Product Owner")
        self.assertEqual("Accepted", accepted["status"])
        edited = self.service.edit(
            self.requirement["requirementId"],
            "Allow Operations Users to search registered devices.",
            "Product Owner",
        )
        self.assertEqual(2, edited["version"])
        self.assertTrue(edited["revisionHistory"])
        skipped = self.service.skip(self.requirement["requirementId"], "Product Owner")
        canonical, _ = self.service.canonical_requirement(self.requirement["requirementId"])
        self.assertEqual("Skipped", skipped["status"])
        self.assertEqual("Need device search.", canonical["normalizedRequirement"])
        regenerated = self.service.refine(self.requirement["requirementId"], force=True)
        self.assertGreater(regenerated["version"], initial["version"])

    def test_unsafe_provider_expansion_falls_back_without_invented_features(self):
        root = Path(self.temp.name)
        service = RequirementRefinementService(
            JsonMapStore(root / "unsafe.json"),
            requirement_ingestion=self.ingestion,
            reasoning_engine=RefinementReasoningSpy(unsafe=True),
        )
        result = service.refine(self.requirement["requirementId"])
        self.assertNotIn("authentication", result["refinedRequirement"].lower())
        self.assertNotIn("audit", result["refinedRequirement"].lower())
        self.assertTrue(any("unsupported functionality" in warning for warning in result["warnings"]))

    def test_transient_deterministic_refinement_retries_immediately_when_provider_recovers(self):
        class RecoveringReasoning:
            def __init__(self):
                self.calls = 0

            def is_provider_available(self, preference="Auto"):
                return True

            def refine(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return {
                        "reasoningMode": "Deterministic",
                        "provider": "Deterministic",
                        "warnings": ["provider_error: temporary failure"],
                        "promptVersion": "requirement-refinement-v2:test",
                    }
                return RefinementReasoningSpy().refine(*args, **kwargs)

        root = Path(self.temp.name)
        reasoning = RecoveringReasoning()
        service = RequirementRefinementService(
            JsonMapStore(root / "recovering.json"),
            requirement_ingestion=self.ingestion,
            reasoning_engine=reasoning,
        )

        result = service.refine(self.requirement["requirementId"])

        self.assertEqual("Phi", result["provider"])
        self.assertEqual(2, reasoning.calls)
        self.assertEqual(
            ["attempt 1: deterministic", "attempt 2: ai"],
            result["providerAttempts"],
        )

    def test_user_can_add_freeform_clarification_without_generated_question(self):
        service = RequirementRefinementService(
            JsonMapStore(Path(self.temp.name) / "freeform-clarification.json"),
            requirement_ingestion=self.ingestion,
            reasoning_engine=self.reasoning,
        )
        initial = service.refine(self.requirement["requirementId"])
        initial["clarificationCandidates"] = []
        service._save(self.requirement["requirementId"], initial)

        clarified = service.answer_clarifications(
            self.requirement["requirementId"],
            [{
                "question": "Additional requirement clarification",
                "answer": "Maintenance Engineers use device ID and device name.",
            }],
            "Product Owner",
        )

        self.assertEqual(
            "Maintenance Engineers use device ID and device name.",
            clarified["clarificationResponses"][0]["answer"],
        )

    def test_analysis_consumes_refined_requirement_and_intent(self):
        root = Path(self.temp.name)
        analysis = RequirementAnalysisService(
            JsonMapStore(root / "analyses.json"),
            requirement_ingestion=self.ingestion,
            refinement_service=self.service,
        )
        result = analysis.analyze(self.requirement["requirementId"])
        self.assertIn("Operations Users", result["planningRequirement"])
        self.assertEqual("device inventory", result["requirementIntent"]["possibleRepositoryTerms"][0])
        self.assertEqual(result["requirementRefinement"]["version"], result["refinementVersion"])
        self.service.skip(self.requirement["requirementId"], "Product Owner")
        skipped = analysis.analyze(self.requirement["requirementId"])
        self.assertEqual("Skipped", skipped["refinementStatus"])
        self.assertIn("Need device search", skipped["planningRequirement"])

    def test_api_supports_review_actions(self):
        app = FastAPI()
        app.include_router(build_requirement_refinement_router(self.service))
        client = TestClient(app)
        requirement_id = self.requirement["requirementId"]
        self.assertEqual(200, client.post(f"/requirements/{requirement_id}/refine", json={}).status_code)
        self.assertEqual(200, client.get(f"/requirements/{requirement_id}/refinement").status_code)
        accepted = client.post(f"/requirements/{requirement_id}/refinement/accept", json={"actor": "Owner"})
        self.assertEqual("Accepted", accepted.json()["status"])
        edited = client.put(f"/requirements/{requirement_id}/refinement", json={
            "actor": "Owner", "refinedRequirement": "Allow users to search registered devices.",
        })
        self.assertEqual(200, edited.status_code)
        clarified = client.post(
            f"/requirements/{requirement_id}/refinement/clarifications",
            json={
                "actor": "Owner",
                "responses": [{
                    "question": "Which device fields should be searchable?",
                    "answer": "Device ID and device name.",
                }],
            },
        )
        self.assertEqual(200, clarified.status_code)
        self.assertEqual("Device ID and device name.", clarified.json()["clarificationResponses"][0]["answer"])
        self.assertEqual(200, client.post(f"/requirements/{requirement_id}/refinement/skip", json={}).status_code)


if __name__ == "__main__":
    unittest.main()
