import os
import tempfile
import unittest
from unittest.mock import patch

from backend.intelligence_trace import TraceEngine
from backend.project_intelligence import ProjectIntelligenceService


def linedefender_profile() -> dict:
    return {
        "project_id": "LineDefender",
        "project_name": "LineDefender Smart Monitoring Platform",
        "domain": "Utility Grid Management",
        "project_type": "Multi-System Platform",
        "project_description": "LineDefender monitors fault events, telemetry, outage investigation, and field response.",
        "applications": [{"name": "Mobile App", "type": "Mobile"}, {"name": "Backend API", "type": "Backend"}],
        "knowledge_registry": {
            "modules": ["Fault Monitoring", "Telemetry", "Asset Health", "Firmware Update"],
            "flows": ["Fault Event Review Flow", "Outage Investigation Flow", "Device Health Review Flow", "Firmware Rollout"],
            "components": ["Fault Detail Screen", "Event Timeline"],
            "source_files": ["README.md", "docs/modules.md"],
        },
    }


class IntelligenceTraceIntegrationTests(unittest.TestCase):
    def test_feature_refinement_persists_planning_trace(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            result = ProjectIntelligenceService().refine_feature(
                {"id": 28, "title": "Critical Fault Detection", "description": "Operators review critical fault events with telemetry context."},
                linedefender_profile(),
                options={"force_provider": "deterministic_fallback"},
            )
            traces = TraceEngine().search({"projectId": "LineDefender", "decision": "Generate Story Recommendations"})

        self.assertEqual(result["intelligence_trace"]["trace_summary"]["decision"], "Generate Story Recommendations")
        self.assertEqual(result["intelligence_trace"]["trace_summary"]["stage"], "Planning")
        self.assertGreaterEqual(traces["count"], 1)

    def test_execution_context_persists_execution_trace(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            story = {
                "id": 34,
                "title": "Display Fault Event Details",
                "description": "As an Operations User, I want to view critical fault event details with telemetry.",
                "acceptance_criteria": ["Fault details are visible.", "Permission restricted users are denied."],
            }
            result = ProjectIntelligenceService().build_execution_context(
                story,
                linedefender_profile(),
                options={"force_provider": "deterministic_fallback"},
            )
            traces = TraceEngine().search({"projectId": "LineDefender", "decision": "Build Execution Package"})

        self.assertEqual(result["intelligence_trace"]["trace_summary"]["stage"], "Execution")
        self.assertGreaterEqual(traces["count"], 1)

    def test_qa_generation_persists_qa_trace(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            story = {
                "id": 35,
                "title": "Review Critical Fault Details",
                "description": "Operators review fault details and telemetry history.",
                "acceptance_criteria": ["Operator can view fault details.", "Unauthorized users are denied."],
            }
            result = ProjectIntelligenceService().generate_qa_test_cases(
                story,
                linedefender_profile(),
                options={"force_provider": "deterministic_fallback"},
            )
            traces = TraceEngine().search({"projectId": "LineDefender", "decision": "Generate QA Test Suite"})

        self.assertEqual(result["intelligence_trace"]["trace_summary"]["stage"], "QA")
        self.assertGreaterEqual(result["intelligence_trace"]["trace_summary"]["repository_evidence_count"], 1)
        self.assertGreaterEqual(traces["count"], 1)


if __name__ == "__main__":
    unittest.main()
