"""Persistent Project Intelligence relationship graph."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GRAPH_SCHEMA_VERSION = "project-graph-v1"


class ProjectKnowledgeGraphService:
    """Small JSON-backed graph for planning, QA, and execution traceability."""

    def __init__(self) -> None:
        data_dir = Path(os.getenv("AI_GEN_DATA_DIR", str(Path(__file__).parent.parent / "data")))
        self._graph_dir = data_dir / "project_intelligence"
        self._graph_path = self._graph_dir / "knowledge_graph.json"
        self._graph_dir.mkdir(parents=True, exist_ok=True)

    def get_graph(self) -> dict[str, Any]:
        graph = self._read_graph()
        return {
            "schema_version": graph["schema_version"],
            "version": graph["version"],
            "updated_at": graph["updated_at"],
            "nodes": list(graph["nodes"].values()),
            "relationships": list(graph["relationships"].values()),
        }

    def summary(self, item_id: str = "") -> dict[str, Any]:
        graph = self._read_graph()
        if item_id:
            return self._scoped_summary(graph, item_id)
        nodes = list(graph["nodes"].values())
        relationships = list(graph["relationships"].values())
        counts: dict[str, int] = {}
        for node in nodes:
            counts[node["type"]] = counts.get(node["type"], 0) + 1
        coverage = self.coverage_summary()
        return {
            "version": graph["version"],
            "updated_at": graph["updated_at"],
            "counts": counts,
            "relationship_count": len(relationships),
            "coverage": coverage,
            "chain": {
                "projects": counts.get("Project", 0),
                "epics": counts.get("Epic", 0),
                "features": counts.get("Feature", 0),
                "stories": counts.get("Story", 0),
                "tasks": counts.get("Task", 0),
                "tests": counts.get("Test Case", 0),
                "execution_packages": counts.get("Execution Package", 0),
            },
        }

    def _scoped_summary(self, graph: dict[str, Any], item_id: str) -> dict[str, Any]:
        node = self._resolve_node(graph, item_id)
        if not node:
            return self.summary()
        scoped_nodes = self._summary_scope_nodes(graph, node)
        scoped_ids = {item["id"] for item in scoped_nodes}
        relationships = [
            rel for rel in graph["relationships"].values()
            if rel["from"] in scoped_ids or rel["to"] in scoped_ids
        ]
        counts: dict[str, int] = {}
        for scoped in scoped_nodes:
            counts[scoped["type"]] = counts.get(scoped["type"], 0) + 1
        coverage = self.coverage_summary(item_id)
        return {
            "version": graph["version"],
            "updated_at": graph["updated_at"],
            "counts": counts,
            "relationship_count": len(relationships),
            "coverage": coverage,
            "chain": {
                "projects": counts.get("Project", 0),
                "epics": counts.get("Epic", 0),
                "features": counts.get("Feature", 0),
                "stories": counts.get("Story", 0),
                "tasks": counts.get("Task", 0),
                "tests": counts.get("Test Case", 0),
                "execution_packages": counts.get("Execution Package", 0),
            },
        }

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        graph = self._read_graph()
        before_nodes = len(graph["nodes"])
        before_relationships = len(graph["relationships"])
        project = _as_dict(payload.get("project"))
        epic = _as_dict(payload.get("epic"))
        feature = _as_dict(payload.get("feature"))
        story = _as_dict(payload.get("story"))
        tasks = _as_list(payload.get("tasks"))
        test_cases = _as_list(payload.get("test_cases"))
        acceptance_criteria = _string_list(payload.get("acceptance_criteria") or story.get("acceptance_criteria"))
        execution_package = _as_dict(payload.get("execution_package"))
        modules = _string_list(payload.get("modules") or story.get("affected_modules"))
        flows = _string_list(payload.get("flows") or story.get("affected_flows"))
        components = _string_list(payload.get("components") or story.get("affected_components"))
        documents = _as_list(payload.get("repository_documents"))

        project_id = self._upsert_entity(graph, "Project", project or {"title": "Project Intelligence"}, preferred_id=_node_id("Project", _item_key(project) or "default"))
        epic_id = self._maybe_upsert(graph, "Epic", epic)
        feature_id = self._maybe_upsert(graph, "Feature", feature)
        story_id = self._maybe_upsert(graph, "Story", story)

        if epic_id:
            self._relate(graph, project_id, epic_id, "CONTAINS")
        if epic_id and feature_id:
            self._relate(graph, epic_id, feature_id, "CONTAINS")
        elif feature_id:
            self._relate(graph, project_id, feature_id, "CONTAINS")
        if feature_id and story_id:
            self._relate(graph, feature_id, story_id, "CONTAINS")
        elif story_id:
            self._relate(graph, feature_id or epic_id or project_id, story_id, "CONTAINS")

        for index, criterion in enumerate(acceptance_criteria, start=1):
            ac_id = self._upsert_entity(
                graph,
                "Acceptance Criteria",
                {"title": criterion, "text": criterion, "index": index},
                preferred_id=_node_id("Acceptance Criteria", f"{story_id or project_id}:{index}:{criterion}"),
            )
            if story_id:
                self._relate(graph, story_id, ac_id, "HAS", {"index": index})

        for task in tasks:
            task_dict = _as_dict(task)
            task_id = self._maybe_upsert(graph, "Task", task_dict)
            if task_id and story_id:
                self._relate(graph, story_id, task_id, "CONTAINS")
                self._link_criteria_coverage(graph, story_id, task_id, task_dict, "COVERED_BY_TASK")

        for test_case in test_cases:
            test_dict = _as_dict(test_case)
            test_id = self._maybe_upsert(graph, "Test Case", test_dict)
            if test_id and story_id:
                self._relate(graph, story_id, test_id, "VERIFIED_BY")
                self._link_criteria_coverage(graph, story_id, test_id, test_dict, "COVERED_BY_TEST")

        if execution_package:
            package_id = self._upsert_entity(graph, "Execution Package", execution_package)
            if story_id:
                self._relate(graph, package_id, story_id, "GENERATED_FROM", {"version": execution_package.get("version")})

        for module in modules:
            module_id = self._upsert_entity(graph, "Module", {"title": module})
            if story_id:
                self._relate(graph, story_id, module_id, "IMPACTS")
        for flow in flows:
            flow_id = self._upsert_entity(graph, "Flow", {"title": flow})
            if story_id:
                self._relate(graph, story_id, flow_id, "USES")
        for component in components:
            component_id = self._upsert_entity(graph, "Component", {"title": component})
            if story_id:
                self._relate(graph, story_id, component_id, "AFFECTS")
        for document in documents:
            document_dict = _as_dict(document)
            document_id = self._upsert_entity(graph, "Repository Document", document_dict)
            self._relate(graph, project_id, document_id, "CONTAINS")

        self._bump(graph)
        self._write_graph(graph)
        return {
            "updated": True,
            "nodes_added": len(graph["nodes"]) - before_nodes,
            "relationships_added": len(graph["relationships"]) - before_relationships,
            "summary": self.summary(),
        }

    def ingest_artifact(self, artifact: dict[str, Any]) -> dict[str, Any]:
        artifact_type = _clean_text(artifact.get("artifact_type"))
        payload = artifact.get("payload")
        source_item = _as_dict(artifact.get("source_item"))
        source_type = _clean_text(source_item.get("type"))
        source_node = _item_payload(source_item)
        base: dict[str, Any] = {"project": {"title": "Project Intelligence"}}
        if source_type in {"Epic", "Feature", "Story", "Task"}:
            base[source_type.lower() if source_type != "Story" else "story"] = source_node
        if artifact_type == "Feature" and isinstance(payload, list):
            result = self._ingest_children(source_node, source_type or "Epic", "Feature", payload)
        elif artifact_type == "Story" and isinstance(payload, list):
            result = self._ingest_children(source_node, source_type or "Feature", "Story", payload)
        elif artifact_type == "Task" and isinstance(payload, list):
            result = self._ingest_children(source_node, source_type or "Story", "Task", payload)
        elif artifact_type in {"Test Suite", "Test Plan"} and isinstance(payload, dict):
            story = source_node if source_type == "Story" else _as_dict(payload.get("story"))
            result = self.ingest({
                **base,
                "story": story,
                "acceptance_criteria": story.get("acceptance_criteria") or payload.get("coverage_summary", {}).get("covered_acceptance_criteria"),
                "test_cases": payload.get("test_suite", {}).get("test_cases", []),
                "modules": payload.get("test_suite", {}).get("modules", []),
                "flows": payload.get("test_suite", {}).get("flows", []),
            })
        elif artifact_type == "Execution Package" and isinstance(payload, dict):
            story = source_node if source_type == "Story" else _as_dict(payload.get("context", {}).get("story"))
            context = _as_dict(payload.get("context"))
            result = self.ingest({
                **base,
                "story": story or {"title": context.get("story_summary") or artifact.get("title")},
                "acceptance_criteria": context.get("acceptance_criteria"),
                "modules": context.get("affected_modules"),
                "flows": context.get("affected_flows"),
                "execution_package": {
                    "title": artifact.get("title"),
                    "version": artifact.get("version"),
                    "artifact_id": artifact.get("artifact_id"),
                },
            })
        else:
            result = self.ingest({**base, source_type.lower() if source_type else "story": source_node or {"title": artifact.get("title")}})
        return result

    def query(self, query_type: str, item_id: str = "") -> dict[str, Any]:
        if query_type == "summary":
            return self.summary()
        if query_type == "stories_for_feature":
            return {"stories": self._children(item_id, "Story")}
        if query_type == "tests_for_story":
            return {"test_cases": self._related(item_id, "VERIFIED_BY", "Test Case")}
        if query_type == "tasks_for_story":
            return {"tasks": self._children(item_id, "Task")}
        if query_type == "impacted_modules":
            return {"modules": self._related(item_id, "IMPACTS", "Module")}
        if query_type == "impacted_flows":
            return {"flows": self._related(item_id, "USES", "Flow")}
        if query_type == "execution_history":
            return {"execution_packages": self._incoming(item_id, "GENERATED_FROM", "Execution Package")}
        if query_type == "uncovered_acceptance_criteria":
            return {"acceptance_criteria": self.uncovered_acceptance_criteria(item_id)}
        if query_type == "impact":
            return self.impact_from_graph(item_id)
        if query_type == "coverage":
            return self.coverage_summary(item_id)
        if query_type == "coverage_report":
            return self.coverage_report(item_id)
        if query_type == "gap_report":
            return self.gap_report(item_id)
        if query_type == "regression":
            return self.regression_impact(item_id)
        if query_type == "quality_gate":
            return self.quality_gate(item_id)
        return {"error": f"Unsupported graph query: {query_type}"}

    def uncovered_acceptance_criteria(self, story_id: str = "") -> list[dict[str, Any]]:
        graph = self._read_graph()
        resolved_story_id = self._resolve_node_id(graph, story_id)
        criteria = self._related(resolved_story_id, "HAS", "Acceptance Criteria") if resolved_story_id else [
            node for node in graph["nodes"].values() if node["type"] == "Acceptance Criteria"
        ]
        covered_ids = {
            rel["from"]
            for rel in graph["relationships"].values()
            if rel["type"] in {"COVERED_BY_TEST", "COVERED_BY_TASK"}
        }
        return [criterion for criterion in criteria if criterion["id"] not in covered_ids]

    def coverage_summary(self, story_id: str = "") -> dict[str, Any]:
        graph = self._read_graph()
        resolved_story_id = self._resolve_node_id(graph, story_id)
        criteria = self._related(resolved_story_id, "HAS", "Acceptance Criteria") if resolved_story_id else [
            node for node in graph["nodes"].values() if node["type"] == "Acceptance Criteria"
        ]
        total = len(criteria)
        covered = total - len(self.uncovered_acceptance_criteria(resolved_story_id))
        return {
            "acceptance_criteria_count": total,
            "covered_acceptance_criteria_count": covered,
            "uncovered_acceptance_criteria_count": total - covered,
            "coverage_percent": round((covered / total) * 100) if total else 0,
        }

    def coverage_report(self, item_id: str = "", threshold: int = 80) -> dict[str, Any]:
        graph = self._read_graph()
        stories = self._scope_stories(item_id)
        story_reports = [self._story_coverage_report(graph, story, threshold) for story in stories]
        feature_reports = [self._feature_coverage_report(graph, feature, story_reports, threshold) for feature in self._scope_features(item_id)]
        project_score = _average([report["overall_score"] for report in story_reports])
        return {
            "coverage_report": {
                "item_id": item_id,
                "threshold": threshold,
                "overall_project_coverage": project_score,
                "quality_gate": "pass" if project_score >= threshold and not self.gap_report(item_id)["blocking_gaps"] else "fail",
                "feature_coverage": feature_reports,
                "story_coverage": story_reports,
                "acceptance_criteria_coverage": [
                    criterion
                    for report in story_reports
                    for criterion in report["acceptance_criteria_coverage"]
                ],
                "gap_summary": self.gap_report(item_id),
            }
        }

    def gap_report(self, item_id: str = "") -> dict[str, Any]:
        stories = self._scope_stories(item_id)
        features = self._scope_features(item_id)
        gaps: list[dict[str, Any]] = []
        for story in stories:
            story_id = story["id"]
            criteria = self._related(story_id, "HAS", "Acceptance Criteria")
            tasks = self._children(story_id, "Task")
            tests = self._related(story_id, "VERIFIED_BY", "Test Case")
            execution = self._incoming(story_id, "GENERATED_FROM", "Execution Package")
            if not criteria:
                gaps.append(_gap("story_no_acceptance_criteria", "critical", story, "Story has no acceptance criteria."))
            if not tasks:
                gaps.append(_gap("story_no_tasks", "critical", story, "Story has no implementation tasks."))
            if not tests:
                gaps.append(_gap("story_no_tests", "critical", story, "Story has no QA test cases."))
            if not execution:
                gaps.append(_gap("execution_package_missing", "major", story, "Story has no execution package."))
            for criterion in criteria:
                task_links = self._outgoing(criterion["id"], "COVERED_BY_TASK", "Task")
                test_links = self._outgoing(criterion["id"], "COVERED_BY_TEST", "Test Case")
                if not task_links:
                    gaps.append(_gap("acceptance_criteria_without_tasks", "major", criterion, "Acceptance criterion has no task coverage.", story))
                if not test_links:
                    gaps.append(_gap("acceptance_criteria_without_tests", "major", criterion, "Acceptance criterion has no test coverage.", story))
        for feature in features:
            stories_for_feature = self._children(feature["id"], "Story")
            if len(stories_for_feature) < 4:
                gaps.append(_gap("feature_weak_decomposition", "minor", feature, "Feature has fewer than four stories."))
        return {
            "gaps": gaps,
            "blocking_gaps": [gap for gap in gaps if gap["severity"] == "critical"],
            "gap_count": len(gaps),
            "blocking_gap_count": len([gap for gap in gaps if gap["severity"] == "critical"]),
        }

    def regression_impact(self, story_id: str) -> dict[str, Any]:
        impact = self.impact_from_graph(story_id)
        regression_items = {
            "tasks": impact["tasks"],
            "test_cases": impact["test_cases"],
            "execution_packages": impact["execution_packages"],
            "modules": impact["modules"],
            "flows": impact["flows"],
            "components": impact["components"],
        }
        regression_required = any(regression_items.values())
        return {
            "story_id": story_id,
            "regression_required": regression_required,
            "reason": "Story has downstream tasks, tests, execution packages, modules, or flows." if regression_required else "No persisted downstream relationships were found.",
            "regression_scope": regression_items,
            "coverage_impact": impact["coverage"],
        }

    def quality_gate(self, item_id: str, threshold: int = 80) -> dict[str, Any]:
        story_reports = [self._story_coverage_report(self._read_graph(), story, threshold) for story in self._scope_stories(item_id)]
        if not story_reports:
            return {
                "status": "fail",
                "threshold": threshold,
                "score": 0,
                "reasons": ["No stories were found for this scope."],
            }
        score = _average([report["overall_score"] for report in story_reports])
        gaps = self.gap_report(item_id)
        reasons = [gap["message"] for gap in gaps["blocking_gaps"]]
        if score < threshold:
            reasons.append(f"Coverage score {score}% is below threshold {threshold}%.")
        return {
            "status": "pass" if score >= threshold and not gaps["blocking_gaps"] else "fail",
            "threshold": threshold,
            "score": score,
            "reasons": reasons,
        }

    def impact_from_graph(self, story_id: str) -> dict[str, Any]:
        graph = self._read_graph()
        resolved_story_id = self._resolve_node_id(graph, story_id)
        return {
            "tasks": self._children(resolved_story_id, "Task"),
            "test_cases": self._related(resolved_story_id, "VERIFIED_BY", "Test Case"),
            "execution_packages": self._incoming(resolved_story_id, "GENERATED_FROM", "Execution Package"),
            "modules": self._related(resolved_story_id, "IMPACTS", "Module"),
            "flows": self._related(resolved_story_id, "USES", "Flow"),
            "components": self._related(resolved_story_id, "AFFECTS", "Component"),
            "coverage": self.coverage_summary(resolved_story_id),
        }

    def _story_coverage_report(self, graph: dict[str, Any], story: dict[str, Any], threshold: int) -> dict[str, Any]:
        story_id = story["id"]
        criteria = self._related(story_id, "HAS", "Acceptance Criteria")
        tasks = self._children(story_id, "Task")
        tests = self._related(story_id, "VERIFIED_BY", "Test Case")
        execution = self._incoming(story_id, "GENERATED_FROM", "Execution Package")
        criterion_reports = []
        for criterion in criteria:
            task_links = self._outgoing(criterion["id"], "COVERED_BY_TASK", "Task")
            test_links = self._outgoing(criterion["id"], "COVERED_BY_TEST", "Test Case")
            if task_links and test_links:
                status = "Covered"
            elif task_links or test_links:
                status = "Partially Covered"
            else:
                status = "Not Covered"
            criterion_reports.append({
                "id": criterion["id"],
                "title": criterion["title"],
                "status": status,
                "covered_by_tasks": task_links,
                "covered_by_tests": test_links,
            })
        ac_score = _coverage_percent(len([item for item in criterion_reports if item["status"] == "Covered"]), len(criterion_reports))
        task_score = _coverage_percent(len([item for item in criterion_reports if item["covered_by_tasks"]]), len(criterion_reports))
        test_score = _coverage_percent(len([item for item in criterion_reports if item["covered_by_tests"]]), len(criterion_reports))
        execution_score = 100 if execution else 0
        story_score = _average([score for score in [ac_score, task_score, test_score, execution_score] if criteria or score])
        return {
            "story_id": story_id,
            "title": story["title"],
            "acceptance_criteria_count": len(criteria),
            "task_count": len(tasks),
            "test_count": len(tests),
            "execution_package_count": len(execution),
            "acceptance_criteria_score": ac_score,
            "task_coverage_score": task_score,
            "test_coverage_score": test_score,
            "execution_coverage_score": execution_score,
            "overall_score": story_score,
            "quality_gate": "pass" if story_score >= threshold and criteria and tasks and tests and execution else "fail",
            "acceptance_criteria_coverage": criterion_reports,
        }

    def _feature_coverage_report(self, graph: dict[str, Any], feature: dict[str, Any], story_reports: list[dict[str, Any]], threshold: int) -> dict[str, Any]:
        stories = self._children(feature["id"], "Story")
        story_ids = {story["id"] for story in stories}
        scoped_reports = [report for report in story_reports if report["story_id"] in story_ids]
        expected_min_stories = 4
        completeness = min(100, round((len(stories) / expected_min_stories) * 100)) if expected_min_stories else 100
        score = _average([report["overall_score"] for report in scoped_reports] + [completeness])
        return {
            "feature_id": feature["id"],
            "title": feature["title"],
            "story_count": len(stories),
            "story_completeness_score": completeness,
            "task_coverage_score": _average([report["task_coverage_score"] for report in scoped_reports]),
            "test_coverage_score": _average([report["test_coverage_score"] for report in scoped_reports]),
            "execution_coverage_score": _average([report["execution_coverage_score"] for report in scoped_reports]),
            "overall_score": score,
            "quality_gate": "pass" if score >= threshold and len(stories) >= expected_min_stories else "fail",
        }

    def _scope_stories(self, item_id: str = "") -> list[dict[str, Any]]:
        graph = self._read_graph()
        if not item_id:
            return [node for node in graph["nodes"].values() if node["type"] == "Story"]
        node = self._resolve_node(graph, item_id)
        if not node:
            return []
        if node["type"] == "Story":
            return [node]
        if node["type"] == "Feature":
            return self._children(item_id, "Story")
        if node["type"] == "Epic":
            return [story for feature in self._children(item_id, "Feature") for story in self._children(feature["id"], "Story")]
        if node["type"] == "Project":
            return [story for feature in [child for epic in self._children(item_id, "Epic") for child in self._children(epic["id"], "Feature")] for story in self._children(feature["id"], "Story")]
        return []

    def _scope_features(self, item_id: str = "") -> list[dict[str, Any]]:
        graph = self._read_graph()
        if not item_id:
            return [node for node in graph["nodes"].values() if node["type"] == "Feature"]
        node = self._resolve_node(graph, item_id)
        if not node:
            return []
        if node["type"] == "Feature":
            return [node]
        if node["type"] == "Epic":
            return self._children(item_id, "Feature")
        if node["type"] == "Project":
            return [feature for epic in self._children(item_id, "Epic") for feature in self._children(epic["id"], "Feature")]
        return []

    def _ingest_children(self, source_item: dict[str, Any], source_type: str, child_type: str, children: list[Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {"project": {"title": "Project Intelligence"}}
        if source_type == "Epic":
            payload["epic"] = source_item
        elif source_type == "Feature":
            payload["feature"] = source_item
        elif source_type == "Story":
            payload["story"] = source_item
        result = self.ingest(payload)
        graph = self._read_graph()
        parent_id = self._maybe_upsert(graph, source_type, source_item)
        for child in children:
            child_dict = _as_dict(child)
            child_id = self._maybe_upsert(graph, child_type, child_dict)
            if parent_id and child_id:
                self._relate(graph, parent_id, child_id, "CONTAINS")
            if child_type == "Story":
                for index, criterion in enumerate(_string_list(child_dict.get("acceptanceCriteria") or child_dict.get("acceptance_criteria")), start=1):
                    ac_id = self._upsert_entity(graph, "Acceptance Criteria", {"title": criterion, "text": criterion, "index": index})
                    self._relate(graph, child_id, ac_id, "HAS", {"index": index})
            if child_type == "Task":
                self._link_criteria_coverage(graph, parent_id or "", child_id or "", child_dict, "COVERED_BY_TASK")
        self._bump(graph)
        self._write_graph(graph)
        return {**result, "summary": self.summary()}

    def _children(self, node_id: str, child_type: str) -> list[dict[str, Any]]:
        return self._related(node_id, "CONTAINS", child_type)

    def _related(self, from_id: str, relationship_type: str, to_type: str = "") -> list[dict[str, Any]]:
        graph = self._read_graph()
        if not from_id:
            return []
        return [
            graph["nodes"][rel["to"]]
            for rel in graph["relationships"].values()
            if rel["from"] == from_id
            and rel["type"] == relationship_type
            and rel["to"] in graph["nodes"]
            and (not to_type or graph["nodes"][rel["to"]]["type"] == to_type)
        ]

    def _outgoing(self, from_id: str, relationship_type: str, to_type: str = "") -> list[dict[str, Any]]:
        return self._related(from_id, relationship_type, to_type)

    def _incoming(self, to_id: str, relationship_type: str, from_type: str = "") -> list[dict[str, Any]]:
        graph = self._read_graph()
        if not to_id:
            return []
        return [
            graph["nodes"][rel["from"]]
            for rel in graph["relationships"].values()
            if rel["to"] == to_id
            and rel["type"] == relationship_type
            and rel["from"] in graph["nodes"]
            and (not from_type or graph["nodes"][rel["from"]]["type"] == from_type)
        ]

    def _maybe_upsert(self, graph: dict[str, Any], entity_type: str, item: dict[str, Any]) -> str:
        if not item:
            return ""
        return self._upsert_entity(graph, entity_type, item)

    def _upsert_entity(self, graph: dict[str, Any], entity_type: str, item: dict[str, Any], preferred_id: str = "") -> str:
        node_id = preferred_id or _node_id(entity_type, _item_key(item))
        now = _now_iso()
        existing = graph["nodes"].get(node_id, {})
        payload = _as_dict(existing.get("payload"))
        payload.update({key: value for key, value in item.items() if value not in (None, "", [], {})})
        graph["nodes"][node_id] = {
            "id": node_id,
            "type": entity_type,
            "title": _clean_text(item.get("title") or item.get("name") or item.get("text") or existing.get("title") or entity_type),
            "payload": payload,
            "version": int(existing.get("version", 0) or 0) + (1 if existing else 0),
            "created_on": existing.get("created_on") or now,
            "updated_on": now,
        }
        return node_id

    def _relate(self, graph: dict[str, Any], from_id: str, to_id: str, relationship_type: str, properties: dict[str, Any] | None = None) -> str:
        rel_id = _relationship_id(from_id, relationship_type, to_id)
        existing = graph["relationships"].get(rel_id, {})
        graph["relationships"][rel_id] = {
            "id": rel_id,
            "from": from_id,
            "to": to_id,
            "type": relationship_type,
            "properties": {**_as_dict(existing.get("properties")), **(properties or {})},
            "created_on": existing.get("created_on") or _now_iso(),
            "updated_on": _now_iso(),
        }
        return rel_id

    def _link_criteria_coverage(self, graph: dict[str, Any], story_id: str, artifact_id: str, item: dict[str, Any], relationship_type: str) -> None:
        if not story_id or not artifact_id:
            return
        criteria = [
            graph["nodes"][rel["to"]]
            for rel in graph["relationships"].values()
            if rel["from"] == story_id and rel["type"] == "HAS" and rel["to"] in graph["nodes"]
        ]
        item_text = " ".join(_string_list(item.get("acceptanceCriteria") or item.get("acceptance_criteria") or item.get("covers_acceptance_criteria")) + [_clean_text(item.get("title")), _clean_text(item.get("description"))]).lower()
        explicit_indexes = [int(value) for value in item.get("covers_acceptance_criteria", []) if isinstance(value, int)] if isinstance(item.get("covers_acceptance_criteria"), list) else []
        for criterion in criteria:
            index = int(_as_dict(criterion.get("payload")).get("index", 0) or 0)
            text = _clean_text(_as_dict(criterion.get("payload")).get("text") or criterion.get("title")).lower()
            if explicit_indexes:
                matched = index in explicit_indexes
            else:
                matched = bool(text and (text in item_text or any(token in item_text for token in text.split()[:4])))
            if matched:
                self._relate(graph, criterion["id"], artifact_id, relationship_type, {"coverage": "covered"})

    def _read_graph(self) -> dict[str, Any]:
        if not self._graph_path.exists():
            return _empty_graph()
        try:
            payload = json.loads(self._graph_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _empty_graph()
        nodes = payload.get("nodes") if isinstance(payload.get("nodes"), dict) else {}
        relationships = payload.get("relationships") if isinstance(payload.get("relationships"), dict) else {}
        return {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "version": int(payload.get("version", 0) or 0),
            "updated_at": _clean_text(payload.get("updated_at")),
            "nodes": {key: value for key, value in nodes.items() if isinstance(value, dict)},
            "relationships": {key: value for key, value in relationships.items() if isinstance(value, dict)},
        }

    def _write_graph(self, graph: dict[str, Any]) -> None:
        self._graph_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")

    def _bump(self, graph: dict[str, Any]) -> None:
        graph["schema_version"] = GRAPH_SCHEMA_VERSION
        graph["version"] = int(graph.get("version", 0) or 0) + 1
        graph["updated_at"] = _now_iso()

    def _resolve_node_id(self, graph: dict[str, Any], item_id: str) -> str:
        node = self._resolve_node(graph, item_id)
        return node["id"] if node else ""

    def _resolve_node(self, graph: dict[str, Any], item_id: str) -> dict[str, Any] | None:
        clean_item_id = _clean_text(item_id)
        if not clean_item_id:
            return None
        direct = graph["nodes"].get(clean_item_id)
        if isinstance(direct, dict):
            return direct
        for node in graph["nodes"].values():
            payload = _as_dict(node.get("payload"))
            payload_id = _clean_text(payload.get("id"))
            title = _clean_text(node.get("title"))
            if clean_item_id == payload_id or clean_item_id == title:
                return node
        return None

    def _summary_scope_nodes(self, graph: dict[str, Any], node: dict[str, Any]) -> list[dict[str, Any]]:
        node_type = _clean_text(node.get("type"))
        scoped: list[dict[str, Any]] = []

        def add(items: list[dict[str, Any]]) -> None:
            for item in items:
                if item and all(existing["id"] != item["id"] for existing in scoped):
                    scoped.append(item)

        add([node])
        if node_type == "Task":
            stories = self._incoming(node["id"], "CONTAINS", "Story")
            add(stories)
            features = [feature for story in stories for feature in self._incoming(story["id"], "CONTAINS", "Feature")]
            add(features)
            epics = [epic for feature in features for epic in self._incoming(feature["id"], "CONTAINS", "Epic")]
            add(epics)
            add([project for epic in epics for project in self._incoming(epic["id"], "CONTAINS", "Project")])
            if stories:
                add(self._related(stories[0]["id"], "VERIFIED_BY", "Test Case"))
                add(self._incoming(stories[0]["id"], "GENERATED_FROM", "Execution Package"))
            return scoped
        if node_type == "Story":
            add(self._children(node["id"], "Task"))
            add(self._related(node["id"], "VERIFIED_BY", "Test Case"))
            add(self._incoming(node["id"], "GENERATED_FROM", "Execution Package"))
            features = self._incoming(node["id"], "CONTAINS", "Feature")
            add(features)
            epics = [epic for feature in features for epic in self._incoming(feature["id"], "CONTAINS", "Epic")]
            add(epics)
            add([project for epic in epics for project in self._incoming(epic["id"], "CONTAINS", "Project")])
            return scoped
        if node_type == "Feature":
            stories = self._children(node["id"], "Story")
            add(stories)
            add([task for story in stories for task in self._children(story["id"], "Task")])
            add([test for story in stories for test in self._related(story["id"], "VERIFIED_BY", "Test Case")])
            add([pkg for story in stories for pkg in self._incoming(story["id"], "GENERATED_FROM", "Execution Package")])
            epics = self._incoming(node["id"], "CONTAINS", "Epic")
            add(epics)
            add([project for epic in epics for project in self._incoming(epic["id"], "CONTAINS", "Project")])
            return scoped
        if node_type == "Epic":
            features = self._children(node["id"], "Feature")
            add(features)
            stories = [story for feature in features for story in self._children(feature["id"], "Story")]
            add(stories)
            add([task for story in stories for task in self._children(story["id"], "Task")])
            add([test for story in stories for test in self._related(story["id"], "VERIFIED_BY", "Test Case")])
            add([pkg for story in stories for pkg in self._incoming(story["id"], "GENERATED_FROM", "Execution Package")])
            add(self._incoming(node["id"], "CONTAINS", "Project"))
            return scoped
        if node_type == "Project":
            epics = self._children(node["id"], "Epic")
            add(epics)
            features = [feature for epic in epics for feature in self._children(epic["id"], "Feature")]
            add(features)
            stories = [story for feature in features for story in self._children(feature["id"], "Story")]
            add(stories)
            add([task for story in stories for task in self._children(story["id"], "Task")])
            add([test for story in stories for test in self._related(story["id"], "VERIFIED_BY", "Test Case")])
            add([pkg for story in stories for pkg in self._incoming(story["id"], "GENERATED_FROM", "Execution Package")])
            return scoped
        return scoped


def _empty_graph() -> dict[str, Any]:
    return {"schema_version": GRAPH_SCHEMA_VERSION, "version": 0, "updated_at": "", "nodes": {}, "relationships": {}}


def _node_id(entity_type: str, key: str) -> str:
    digest = hashlib.sha256(f"{entity_type}|{key}".encode("utf-8")).hexdigest()[:16]
    return f"{_slug(entity_type)}_{digest}"


def _relationship_id(from_id: str, relationship_type: str, to_id: str) -> str:
    digest = hashlib.sha256(f"{from_id}|{relationship_type}|{to_id}".encode("utf-8")).hexdigest()[:20]
    return f"rel_{digest}"


def _item_key(item: dict[str, Any]) -> str:
    return _clean_text(item.get("id") or item.get("azure_id") or item.get("artifact_id") or item.get("title") or item.get("name") or item.get("text") or json.dumps(item, sort_keys=True))


def _item_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _clean_text(item.get("id") or item.get("azure_id")),
        "title": _clean_text(item.get("title") or item.get("name")),
        "description": _clean_text(item.get("description")),
        "acceptance_criteria": _string_list(item.get("acceptanceCriteria") or item.get("acceptance_criteria")),
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [_clean_text(item) for item in value if _clean_text(item)]
    return []


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_") or "node"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coverage_percent(covered: int, total: int) -> int:
    return round((covered / total) * 100) if total else 0


def _average(values: list[int]) -> int:
    numbers = [int(value) for value in values if value is not None]
    return round(sum(numbers) / len(numbers)) if numbers else 0


def _gap(gap_type: str, severity: str, node: dict[str, Any], message: str, parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": gap_type,
        "severity": severity,
        "item_id": node.get("id", ""),
        "item_type": node.get("type", ""),
        "title": node.get("title", ""),
        "parent_id": (parent or {}).get("id", ""),
        "parent_title": (parent or {}).get("title", ""),
        "message": message,
    }


project_knowledge_graph_service = ProjectKnowledgeGraphService()
