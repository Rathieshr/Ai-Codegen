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


class RequirementReasoningSpy:
    def __init__(self):
        self.calls = []

    def analyze(self, workflow_type, engineering_context, **kwargs):
        self.calls.append((workflow_type, engineering_context, kwargs))
        if workflow_type == "Requirement Intent Analysis":
            return {
                "reasoningMode": "AI",
                "provider": "Phi",
                "model": "phi-test",
                "promptVersion": "requirement-intent-v1",
                "recommendation": {
                    "requirementIntent": {
                        "intentSummary": "Give Operations Users timely device health visibility.",
                        "businessGoal": "Reduce the time required to identify unhealthy devices.",
                        "functionalIntent": ["View current device health and communication status."],
                        "entities": ["Operations User", "Device"],
                        "capabilities": ["Device Health Overview"],
                        "concepts": ["device health", "communication status"],
                        "searchKeywords": ["device", "health", "communication", "status"],
                        "possibleModuleNames": ["Device Health"],
                        "possibleFeatureNames": ["Device Health Overview"],
                        "possibleApis": ["Device Health API"],
                        "possibleRepositoryTerms": ["device health"],
                        "possibleAzureDevOpsSearchTerms": ["device health"],
                        "possibleMarkdownSearchTerms": ["device health architecture"],
                        "clarificationCandidates": [],
                        "confidence": 0.9,
                    },
                },
                "reasoning": ["The source states a user and observable outcome."],
                "alternatives": [],
                "evidence": [{"referenceId": "source:requirement"}],
                "warnings": [],
                "confidence": {"overall": 90, "level": "High"},
            }
        if workflow_type == "Requirement Evidence Synthesis":
            return {
                "reasoningMode": "AI",
                "provider": "Phi",
                "model": "phi-test",
                "promptVersion": "requirement-synthesis-v1",
                "recommendation": {
                    "executiveSummary": "Operations Users need current device health visibility.",
                    "businessGoal": "Reduce the time required to identify unhealthy devices.",
                    "functionalRequirements": [
                        "Operations Users must view current device health and communication status.",
                    ],
                    "repositoryFindings": [],
                    "architectureFindings": [],
                    "reuseOpportunities": [],
                    "affectedEngineeringElements": [],
                    "risks": [],
                    "openQuestions": [],
                    "missingInformation": ["Acceptance Criteria"],
                    "engineeringInsights": ["Use verified context before planning."],
                },
                "reasoning": ["The final analysis preserves the source behavior."],
                "alternatives": [],
                "evidence": [],
                "warnings": [],
                "confidence": {"overall": 84, "level": "High"},
            }
        if workflow_type == "Acceptance Criteria Generation":
            functional = engineering_context["requirement"]["functionalRequirements"][0]
            return {
                "reasoningMode": "AI",
                "provider": "Phi",
                "model": "phi-test",
                "promptVersion": "requirement-ac-v1",
                "recommendation": {
                    "acceptanceCriteria": [{
                        "title": "View Device Health",
                        "text": (
                            "Scenario: View Device Health\n"
                            "Given an Operations User\n"
                            "When the user opens device health\n"
                            "Then current health and communication status are visible."
                        ),
                        "type": "Functional",
                        "mappedFunctionalRequirement": functional,
                        "confidence": 91,
                    }],
                },
                "reasoning": ["The criterion maps to the supplied functional requirement."],
                "alternatives": [],
                "warnings": [],
                "confidence": {"overall": 88, "level": "High"},
            }
        return {
            "reasoningMode": "AI",
            "provider": "Phi",
            "model": "phi-test",
            "promptVersion": "requirement-analysis-v1",
            "recommendation": {"title": "Review generated criteria"},
            "reasoning": ["The requirement has a clear functional outcome."],
            "alternatives": [],
            "warnings": [],
            "confidence": {"overall": 84, "level": "High"},
        }


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
        self.assertEqual(1, len(suggested["acceptanceCriteriaSuggestions"]))
        self.assertTrue(all(item["origin"] == "AI Inferred" for item in suggested["acceptanceCriteriaSuggestions"]))
        self.assertIn("Given", suggested["acceptanceCriteriaSuggestions"][0]["text"])
        self.assertEqual(
            suggested["functionalRequirements"][0],
            suggested["acceptanceCriteriaSuggestions"][0]["mappedFunctionalRequirement"],
        )
        self.assertTrue(suggested["acceptanceCriteriaSuggestions"][0]["evidence"])
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
        self.assertEqual(1, len(approved["acceptanceCriteria"]))
        self.assertFalse(approved["missingAcceptanceCriteria"])
        summary = build_requirement_summary(self.ingestion.get(context["requirementId"]), approved)
        self.assertEqual(approved["acceptanceCriteria"], summary["acceptanceCriteria"])
        self.assertEqual(100, summary["acceptanceCoverage"]["coveragePercent"])

    def test_generated_criteria_are_evidence_driven_without_generic_templates(self):
        context = self.ingest(
            "Business Goal:\nReduce outage investigation time.\n"
            "Functional Requirements:\nOperations Users must view current device health.\n"
            "Actors:\nOperations User"
        )
        analysis = self.service.analyze(context["requirementId"])
        generated = self.service.suggest_acceptance_criteria(context["requirementId"])
        text = "\n".join(item["text"] for item in generated["acceptanceCriteriaSuggestions"]).lower()
        self.assertIn("view current device health", text)
        for unsupported in ("access is denied", "validation message", "audit", "session", "role management"):
            self.assertNotIn(unsupported, text)
        criterion = generated["acceptanceCriteriaSuggestions"][0]
        self.assertTrue(criterion["quality"]["traceable"])
        self.assertTrue(criterion["quality"]["independent"])
        self.assertTrue(criterion["quality"]["implementationIndependent"])
        self.assertEqual(analysis["functionalRequirements"][0], criterion["evidence"][0]["requirementSentence"])

    def test_product_language_actions_generate_evidence_backed_criteria(self):
        context = self.ingest(
            "Business Goal:\nIncrease productivity by adding AI intelligence.\n"
            "Functional Requirements:\nProvide recommendations and monitor fault proactiveness."
        )
        self.service.analyze(context["requirementId"])
        generated = self.service.suggest_acceptance_criteria(context["requirementId"])
        self.assertEqual("AISuggested", generated["acceptanceCriteriaState"]["state"])
        self.assertTrue(generated["acceptanceCriteriaSuggestions"])
        criterion = generated["acceptanceCriteriaSuggestions"][0]
        self.assertIn("provide recommendations", criterion["text"].lower())
        self.assertEqual(
            "Provide recommendations and monitor fault proactiveness.",
            criterion["evidence"][0]["requirementSentence"],
        )

    def test_ado_import_promotes_real_business_goal_and_rejects_import_metadata(self):
        imported_content = (
            "Business Goals:\n"
            "Allow Operations Users to search, monitor, and manage registered field devices "
            "from a centralized inventory.\n"
            "Description:\n"
            "Expected features\n"
            "Device Registration\n"
            "Device Search\n"
            "Device Details\n"
            "Area and Iteration:\n"
            "Area: LineDefender\n"
            "Iteration: LineDefender\n"
            "Functional Requirements:\n"
            "Requirement Summary:\n"
            "Planning Recommendations:\n"
            "No Acceptance Criteria were provided in the source requirement."
        )
        imported_ingestion = RequirementIngestionService(
            JsonMapStore(Path(self.temp.name) / "ado-contexts.json"),
            work_item_provider=lambda _project, _item: {
                "title": "Device inventory",
                "description": imported_content,
                "revision": 3,
            },
        )
        imported_service = RequirementAnalysisService(
            JsonMapStore(Path(self.temp.name) / "ado-analyses.json"),
            requirement_ingestion=imported_ingestion,
        )
        context = imported_ingestion.ingest({
            "sourceType": "AzureDevOpsWorkItem",
            "projectId": "linedefender",
            "workItemId": "245",
            "requirementSummary": imported_content,
        })

        analyzed = imported_service.analyze(context["requirementId"])

        evidence = (
            "Allow Operations Users to search, monitor, and manage registered field devices "
            "from a centralized inventory."
        )
        self.assertEqual([], analyzed["businessGoals"])
        self.assertEqual([evidence], analyzed["functionalRequirements"])
        self.assertEqual(["Operations Users"], analyzed["actors"])
        polluted = "\n".join(
            analyzed["businessGoals"] + analyzed["functionalRequirements"]
        )
        for value in (
            "Requirement Summary",
            "Planning Recommendations",
            "No Acceptance Criteria were provided",
            "Area: LineDefender",
            "Device Registration",
        ):
            self.assertNotIn(value, polluted)

        generated = imported_service.suggest_acceptance_criteria(context["requirementId"])
        self.assertEqual("AISuggested", generated["acceptanceCriteriaState"]["state"])
        self.assertEqual(3, len(generated["acceptanceCriteriaSuggestions"]))
        self.assertEqual(
            evidence,
            generated["acceptanceCriteriaSuggestions"][0]["evidence"][0]["requirementSentence"],
        )

    def test_generate_suggestions_refreshes_stale_requirement_analysis(self):
        context = self.ingest(
            "Business Goals:\n"
            "Allow Operations Users to search registered field devices from a centralized inventory."
        )
        analyzed = self.service.analyze(context["requirementId"])
        analyzed["diagnostics"]["engine"] = "DeterministicRequirementAnalysisV1"
        analyzed["functionalRequirements"] = ["Planning Recommendations"]
        values = self.service.store.read()
        values[context["requirementId"]] = analyzed
        self.service.store.write(values)

        generated = self.service.suggest_acceptance_criteria(context["requirementId"])

        self.assertEqual(
            "DeterministicRequirementAnalysisV3",
            generated["diagnostics"]["engine"],
        )
        self.assertNotIn("Planning Recommendations", generated["functionalRequirements"])
        self.assertTrue(generated["acceptanceCriteriaSuggestions"])

    def test_generate_suggestions_rebuilds_missing_analysis_from_requirement_context(self):
        context = self.ingest(
            "Business Goals:\n"
            "Allow Operations Users to identify unhealthy devices before failures occur.\n"
            "Functional Requirements:\n"
            "Operations Users must view current device health and communication status."
        )

        generated = self.service.suggest_acceptance_criteria(context["requirementId"])

        self.assertEqual(context["requirementId"], generated["requirementId"])
        self.assertEqual("AISuggested", generated["acceptanceCriteriaState"]["state"])
        self.assertTrue(generated["acceptanceCriteriaSuggestions"])
        self.assertIsNotNone(self.service.get(context["requirementId"]))

    def test_phi_reasoning_enriches_analysis_and_generates_acceptance_criteria(self):
        reasoning = RequirementReasoningSpy()
        service = RequirementAnalysisService(
            self.service.store,
            requirement_ingestion=self.ingestion,
            reasoning_engine=reasoning,
        )
        context = self.ingest(
            "Business Goals:\n"
            "Allow Operations Users to identify unhealthy devices before failures occur.\n"
            "Functional Requirements:\n"
            "Operations Users must view current device health and communication status."
        )

        analyzed = service.analyze(context["requirementId"])
        generated = service.suggest_acceptance_criteria(context["requirementId"])

        self.assertEqual("AI", analyzed["aiAnalysis"]["reasoningMode"])
        self.assertEqual("Phi", analyzed["aiAnalysis"]["provider"])
        self.assertEqual("Device Health Overview", analyzed["requirementIntent"]["capabilities"][0])
        self.assertEqual("requirement-analysis-ai-v1", analyzed["analysisLineage"]["analysisVersion"])
        self.assertIn("engineeringDiscovery", analyzed)
        self.assertEqual(
            [
                "Requirement Intent Analysis",
                "Requirement Evidence Synthesis",
                "Acceptance Criteria Generation",
            ],
            [call[0] for call in reasoning.calls],
        )
        self.assertEqual("AI", generated["acceptanceDiagnostics"]["generationMode"])
        self.assertEqual("Phi", generated["acceptanceDiagnostics"]["provider"])
        self.assertEqual(
            "AI Suggested",
            generated["acceptanceCriteriaSuggestions"][0]["origin"],
        )
        self.assertIn(
            "current health and communication status are visible",
            generated["acceptanceCriteriaSuggestions"][0]["text"],
        )

    def test_missing_requirement_context_is_not_hidden_by_analysis_recovery(self):
        with self.assertRaisesRegex(ValueError, "Requirement context was not found"):
            self.service.suggest_acceptance_criteria("requirement_missing")

    def test_insufficient_generation_evidence_returns_missing_information_not_error(self):
        context = self.ingest("Improve the operational experience.")
        self.service.analyze(context["requirementId"])
        result = self.service.suggest_acceptance_criteria(context["requirementId"])
        self.assertEqual("Missing", result["acceptanceCriteriaState"]["state"])
        self.assertEqual("NeedsUserInput", result["acceptanceCriteriaState"]["status"])
        self.assertEqual("InsufficientEvidence", result["acceptanceDiagnostics"]["generationStatus"])
        self.assertIn(
            "Generation Evidence",
            {item["field"] for item in result["missingInformation"]},
        )

    def test_each_functional_requirement_receives_criterion_and_coverage_mapping(self):
        context = self.ingest(
            "Functional Requirements:\n"
            "- Operations Users must view current device health.\n"
            "- Operations Users must filter devices by health status.\n"
            "Actors:\nOperations User"
        )
        self.service.analyze(context["requirementId"])
        generated = self.service.suggest_acceptance_criteria(context["requirementId"])
        self.assertEqual(2, len(generated["acceptanceCriteriaSuggestions"]))
        self.assertEqual(100, generated["acceptanceCoverage"]["coveragePercent"])
        self.assertFalse(generated["acceptanceCoverage"]["uncoveredFunctionalRequirements"])
        areas = {item["area"]: item["status"] for item in generated["acceptanceCoverage"]["areas"]}
        self.assertEqual("Covered", areas["Functional Requirements"])
        self.assertEqual("Covered", areas["Acceptance Criteria"])
        self.assertEqual("Not Provided", areas["Dependencies"])

    def test_allow_actor_requirement_generates_grammatical_fallback_criterion(self):
        context = self.ingest(
            "Functional Requirements:\n"
            "Allow Operations Users to search, monitor, and manage registered field devices "
            "from a centralized inventory.\n"
            "Actors:\nOperations Users"
        )
        self.service.analyze(context["requirementId"])
        generated = self.service.suggest_acceptance_criteria(context["requirementId"])
        criteria = generated["acceptanceCriteriaSuggestions"]
        combined = "\n".join(item["text"] for item in criteria)

        self.assertEqual(3, len(criteria))
        self.assertIn("Scenario: Search Registered Field Devices", combined)
        self.assertIn("Scenario: Monitor Registered Field Devices", combined)
        self.assertIn("Scenario: Manage Registered Field Devices", combined)
        self.assertIn("Given an Operations User is using the relevant workflow", combined)
        self.assertNotIn("can Operations Users to", combined)
        self.assertFalse(generated["missingAcceptanceCriteria"])

    def test_supported_business_rule_and_measurable_quality_evidence_generate_criteria(self):
        context = self.ingest(
            "Functional Requirements:\nOperations Users must view restricted device health.\n"
            "Actors:\nOperations User\n"
            "Business Rules:\nOnly authorized Operations Users may view restricted device health.\n"
            "Non Functional Requirements:\nDevice health must load within 2 seconds."
        )
        self.service.analyze(context["requirementId"])
        generated = self.service.suggest_acceptance_criteria(context["requirementId"])
        types = {item["type"] for item in generated["acceptanceCriteriaSuggestions"]}
        self.assertEqual({"Functional", "Business Rule", "Non-Functional"}, types)
        evidence_text = "\n".join(
            item["evidence"][0]["requirementSentence"]
            for item in generated["acceptanceCriteriaSuggestions"]
        )
        self.assertIn("Only authorized Operations Users", evidence_text)
        self.assertIn("within 2 seconds", evidence_text)

    def test_missing_information_and_assumptions_are_not_generated_as_criteria(self):
        context = self.ingest(
            "Functional Requirements:\nThe system must display device health.\n"
            "Assumptions:\nAssume telemetry is available."
        )
        analyzed = self.service.analyze(context["requirementId"])
        fields = {item["field"] for item in analyzed["missingInformation"]}
        self.assertIn("Actor", fields)
        self.assertIn("Trigger", fields)
        self.assertEqual("NeedsReview", analyzed["aiAssumptions"][0]["status"])
        generated = self.service.suggest_acceptance_criteria(context["requirementId"])
        text = "\n".join(item["text"] for item in generated["acceptanceCriteriaSuggestions"])
        self.assertNotIn("Assume telemetry is available", text)

    def test_source_criteria_include_traceable_evidence_records(self):
        context = self.ingest(
            "Functional Requirements:\nUsers must search devices by identifier.\n"
            "Acceptance Criteria:\nSearching a known identifier returns the matching device."
        )
        result = self.service.analyze(context["requirementId"])
        record = result["acceptanceCriteriaRecords"][0]
        self.assertEqual("Source Derived", record["origin"])
        self.assertEqual("Approved", record["status"])
        self.assertEqual(1.0, record["evidence"][0]["confidence"])
        self.assertEqual(100, result["acceptanceCoverage"]["coveragePercent"])

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

    def test_old_cached_analysis_is_rebuilt_for_acceptance_engine_version(self):
        context = self.ingest("Users must view device health.")
        first = self.service.analyze(context["requirementId"])
        values = self.service.store.read()
        values[context["requirementId"]].pop("acceptanceDiagnostics", None)
        self.service.store.write(values)
        refreshed = self.service.analyze(context["requirementId"])
        self.assertNotEqual(first["analysisId"], refreshed["analysisId"])
        self.assertEqual(
            "IntelligentAcceptanceCriteriaV1",
            refreshed["acceptanceDiagnostics"]["engine"],
        )

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
