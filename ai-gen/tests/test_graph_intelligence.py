from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.intelligence.graph import (
    EngineeringGraph,
    GraphBuilder,
    GraphDiagnostics,
    GraphEdge,
    GraphNode,
    GraphQuery,
    GraphStore,
    GraphTraverser,
)


class GraphIntelligenceTests(unittest.TestCase):
    def _sample_graph(self) -> EngineeringGraph:
        return GraphBuilder().build_engineering_graph(
            project_profile={"project_id": "line", "project_name": "LineDefender"},
            knowledge_registry={
                "applications": [{"name": "Operations Dashboard"}],
                "modules": [{"name": "Fault Monitoring"}, {"name": "Telemetry"}],
                "flows": [{"name": "Fault Event Review Flow"}],
                "standards": [{"name": "Role-based access control"}],
            },
            repository_snapshot={
                "repository": "LineDefender",
                "source_files": [{"path": "src/fault/FaultEventController.cs"}],
            },
            planning_artifacts=[
                {"id": 109, "type": "Epic", "title": "Real-Time Fault Event Monitoring"},
                {
                    "id": 201,
                    "type": "Feature",
                    "parent_id": 109,
                    "parent_type": "Epic",
                    "title": "Critical Fault Detection",
                    "modules": ["Fault Monitoring"],
                    "flows": ["Fault Event Review Flow"],
                    "personas": ["Operations User"],
                },
                {
                    "id": 301,
                    "type": "Story",
                    "parent_id": 201,
                    "parent_type": "Feature",
                    "title": "Open critical fault event details",
                    "modules": ["Fault Monitoring"],
                    "flows": ["Fault Event Review Flow"],
                },
                {
                    "id": 401,
                    "type": "Task",
                    "parent_id": 301,
                    "parent_type": "Story",
                    "title": "Add fault details API response mapping",
                },
            ],
            context_capsules=[
                {
                    "capsuleId": "capsule-301",
                    "capsuleType": "execution",
                    "sourceWorkItemId": 301,
                    "selectedModules": ["Fault Monitoring"],
                    "selectedFlows": ["Fault Event Review Flow"],
                    "selectedDependencies": ["Telemetry freshness"],
                    "relevantFiles": [{"path": "src/fault/FaultEventController.cs", "confidence": 0.91}],
                }
            ],
            execution_artifacts=[
                {
                    "artifact_id": "exec-301",
                    "title": "Fault details execution package",
                    "context_capsule": {"capsuleId": "capsule-301"},
                    "modules": ["Fault Monitoring"],
                    "flows": ["Fault Event Review Flow"],
                }
            ],
            validation_reports=[
                {
                    "report_id": "validation-301",
                    "sourceWorkItemId": 301,
                    "status": "Approved",
                }
            ],
        )

    def test_builder_creates_project_knowledge_and_repository_nodes(self) -> None:
        graph = self._sample_graph()

        self.assertIn("Project:line", graph.nodes)
        self.assertEqual(len(graph.nodes_by_type("Module")), 2)
        self.assertEqual(len(graph.nodes_by_type("Flow")), 1)
        self.assertEqual(len(graph.nodes_by_type("File")), 1)
        self.assertTrue(graph.edges_by_type("references"))

    def test_builder_persists_work_item_hierarchy(self) -> None:
        graph = self._sample_graph()
        path = GraphTraverser(graph).shortest_path(
            "Project:line",
            "Task:401",
            edge_types={"contains"},
        )

        self.assertEqual([node["type"] for node in path], ["Project", "Epic", "Feature", "Story", "Task"])

    def test_capsule_links_to_relevant_context_without_inventing_files(self) -> None:
        graph = self._sample_graph()
        capsule_id = next(node.id for node in graph.nodes_by_type("ContextCapsule"))
        refs = GraphQuery(graph).neighbors(capsule_id)
        names = {item["name"] for item in refs}

        self.assertIn("Fault Monitoring", names)
        self.assertIn("Fault Event Review Flow", names)
        self.assertIn("src/fault/FaultEventController.cs", names)
        self.assertNotIn("Firmware Management", names)

    def test_execution_package_is_generated_from_context_capsule(self) -> None:
        graph = self._sample_graph()
        package = graph.nodes_by_type("ExecutionPackage")[0]
        outgoing = graph.outgoing(package.id, "generated_from")

        self.assertEqual(len(outgoing), 1)
        self.assertEqual(graph.nodes[outgoing[0].to_node].type, "ContextCapsule")

    def test_validation_report_validates_story(self) -> None:
        graph = self._sample_graph()
        story_edges = graph.outgoing("Story:301", "validated_by")

        self.assertEqual(len(story_edges), 1)
        self.assertEqual(graph.nodes[story_edges[0].to_node].type, "ValidationReport")

    def test_query_and_traversal_handle_cycles(self) -> None:
        graph = EngineeringGraph()
        graph.add_node(GraphNode("A", "Module", "A"))
        graph.add_node(GraphNode("B", "Flow", "B"))
        graph.add_edge(GraphEdge("", "A", "B", "uses"))
        graph.add_edge(GraphEdge("", "B", "A", "related_to"))

        result = GraphTraverser(graph).traverse("A", depth=3)

        self.assertEqual([node["id"] for node in result], ["B"])

    def test_diagnostics_reports_missing_endpoints_and_isolated_nodes(self) -> None:
        graph = EngineeringGraph()
        graph.add_node(GraphNode("A", "Module", "A"))
        graph.add_node(GraphNode("C", "Flow", "C"))
        graph.add_edge(GraphEdge("", "A", "B", "uses"), require_nodes=False)

        summary = GraphDiagnostics(graph).summary()

        self.assertEqual(len(summary["missing_endpoint_edges"]), 1)
        self.assertEqual(summary["isolated_nodes"], ["C"])

    def test_graph_store_round_trips_json(self) -> None:
        graph = self._sample_graph()
        with tempfile.TemporaryDirectory() as temp_dir:
            store = GraphStore(Path(temp_dir) / "engineering_graph.json")
            saved = store.save(graph)
            loaded = store.load()

        self.assertGreater(saved["node_count"], 0)
        self.assertEqual(len(loaded.nodes), len(graph.nodes))
        self.assertEqual(len(loaded.edges), len(graph.edges))


if __name__ == "__main__":
    unittest.main()
