from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.platform.shared import JsonMapStore
from backend.requirement_analysis import RequirementAnalysisEngine, RequirementAnalysisService, build_requirement_analysis_router
from backend.requirement_analysis.summary import build_requirement_summary
from backend.requirement_intake import RequirementIngestionService, RequirementIntakeService


ROOT = Path(__file__).resolve().parents[1]


class ContextSpy:
    def __init__(self):
        self.requests = []

    def orchestrate(self, request):
        self.requests.append(request)
        return {"capsuleId": "capsule-analysis", "status": "Ready", "confidence": 0.8, "freshnessStatus": "Fresh", "sourceSummary": [], "warnings": [], "blockers": []}


class RequirementAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.ingestion = RequirementIngestionService(JsonMapStore(root / "contexts.json"))
        self.service = RequirementAnalysisService(JsonMapStore(root / "analyses.json"), requirement_ingestion=self.ingestion)

    def tearDown(self):
        self.temp.cleanup()

    def ingest(self, content: str, title: str = "Device health"):
        return self.ingestion.ingest({"sourceType": "PasteRequirement", "projectId": "gridhub", "title": title, "content": content})

    def test_extracts_normalized_engineering_categories(self):
        context = self.ingest("""
Business Goal:
Reduce the time Operations Users spend identifying offline devices.
Functional Requirements:
- Operations Users must filter devices by health status.
Non-Functional Requirements:
- Results must load within 2 seconds.
Acceptance Criteria:
- Given offline devices, when status is filtered, then only matching devices are shown.
Actors:
- Operations User
Business Rules:
- Only authorized users may view restricted devices.
Constraints:
- Results are limited to the selected operating region.
Dependencies:
- Requires the Device Health API service.
Risks:
- Stale telemetry may delay status changes.
Open Questions:
- What telemetry freshness threshold applies?
Assumptions:
- Assume device status is available from telemetry.
""")
        result = self.service.analyze(context["requirementId"])
        self.assertEqual("Ready", result["planningReadiness"]["status"])
        for key in ("businessGoals", "functionalRequirements", "nonFunctionalRequirements", "acceptanceCriteria", "actors", "businessRules", "constraints", "dependencies", "risks", "openQuestions", "assumptions"):
            self.assertTrue(result[key], key)
        self.assertIn("Functional Requirements:", result["planningRequirement"])
        self.assertGreaterEqual(result["requirementQualityScore"], 70)

    def test_missing_acceptance_and_ambiguity_need_user_input(self):
        context = self.ingest("The system should quickly show some appropriate device information.")
        result = self.service.analyze(context["requirementId"])
        self.assertEqual("NeedsUserInput", result["planningReadiness"]["status"])
        self.assertTrue(result["missingAcceptanceCriteria"])
        self.assertTrue(result["ambiguousRequirements"])
        self.assertEqual("Missing", result["acceptanceCriteriaState"]["state"])
        self.assertIn("provided in the source", result["acceptanceCriteriaState"]["description"])
        self.assertNotIn("Acceptance criteria require definition", result["planningRequirement"])

    def test_missing_acceptance_is_ready_with_recommendations_not_ai_failure(self):
        context = self.ingest(
            "Business Goal:\nReduce device outage investigation time.\n"
            "Functional Requirements:\nOperations Users must view current device health.\n"
            "Actors:\nOperations User\n"
            "Non Functional Requirements:\nResults must load within 2 seconds."
        )
        result = self.service.analyze(context["requirementId"])
        self.assertEqual("ReadyWithRecommendations", result["planningReadiness"]["status"])
        self.assertTrue(result["planningReadiness"]["readyForPlanning"])
        self.assertEqual("Missing", result["acceptanceCriteriaState"]["state"])
        self.assertEqual("Missing", result["acceptanceCriteriaState"]["status"])
        self.assertLess(result["requirementQualityScore"], 100)
        self.assertGreaterEqual(result["requirementQualityScore"], 60)

    def test_source_acceptance_criteria_are_approved_and_origin_is_visible(self):
        context = self.ingest(
            "Functional Requirements:\nUsers must view device health.\n"
            "Acceptance Criteria:\nEach device displays its current health state."
        )
        result = self.service.analyze(context["requirementId"])
        self.assertEqual("SourceProvided", result["acceptanceCriteriaState"]["state"])
        self.assertEqual("Approved", result["acceptanceCriteriaState"]["status"])
        self.assertEqual("Source", result["fieldOrigins"]["acceptanceCriteria"])
        with self.assertRaisesRegex(ValueError, "already authoritative"):
            self.service.suggest_acceptance_criteria(context["requirementId"])
        with self.assertRaisesRegex(ValueError, "cannot be discarded"):
            self.service.discard_acceptance_criteria(context["requirementId"], "Product Owner")

    def test_ai_suggestions_require_review_and_do_not_leak_into_summary(self):
        context = self.ingest(
            "Business Goal:\nReduce device outage investigation time.\n"
            "Functional Requirements:\nOperations Users must view current device health.\n"
            "Actors:\nOperations User"
        )
        result = self.service.analyze(context["requirementId"])
        suggested = self.service.suggest_acceptance_criteria(context["requirementId"], "Product Owner")
        self.assertEqual("AISuggested", suggested["acceptanceCriteriaState"]["state"])
        self.assertEqual("PendingReview", suggested["acceptanceCriteriaState"]["status"])
        self.assertEqual([], suggested["acceptanceCriteria"])
        self.assertEqual(3, len(suggested["acceptanceCriteriaSuggestions"]))
        self.assertTrue(all(item["origin"] == "AI Suggested" for item in suggested["acceptanceCriteriaSuggestions"]))
        self.assertIn("Given", suggested["acceptanceCriteriaSuggestions"][0]["text"])
        with self.assertRaisesRegex(ValueError, "Review the AI Suggested"):
            self.service.approve(context["requirementId"], "Product Owner")

        summary = build_requirement_summary(self.ingestion.get(context["requirementId"]), suggested)
        self.assertEqual([], summary["acceptanceCriteria"])
        self.assertEqual("PendingReview", summary["acceptanceCriteriaState"]["status"])

    def test_approved_ai_suggestions_become_planning_criteria(self):
        context = self.ingest(
            "Business Goal:\nReduce device outage investigation time.\n"
            "Functional Requirements:\nOperations Users must view current device health.\n"
            "Actors:\nOperations User"
        )
        self.service.analyze(context["requirementId"])
        self.service.suggest_acceptance_criteria(context["requirementId"], "Product Owner")
        approved = self.service.approve_acceptance_criteria(context["requirementId"], "Product Owner")
        self.assertEqual("Approved", approved["acceptanceCriteriaState"]["status"])
        self.assertEqual("AI Suggested", approved["fieldOrigins"]["acceptanceCriteria"])
        self.assertEqual(3, len(approved["acceptanceCriteria"]))
        self.assertFalse(approved["missingAcceptanceCriteria"])
        summary = build_requirement_summary(self.ingestion.get(context["requirementId"]), approved)
        self.assertEqual(approved["acceptanceCriteria"], summary["acceptanceCriteria"])

    def test_edit_and_discard_ai_suggestions_preserve_user_control(self):
        context = self.ingest(
            "Business Goal:\nReduce device outage investigation time.\n"
            "Functional Requirements:\nOperations Users must view current device health."
        )
        self.service.analyze(context["requirementId"])
        suggested = self.service.suggest_acceptance_criteria(context["requirementId"])
        edited = self.service.update_acceptance_criteria_suggestions(
            context["requirementId"],
            [{**suggested["acceptanceCriteriaSuggestions"][0], "text": "Given a device, when health loads, then its current state is visible."}],
            "Product Owner",
        )
        self.assertEqual("User Edited", edited["acceptanceCriteriaState"]["origin"])
        approved = self.service.approve_acceptance_criteria(context["requirementId"], "Product Owner")
        self.assertEqual("User Edited", approved["fieldOrigins"]["acceptanceCriteria"])

        discarded = self.service.discard_acceptance_criteria(context["requirementId"], "Product Owner")
        self.assertEqual("Discarded", discarded["acceptanceCriteriaState"]["status"])
        self.assertEqual([], discarded["acceptanceCriteria"])
        self.assertEqual("ReadyWithRecommendations", discarded["planningReadiness"]["status"])

    def test_repository_selection_refresh_preserves_approved_ai_criteria(self):
        class RepositoryDetector:
            def detect_requirement(self, requirement, analysis):
                return {
                    "source": "Detection",
                    "confidence": 0.9,
                    "suggestedRepository": {
                        "repositoryId": "repo-device",
                        "name": "Device Platform",
                        "matchedModules": ["Device Health"],
                    },
                }

        service = RequirementAnalysisService(
            JsonMapStore(Path(self.temp.name) / "repository-refresh-analyses.json"),
            requirement_ingestion=self.ingestion,
            repository_detector=RepositoryDetector(),
        )
        context = self.ingest(
            "Business Goal:\nReduce device outage investigation time.\n"
            "Functional Requirements:\nOperations Users must view current device health."
        )
        service.analyze(context["requirementId"])
        service.suggest_acceptance_criteria(context["requirementId"], "Product Owner")
        approved_criteria = service.approve_acceptance_criteria(context["requirementId"], "Product Owner")["acceptanceCriteria"]
        approved = service.approve(context["requirementId"], "Product Owner")
        self.assertEqual(approved_criteria, approved["acceptanceCriteria"])
        self.assertEqual("Approved", approved["acceptanceCriteriaState"]["status"])

    def test_repeated_inline_headings_do_not_leak_labels_into_business_goal(self):
        context = self.ingest(
            "Business Goal: Business Value: Give Operations Users a centralized view of device health. "
            "Functional Requirements: The dashboard should show current equipment status. "
            "Acceptance Criteria: Each device displays its current health state.",
            "Launch LineDefender in GridHubb",
        )

        result = self.service.analyze(context["requirementId"])

        self.assertEqual(
            ["Give Operations Users a centralized view of device health."],
            result["businessGoals"],
        )
        self.assertNotIn("Business Value", result["requirementSummary"])
        self.assertEqual(1, len(result["functionalRequirements"]))
        self.assertEqual(1, len(result["acceptanceCriteria"]))

    def test_conflicting_requirements_block_planning(self):
        analysis = RequirementAnalysisEngine().analyze({
            "requirementId": "r1", "contextVersion": "1", "contentHash": "h", "title": "Restricted device access",
            "normalizedRequirement": "Functional Requirements:\nAuthorized users must view restricted device health records.\nAuthorized users must not view restricted device health records.\nAcceptance Criteria:\nAccess is validated for an authorized Operations User.",
        }).to_dict()
        self.assertEqual("Blocked", analysis["planningReadiness"]["status"])
        self.assertTrue(analysis["conflictingRequirements"])

    def test_negative_permission_criterion_is_not_a_false_conflict(self):
        analysis = RequirementAnalysisEngine().analyze({
            "requirementId": "r2", "contextVersion": "1", "contentHash": "h", "title": "Restricted device access",
            "normalizedRequirement": "Functional Requirements:\nAuthorized Operations Users must view restricted device records.\nAcceptance Criteria:\nUnauthorized Operations Users must not view restricted device records.",
        }).to_dict()
        self.assertFalse(analysis["conflictingRequirements"])

    def test_duplicate_requirements_are_reported_but_removed_from_planning_input(self):
        context = self.ingest("Functional Requirements:\nUsers must search devices by identifier.\nUsers must search devices by identifier.\nAcceptance Criteria:\nSearching by a known identifier returns one device.")
        result = self.service.analyze(context["requirementId"])
        self.assertTrue(result["duplicateRequirements"])
        self.assertEqual(1, result["planningRequirement"].count("Users must search devices by identifier."))

    def test_analysis_is_cached_until_context_content_changes(self):
        context = self.ingest("Users must view device health.\nAcceptance Criteria:\nDevice health status is displayed.")
        first = self.service.analyze(context["requirementId"])
        second = self.service.analyze(context["requirementId"])
        self.assertEqual(first["analysisId"], second["analysisId"])
        changed = self.ingestion.ingest({
            "requirementId": context["requirementId"], "sourceType": "PasteRequirement", "projectId": "gridhub",
            "title": "Device health", "content": "Users must view current device health.\nAcceptance Criteria:\nCurrent status is displayed for each device.",
        })
        refreshed = self.service.analyze(changed["requirementId"])
        self.assertNotEqual(first["analysisId"], refreshed["analysisId"])
        self.assertEqual(changed["contentHash"], refreshed["contentHash"])

    def test_analysis_api_exposes_post_and_persisted_get(self):
        context = self.ingest("Users must view device health.\nAcceptance Criteria:\nDevice health status is displayed.")
        app = FastAPI()
        app.include_router(build_requirement_analysis_router(self.service))
        client = TestClient(app)
        response = client.post("/requirements/analyze", json={"requirementId": context["requirementId"]})
        self.assertEqual(200, response.status_code)
        stored = client.get(f"/requirements/{context['requirementId']}/analysis")
        self.assertEqual(response.json()["analysisId"], stored.json()["analysisId"])
        approved = client.post(f"/requirements/{context['requirementId']}/analysis/approve", json={"actor": "Product Owner"})
        self.assertEqual("Approved", approved.json()["reviewStatus"])
        reanalyzed = client.post(f"/requirements/{context['requirementId']}/analysis/reanalyze")
        self.assertEqual("Pending", reanalyzed.json()["reviewStatus"])
        edited = client.post(f"/requirements/{context['requirementId']}/analysis/edit", json={
            "title": "Current device health",
            "content": "Functional Requirements:\nUsers must view current device health.\nAcceptance Criteria:\nCurrent health is displayed.",
            "actor": "Product Owner",
        })
        self.assertEqual("2.0", edited.json()["contextVersion"])
        cancelled = client.post(f"/requirements/{context['requirementId']}/analysis/cancel", json={"actor": "Product Owner"})
        self.assertEqual("Cancelled", cancelled.json()["reviewStatus"])
        self.assertEqual(404, client.post("/requirements/analyze", json={"requirementId": "missing"}).status_code)

    def test_planning_consumes_analysis_output_and_blocks_conflicts(self):
        context_spy = ContextSpy()
        artifacts = []
        intake = RequirementIntakeService(
            JsonMapStore(Path(self.temp.name) / "planning.json"),
            context_orchestrator=context_spy,
            artifact_writer=lambda item: artifacts.append(item) or {**item, "artifact_id": "pack-1"},
            ingestion_service=self.ingestion,
            analysis_service=self.service,
        )
        context = self.ingest("Functional Requirements:\nUsers must view current device health.\nAcceptance Criteria:\nCurrent health is shown for each device.")
        with self.assertRaisesRegex(ValueError, "Review and approve"):
            intake.submit({"requirementContextId": context["requirementId"]})
        self.service.analyze(context["requirementId"])
        self.service.approve(context["requirementId"], "Product Owner")
        result = intake.submit({"requirementContextId": context["requirementId"]})
        self.assertIn("Functional Requirements:", context_spy.requests[0].artifact["description"])
        self.assertEqual(result["requirementAnalysis"]["analysisId"], artifacts[0]["payload"]["requirementAnalysis"]["analysisId"])

        conflict = self.ingest("Functional Requirements:\nUsers must view restricted device records.\nUsers must not view restricted device records.\nAcceptance Criteria:\nAccess is validated for restricted records.", "Conflict")
        self.service.analyze(conflict["requirementId"])
        with self.assertRaisesRegex(ValueError, "Blocked requirement analysis"):
            self.service.approve(conflict["requirementId"], "Product Owner")

    def test_edit_invalidates_approval_and_reanalysis_requires_new_review(self):
        context = self.ingest("Functional Requirements:\nUsers must view device health.\nAcceptance Criteria:\nDevice health is displayed.")
        self.service.analyze(context["requirementId"])
        approved = self.service.approve(context["requirementId"], "Product Owner")
        self.assertEqual("Approved", approved["reviewStatus"])
        edited = self.service.edit(context["requirementId"], {
            "title": "Current device health",
            "content": "Functional Requirements:\nUsers must view current device health.\nAcceptance Criteria:\nCurrent device health is displayed.",
            "actor": "Product Owner",
        })
        self.assertEqual("Pending", edited["reviewStatus"])
        self.assertEqual("2.0", edited["contextVersion"])
        with self.assertRaisesRegex(ValueError, "approval is required"):
            self.service.assert_approved(context["requirementId"])

    def test_ui_runs_analysis_between_ingestion_and_planning(self):
        source = (ROOT / "azure-devops-extension/src/newRequirementWorkspace.tsx").read_text()
        self.assertLess(source.index("/requirements/ingest"), source.index("/requirements/analyze"))
        self.assertLess(source.index("/requirements/analyze"), source.index("/planning/context/build"))
        self.assertLess(source.index("/planning/context/build"), source.index("/planning/recommendation"))
        self.assertLess(source.index("/planning/recommendation"), source.index("/planning/proposal"))
        self.assertNotIn("/requirements/intake", source)
        self.assertIn("Requirement Analysis", source)
        for action in ("Continue to Planning", "Edit", "Cancel", "Re-analyze"):
            self.assertIn(action, source)
        self.assertIn("Approve & Continue to Planning", source)
        self.assertIn("No Planning Pack has been created", source)

    def test_requirement_review_exposes_enterprise_ux_landmarks(self):
        source = (ROOT / "azure-devops-extension/src/newRequirementWorkspace.tsx").read_text()
        styles = (ROOT / "azure-devops-extension/src/storyPlanner.css").read_text()

        for label in (
            "Requirement Source", "Requirement Analysis", "Repository Detection", "Engineering Memory",
            "Quality Review", "Planning", "Approval", "Azure DevOps",
        ):
            self.assertIn(label, source)
        for section in (
            "Requirement Health", "Repository Recommendation", "Quality Findings", "Engineering Context", "HEI Insights",
        ):
            self.assertIn(section, source)
        for action in ("Accept Recommendation", "Override Repository", "Edit Requirement"):
            self.assertIn(action, source)
        self.assertIn("hei-requirement-sticky-actions", source)
        self.assertIn("Estimated planning complexity", source)
        self.assertIn("Recommended Next Action", source)
        self.assertIn("hei-requirement-review-layout", styles)
        self.assertIn(".hei-insights", styles)
        self.assertIn("position: sticky", styles)
        self.assertIn("@media (max-width: 1100px)", styles)
        self.assertIn("@media (max-width: 720px)", styles)

    def test_requirement_review_exposes_acceptance_origin_and_approval_actions(self):
        source = (ROOT / "azure-devops-extension/src/newRequirementWorkspace.tsx").read_text()
        styles = (ROOT / "azure-devops-extension/src/storyPlanner.css").read_text()
        for label in (
            "SourceProvided", "AISuggested", "AI Suggested", "User Edited", "Imported",
            "Generate Suggested Acceptance Criteria", "Approve Suggestions", "Regenerate",
            "Discard", "This is not an AI error", "Ready with Recommendations",
        ):
            self.assertIn(label, source)
        self.assertIn("acceptance-criteria/${path}", source)
        api = (ROOT / "backend/requirement_analysis/api.py").read_text()
        self.assertIn('acceptance-criteria/suggestions', api)
        self.assertIn("hei-origin-badge", styles)
        self.assertIn("hei-acceptance-card", styles)


if __name__ == "__main__":
    unittest.main()
