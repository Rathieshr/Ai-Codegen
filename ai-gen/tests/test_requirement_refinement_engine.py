from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.platform.shared import JsonMapStore
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
            "promptVersion": "requirement-refinement-v1",
            "recommendation": {"refinement": {
                "refinedRequirement": refined,
                "requirementSummary": "Search registered devices",
                "businessObjective": "Help Operations Users locate registered devices.",
                "problemStatement": "Registered devices are difficult to locate.",
                "userIntent": "Search registered field devices.",
                "primaryActor": "Operations User",
                "coreCapability": "Device Search",
                "expectedOutcome": "The requested registered device can be located.",
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
        self.assertEqual("requirement-refinement-v1", result["promptVersion"])
        self.assertEqual(["device inventory"], result["requirementIntent"]["repositoryHints"])
        workflow, context, _ = self.reasoning.calls[0]
        self.assertEqual("Requirement Refinement", workflow)
        self.assertEqual("RequirementRefinementInput", context["contextType"])
        self.assertNotIn("repository", context)
        self.assertNotIn("azureDevOps", context)

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
        self.assertEqual(200, client.post(f"/requirements/{requirement_id}/refinement/skip", json={}).status_code)


if __name__ == "__main__":
    unittest.main()
