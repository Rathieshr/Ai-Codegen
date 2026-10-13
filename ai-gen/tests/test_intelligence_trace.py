import tempfile
import unittest
from pathlib import Path

from backend.intelligence_trace import TraceEngine


class IntelligenceTraceTests(unittest.TestCase):
    def test_record_decision_stores_explainability_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = TraceEngine(Path(temp_dir) / "trace.json")
            trace = engine.record_decision(
                project_id="LineDefender",
                artifact_type="Feature",
                artifact_id="feature-1",
                artifact_title="Critical Fault Detection",
                stage="Planning",
                source="Planning Intelligence",
                decision="Generate Story Recommendations",
                reason="Selected Fault Monitoring because the feature is about critical fault review.",
                confidence=0.91,
                evidence=["Fault Monitoring capability matched feature intent"],
                memory_used=[{"title": "Prior Fault Detail Story", "artifactType": "Story"}],
                repository_evidence=[{"name": "Fault Monitoring", "type": "Module", "reason": "fault intent"}],
                graph_evidence=[{"name": "Fault Event Review Flow", "type": "Flow"}],
                validation_result={"status": "Approved"},
                prompt_version="phi-small-v1",
                latency_ms=123,
                model="Phi-4",
                token_usage={"prompt_tokens": 300, "completion_tokens": 90},
            )

        self.assertEqual(trace["projectId"], "LineDefender")
        self.assertEqual(trace["decision"], "Generate Story Recommendations")
        self.assertEqual(trace["memoryUsed"][0]["title"], "Prior Fault Detail Story")
        self.assertEqual(trace["repositoryEvidence"][0]["name"], "Fault Monitoring")
        self.assertEqual(trace["graphEvidence"][0]["name"], "Fault Event Review Flow")
        self.assertEqual(trace["validationResult"]["status"], "Approved")
        self.assertEqual(trace["model"], "Phi-4")
        self.assertEqual(trace["tokenUsage"]["prompt_tokens"], 300)

    def test_search_filters_by_artifact_module_decision_and_project(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = TraceEngine(Path(temp_dir) / "trace.json")
            engine.record_decision(
                project_id="LineDefender",
                artifact_type="Feature",
                artifact_id="feature-1",
                artifact_title="Critical Fault Detection",
                stage="Planning",
                source="Planning Intelligence",
                decision="Generate Story Recommendations",
                reason="Fault Monitoring was selected.",
                confidence=0.8,
                repository_evidence=[{"name": "Fault Monitoring", "type": "Module"}],
            )
            engine.record_decision(
                project_id="OtherProject",
                artifact_type="Feature",
                artifact_id="feature-2",
                artifact_title="Critical Fault Detection",
                stage="Planning",
                source="Planning Intelligence",
                decision="Generate Story Recommendations",
                reason="Fault Monitoring was selected.",
                confidence=0.8,
                repository_evidence=[{"name": "Fault Monitoring", "type": "Module"}],
            )
            result = engine.search({
                "projectId": "LineDefender",
                "artifactType": "Feature",
                "decision": "Generate Story",
                "module": "Fault Monitoring",
            })

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["traces"][0]["artifactId"], "feature-1")
        self.assertIn("module", result["traces"][0]["matchReasons"])

    def test_timeline_and_explain_group_trace_stages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = TraceEngine(Path(temp_dir) / "trace.json")
            engine.record_decision(
                project_id="LineDefender",
                artifact_type="Story",
                artifact_id="story-1",
                artifact_title="Review Critical Fault Details",
                stage="Planning",
                source="Planning Intelligence",
                decision="Generate Task Recommendations",
                reason="Story approved for task breakdown.",
                confidence=0.82,
            )
            engine.record_decision(
                project_id="LineDefender",
                artifact_type="Story",
                artifact_id="story-1",
                artifact_title="Review Critical Fault Details",
                stage="Execution",
                source="Execution Intelligence",
                decision="Build Execution Package",
                reason="Task and story DNA selected a compact capsule.",
                confidence=0.86,
            )
            timeline = engine.timeline("story-1", "LineDefender")
            explanation = engine.explain("story-1", "Build Execution Package", "LineDefender")

        stages = {step["stage"]: step for step in timeline["timeline"]}
        self.assertEqual(stages["Planning"]["status"], "Complete")
        self.assertEqual(stages["Execution"]["status"], "Complete")
        self.assertEqual(stages["QA"]["status"], "Pending")
        self.assertEqual(explanation["count"], 1)
        self.assertEqual(explanation["traces"][0]["stage"], "Execution")

    def test_diagnostics_summary_counts_sources_and_stages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = TraceEngine(Path(temp_dir) / "trace.json")
            engine.record_decision(
                project_id="LineDefender",
                artifact_type="Epic",
                artifact_id="epic-1",
                artifact_title="Fault Monitoring",
                stage="Planning",
                source="Planning Intelligence",
                decision="Generate Features",
                reason="Epic approved for feature generation.",
                confidence=0.9,
            )
            engine.record_decision(
                project_id="LineDefender",
                artifact_type="Story",
                artifact_id="story-1",
                artifact_title="Review Fault Details",
                stage="QA",
                source="QA Intelligence",
                decision="Generate Test Suite",
                reason="QA analysis requested.",
                confidence=0.85,
            )
            summary = engine.diagnostics_summary()

        self.assertEqual(summary["traceCount"], 2)
        self.assertEqual(summary["byStage"]["Planning"], 1)
        self.assertEqual(summary["byStage"]["QA"], 1)
        self.assertEqual(summary["bySource"]["QA Intelligence"], 1)


if __name__ == "__main__":
    unittest.main()
