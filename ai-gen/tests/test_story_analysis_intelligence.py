import os
import tempfile
import unittest
from unittest.mock import patch

from backend.intelligence.dna import generateDNA
from backend.intelligence.story_analysis import StoryAnalysisEngine
from backend.project_intelligence import ProjectIntelligenceService


class _TimeoutProvider:
    metadata = {}
    parsed = {}

    def is_enabled(self) -> bool:
        return True

    def health_snapshot(self) -> dict:
        return {"deployment": "Phi-4", "health": "healthy"}

    def safe_config(self) -> dict:
        return {"configured": True, "deployment": "Phi-4"}

    def generate_json(self, prompt: str, output_type: str) -> dict:
        raise TimeoutError("feature analysis provider timed out")

    def probe_json(self, *args, **kwargs) -> dict:
        raise TimeoutError("feature analysis provider timed out")


class _TruncatedProvider(_TimeoutProvider):
    def __init__(self) -> None:
        self.calls = 0
        self.user_prompt = ""

    def generate_json(self, prompt: str, output_type: str) -> dict:
        raise AssertionError("Feature Analysis enrichment must not use generic JSON artifact generation")

    def probe_json(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        self.calls += 1
        self.user_prompt = user_prompt
        return {
            "status": "parse_error",
            "http_status": 200,
            "elapsed_ms": 500,
            "raw_content": "It appears that you have provided a JSON-like structure with empty or null values.",
            "raw_response_preview": "It appears that you have provided a JSON-like structure with empty or null values.",
            "parsed_json": {},
            "failure_reason": "parse_error",
            "failure_message": "Model response could not be normalized into a JSON object.",
            "parse_error": "NoJsonObjectFound",
            "finish_reason": "length",
            "completion_tokens": 200,
            "prompt_tokens": 100,
            "response_length": 94,
        }


class _LeakyReasoningProvider(_TruncatedProvider):
    def probe_json(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        self.calls += 1
        self.user_prompt = user_prompt
        return {
            "status": "parse_error",
            "http_status": 200,
            "elapsed_ms": 500,
            "raw_content": "User journeys:\n- Fault Event Review Flow\n- Login Flow\n- Analytics Platform\nRisks:\n- Permission issues accessing fault events.",
            "raw_response_preview": "User journeys:\n- Fault Event Review Flow\n- Login Flow\n- Analytics Platform\nRisks:\n- Permission issues accessing fault events.",
            "parsed_json": {},
            "failure_reason": "parse_error",
            "failure_message": "Model response could not be normalized into a JSON object.",
            "parse_error": "NoJsonObjectFound",
            "finish_reason": "stop",
            "completion_tokens": 40,
            "prompt_tokens": 100,
            "response_length": 120,
        }


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

    def test_feature_analysis_truncated_phi_response_is_recoverable(self) -> None:
        provider = _TruncatedProvider()
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            result = ProjectIntelligenceService().refine_feature(
                {"id": 501, "title": "Critical Fault Detection", "work_item_dna": _feature_dna()},
                _profile(),
                options={"mode": "retry_ai_enrichment", "llm_provider": provider},
            )

        analysis = result["feature_analysis_result"]
        self.assertEqual(provider.calls, 1)
        self.assertIn("Feature Analysis AI Enrichment", provider.user_prompt)
        self.assertNotIn("current_intent", provider.user_prompt)
        self.assertEqual(result["phi_status"], "truncated_response")
        self.assertEqual(analysis["aiStatus"], "truncated_response")
        self.assertTrue(analysis["deterministicDraft"]["storyCandidates"])
        self.assertNotIn("error", result)

    def test_feature_analysis_enrichment_filters_irrelevant_context_leakage(self) -> None:
        provider = _LeakyReasoningProvider()
        profile = _profile()
        profile["knowledge_registry"]["flows"] = [
            "Fault Event Review Flow",
            "Device Health Review Flow",
            "Login Flow",
            "Analytics Platform",
        ]
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            result = ProjectIntelligenceService().refine_feature(
                {"id": 501, "title": "Critical Fault Detection", "work_item_dna": _feature_dna()},
                profile,
                options={"mode": "retry_ai_enrichment", "llm_provider": provider},
            )

        self.assertIn("Fault Event Review Flow", provider.user_prompt)
        self.assertNotIn("Login Flow", provider.user_prompt)
        self.assertNotIn("Analytics Platform", provider.user_prompt)
        reasoning = result["feature_analysis_result"]["aiEnrichment"]["aiReasoningText"]
        self.assertIn("Fault Event Review Flow", reasoning)
        self.assertNotIn("Login Flow", reasoning)
        self.assertNotIn("Analytics Platform", reasoning)


if __name__ == "__main__":
    unittest.main()
