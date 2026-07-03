import os
import tempfile
import unittest
from unittest.mock import patch

from backend.engineering_memory import EngineeringMemoryEngine
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


def approve_and_index(engine: EngineeringMemoryEngine, payload: dict) -> dict:
    stored = engine.store_memory({**payload, "source": payload.get("source") or {"status": "Approved"}})
    memory = stored["memory"]
    engine.approve_memory(memory["id"], "tester")
    return engine.index_memory(memory["id"], "tester")["memory"]


class EngineeringMemoryIntegrationTests(unittest.TestCase):
    def test_planning_retrieves_similar_approved_stories(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            engine = EngineeringMemoryEngine()
            approve_and_index(engine, {
                "projectId": "LineDefender",
                "category": "Planning Memory",
                "title": "Review Critical Fault Details Story Pattern",
                "summary": "Reusable story pattern for reviewing critical fault details with telemetry and permission checks.",
                "content": "Acceptance: fault detail data visible; permission restricted users denied; stale telemetry labeled.",
                "artifactType": "Story",
                "artifactId": "story-34",
                "knowledgeReferences": ["Fault Monitoring", "Telemetry", "Fault Event Review Flow"],
                "tags": ["fault", "story", "acceptance"],
                "confidence": 0.94,
            })

            feature = {
                "title": "Critical Fault Detection",
                "description": "Operators review critical fault events with telemetry context.",
            }
            result = ProjectIntelligenceService().refine_feature(feature, linedefender_profile(), options={"force_provider": "deterministic_fallback"})

        self.assertGreaterEqual(result["memory_context"]["confidence"], 0.9)
        self.assertEqual(result["memory_context"]["relevantMemories"][0]["artifactType"], "Story")
        self.assertTrue(result["acceptance_criteria_memory_hints"])
        self.assertIn("same_module", result["memory_context"]["retrievalReasons"])

    def test_execution_retrieves_prior_successful_package(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            engine = EngineeringMemoryEngine()
            approve_and_index(engine, {
                "projectId": "LineDefender",
                "category": "Execution Memory",
                "title": "Fault Detail Execution Package",
                "summary": "Successful package for Fault Monitoring and Telemetry detail rendering with permission tests.",
                "content": "Known risk: stale telemetry requires Data Unavailable handling. Test expectation: permission test required.",
                "artifactType": "Execution Package",
                "artifactId": "pkg-9",
                "knowledgeReferences": ["Fault Monitoring", "Telemetry", "Fault Event Review Flow"],
                "tags": ["execution", "risk", "test"],
                "confidence": 0.91,
            })
            story = {
                "title": "Display Fault Event Details",
                "description": "As an Operations User, I want to view critical fault event details with telemetry.",
                "acceptance_criteria": ["Fault details are visible.", "Permission restricted users are denied."],
            }
            result = ProjectIntelligenceService().build_execution_context(story, linedefender_profile(), options={"force_provider": "deterministic_fallback"})

        self.assertTrue(result["relevant_prior_implementation"])
        self.assertTrue(result["known_implementation_risks"])
        self.assertTrue(result["reusable_testing_expectations"])
        self.assertEqual(result["memory_context"]["previousSuccessfulArtifacts"][0]["artifactType"], "Execution Package")

    def test_qa_retrieves_prior_regression_tests(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            engine = EngineeringMemoryEngine()
            approve_and_index(engine, {
                "projectId": "LineDefender",
                "category": "QA Memory",
                "title": "Fault Review Regression Permission Tests",
                "summary": "Regression test pattern for restricted fault event access and stale telemetry behavior.",
                "content": "Prior tests: unauthorized user denied; stale telemetry visible as Data Unavailable.",
                "artifactType": "Test Suite",
                "artifactId": "qa-5",
                "knowledgeReferences": ["Fault Monitoring", "Telemetry", "Fault Event Review Flow"],
                "tags": ["qa", "regression", "permission", "test"],
                "confidence": 0.9,
            })
            story = {
                "title": "Review Critical Fault Details",
                "description": "Operators review fault details and telemetry history.",
                "acceptance_criteria": ["Operator can view fault details.", "Unauthorized users are denied."],
            }
            result = ProjectIntelligenceService().generate_qa_test_cases(story, linedefender_profile(), options={"force_provider": "deterministic_fallback"})

        self.assertTrue(result["qa_memory"]["prior_tests"])
        self.assertTrue(result["qa_memory"]["regression_patterns"])
        self.assertEqual(result["memory_context"]["relevantMemories"][0]["artifactType"], "Test Suite")

    def test_deprecated_and_rejected_memory_are_excluded(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            engine = EngineeringMemoryEngine()
            deprecated = approve_and_index(engine, {
                "projectId": "LineDefender",
                "category": "Planning Memory",
                "title": "Deprecated Fault Story",
                "summary": "Old fault detail pattern.",
                "artifactType": "Story",
                "artifactId": "old-story",
                "knowledgeReferences": ["Fault Monitoring", "Telemetry"],
                "confidence": 0.95,
            })
            engine.archive_memory(deprecated["id"], "tester")
            rejected = engine.store_memory({
                "projectId": "LineDefender",
                "category": "Planning Memory",
                "title": "Rejected Fault Story",
                "summary": "Rejected story should not become memory.",
                "artifactType": "Story",
                "artifactId": "bad-story",
                "knowledgeReferences": ["Fault Monitoring"],
                "confidence": 0.95,
                "source": {"status": "Rejected"},
            })
            self.assertFalse(rejected["stored"])
            result = ProjectIntelligenceService().refine_feature(
                {"title": "Critical Fault Detection", "description": "Review fault details with telemetry."},
                linedefender_profile(),
                options={"force_provider": "deterministic_fallback"},
            )

        self.assertEqual(result["memory_context"]["relevantMemories"], [])
        excluded_reasons = [reason for item in result["memory_context"]["excludedMemory"] for reason in item["reasons"]]
        self.assertIn("not_approved_indexed_or_available", excluded_reasons)

    def test_repository_boundary_excludes_unrelated_memory(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_DATA_DIR": temp_dir}, clear=False):
            engine = EngineeringMemoryEngine()
            approve_and_index(engine, {
                "projectId": "LineDefender",
                "category": "Execution Memory",
                "title": "Firmware Rollout Package",
                "summary": "Firmware package should not guide fault detail execution.",
                "artifactType": "Execution Package",
                "artifactId": "firmware-pkg",
                "knowledgeReferences": ["Firmware Update", "Firmware Rollout"],
                "tags": ["firmware", "execution"],
                "confidence": 0.96,
            })
            story = {
                "title": "Display Fault Event Details",
                "description": "Operations users review critical fault details and telemetry context.",
                "acceptance_criteria": ["Fault details are visible."],
            }
            result = ProjectIntelligenceService().build_execution_context(story, linedefender_profile(), options={"force_provider": "deterministic_fallback"})

        self.assertEqual(result["memory_context"]["relevantMemories"], [])
        excluded_reasons = [reason for item in result["memory_context"]["excludedMemory"] for reason in item["reasons"]]
        self.assertIn("outside_current_planning_boundary", excluded_reasons)


if __name__ == "__main__":
    unittest.main()
