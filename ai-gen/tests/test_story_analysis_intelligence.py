import unittest

from backend.intelligence.dna import generateDNA
from backend.intelligence.story_analysis import StoryAnalysisEngine
from backend.project_intelligence import ProjectIntelligenceService


class _TimeoutProvider:
    metadata = {}
    parsed = {}

    def generate_json(self, prompt: str, output_type: str) -> dict:
        raise TimeoutError("feature analysis provider timed out")


def _profile() -> dict:
    return {
        "project_name": "LineDefender",
        "domain": "Utility Grid Management",
        "users": ["Operations User"],
        "knowledge_registry": {
            "modules": ["Fault Monitoring", "Telemetry", "Asset Health"],
            "flows": ["Fault Event Review Flow", "Device Health Review Flow"],
            "components": ["Fault Event List", "Fault Detail Panel"],
        },
        "development_standards": {
            "security_requirements": ["Role-based access"],
            "testing_requirements": ["Unit tests required"],
        },
    }


def _feature_dna() -> dict:
    return generateDNA(
        {
            "id": 501,
            "title": "Critical Fault Detection",
            "capability": "Fault Monitoring",
            "responsibilities": [
                "Detect fault",
                "Classify severity",
                "Review events",
                "Filter events",
                "View event details",
            ],
            "affected_modules": ["Fault Monitoring", "Telemetry"],
            "affected_flows": ["Fault Event Review Flow"],
            "dependencies": ["Telemetry Service"],
            "acceptance_criteria": ["Visibility", "Accuracy", "Filtering", "Security"],
        },
        "Feature",
        profile=_profile(),
        approved=True,
    )


class StoryAnalysisIntelligenceTests(unittest.TestCase):
    def test_story_analysis_derives_responsibilities_from_feature_dna(self) -> None:
        analysis = StoryAnalysisEngine().analyze({"id": 501, "title": "Critical Fault Detection"}, _feature_dna(), profile=_profile())

        self.assertIn("Detect fault", analysis["businessResponsibilities"])
        self.assertIn("Classify severity", analysis["businessResponsibilities"])
        self.assertEqual(analysis["validation"]["planningReadiness"], "PASS")

    def test_user_journeys_are_unique_and_have_repository_evidence(self) -> None:
        analysis = StoryAnalysisEngine().analyze({"id": 501, "title": "Critical Fault Detection"}, _feature_dna(), profile=_profile())
        journey_names = [journey["journeyName"] for journey in analysis["userJourneys"]]

        self.assertEqual(len(journey_names), len(set(journey_names)))
        self.assertTrue(analysis["repositoryEvidence"])
        self.assertTrue(all(journey["repositoryEvidence"] for journey in analysis["userJourneys"]))

    def test_story_analysis_planning_boundary_and_acceptance_themes(self) -> None:
        analysis = StoryAnalysisEngine().analyze({"id": 501, "title": "Critical Fault Detection"}, _feature_dna(), profile=_profile())

        self.assertTrue(analysis["planningBoundary"]["inScope"])
        self.assertIn("Visibility", analysis["acceptanceThemes"])
        self.assertIn("Security", analysis["acceptanceThemes"])
        self.assertGreaterEqual(analysis["diagnostics"]["validationScore"], 80)

    def test_story_generation_creates_one_story_per_approved_journey(self) -> None:
        dna = _feature_dna()
        analysis = StoryAnalysisEngine().analyze({"id": 501, "title": "Critical Fault Detection"}, dna, profile=_profile())
        journey = analysis["userJourneys"][0]
        story = StoryAnalysisEngine().generate_story_for_journey(journey, dna)

        self.assertEqual(story["journey_id"], journey["journeyId"])
        self.assertIn("As a ", story["description"])
        self.assertTrue(story["acceptance_criteria"])
        self.assertEqual(story["validationReport"]["status"], "Approved")

    def test_validation_rejects_duplicate_responsibilities(self) -> None:
        dna = _feature_dna()
        analysis = StoryAnalysisEngine().analyze({"id": 501, "title": "Critical Fault Detection"}, dna, profile=_profile())
        journey = analysis["userJourneys"][0]
        story = StoryAnalysisEngine().generate_story_for_journey(
            journey,
            dna,
            existing_responsibilities=[journey["businessResponsibility"]],
        )

        self.assertEqual(story["validationReport"]["status"], "Rejected")
        self.assertIn("Duplicate responsibility", story["validationReport"]["issues"][0])

    def test_refine_feature_returns_story_analysis_and_story_dna(self) -> None:
        dna = _feature_dna()
        result = ProjectIntelligenceService().refine_feature(
            {"id": 501, "title": "Critical Fault Detection", "work_item_dna": dna},
            _profile(),
            options={"force_provider": "deterministic_fallback"},
        )

        self.assertIn("story_analysis", result)
        self.assertIn("story_review", result)
        self.assertTrue(result["recommended_stories"])
        self.assertTrue(all(story["work_item_dna"]["parentDNA"] == dna["dnaId"] for story in result["recommended_stories"]))
        self.assertEqual(result["story_analysis"]["validation"]["planningReadiness"], "PASS")

    def test_feature_analysis_returns_deterministic_result_without_ai(self) -> None:
        result = ProjectIntelligenceService().refine_feature(
            {"id": 501, "title": "Critical Fault Detection", "work_item_dna": _feature_dna()},
            _profile(),
        )

        analysis = result["feature_analysis_result"]
        self.assertEqual(analysis["aiStatus"], "not_requested")
        self.assertEqual(analysis["validationStatus"], "Ready")
        self.assertTrue(analysis["deterministicDraft"]["storyCandidates"])
        self.assertNotIn("error", result)

    def test_feature_analysis_timeout_keeps_deterministic_draft(self) -> None:
        result = ProjectIntelligenceService().refine_feature(
            {"id": 501, "title": "Critical Fault Detection", "work_item_dna": _feature_dna()},
            _profile(),
            options={"mode": "retry_ai_enrichment", "llm_provider": _TimeoutProvider()},
        )

        analysis = result["feature_analysis_result"]
        self.assertEqual(analysis["aiStatus"], "timeout")
        self.assertEqual(analysis["validationStatus"], "NeedsReview")
        self.assertTrue(analysis["deterministicDraft"]["storyCandidates"])
        self.assertIn("AI enrichment failed", analysis["warnings"][0])
        self.assertNotIn("error", result)


if __name__ == "__main__":
    unittest.main()
