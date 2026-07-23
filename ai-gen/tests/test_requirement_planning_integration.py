from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.engineering_estimation import EngineeringEstimationEngine, EngineeringEstimationRepository
from backend.platform.shared import JsonMapStore
from backend.planning_integration import RequirementPlanningService, build_requirement_planning_router
from backend.planning_context import PlanningContextService, build_planning_context_router
from backend.planning_recommendation import PlanningRecommendationService, build_planning_recommendation_router
from backend.planning_proposal import PlanningProposalService, build_planning_proposal_router
from backend.planning_integration import IntelligentPlanningEngine
from backend.repository_intelligence.application import RepositoryDetectionService
from backend.repository_intelligence.domain import Repository, RepositorySnapshot
from backend.repository_intelligence.infrastructure import FileBackedRepositoryService, FileBackedSnapshotService
from backend.requirement_analysis import RequirementAnalysisService
from backend.requirement_intake import RequirementIngestionService, RequirementIntakeService


CONTENT = """Business Goal:
Reduce the time required to identify unhealthy devices.
Functional Requirements:
- Operations users must filter devices by health status.
Non Functional Requirements:
- Results must load within 2 seconds.
Acceptance Criteria:
- Filtering by Offline returns only offline devices.
Dependencies:
- Requires the Device Health API service.
Risks:
- Stale telemetry may delay status changes.
"""


class ContextSpy:
    def __init__(self):
        self.requests = []

    def orchestrate(self, request):
        self.requests.append(request)
        return {
            "capsuleId": f"capsule-{len(self.requests)}", "status": "Ready", "confidence": 0.91,
            "freshnessStatus": "Fresh", "sourceSummary": [
                {"sourceType": "Repository", "available": True, "selectedCount": 1, "freshness": "Fresh", "version": "v3"},
                {"sourceType": "EngineeringMemory", "available": True, "selectedCount": 0, "freshness": "Fresh", "version": "1"},
            ], "warnings": [], "blockers": [],
        }


class EmptyMemory:
    def find_relevant_memory(self, _query):
        return {"results": [], "count": 0}


class RequirementPlanningIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.repositories = FileBackedRepositoryService(root / "repositories.json")
        self.snapshots = FileBackedSnapshotService(root / "snapshots.json")
        self.repositories.create_repository(Repository(
            repository_id="device-repository", name="Device Operations", project_id="gridhub",
            url="https://dev.azure.com/hei/gridhub/_git/device-operations",
            metadata={"domain": "device health telemetry operations"},
        ))
        self.snapshots.save_snapshot(RepositorySnapshot(
            snapshot_id="snapshot-device-v3", repository_id="device-repository", version=3,
            modules=["Device Health", "Telemetry"], languages={"TypeScript": 20, "C#": 12}, total_files=32,
        ))
        self.ingestion = RequirementIngestionService(
            JsonMapStore(root / "requirement-contexts.json"),
            work_item_provider=lambda _project, _item: {
                "title": "Device Health Work Item", "description": CONTENT,
                "acceptanceCriteria": ["Filtering by Offline returns only offline devices."], "revision": 7,
            },
        )
        detector = RepositoryDetectionService(
            repository_service=self.repositories, snapshot_service=self.snapshots, memory_engine=EmptyMemory(),
            suggestion_store=JsonMapStore(root / "repository-suggestions.json"),
            override_store=JsonMapStore(root / "repository-overrides.json"),
            requirement_ingestion=self.ingestion,
        )
        self.analysis = RequirementAnalysisService(
            JsonMapStore(root / "analyses.json"), requirement_ingestion=self.ingestion, repository_detector=detector,
        )
        self.context = ContextSpy()
        self.artifacts = []

        def write_artifact(item):
            record = {
                **item, "artifact_id": f"planning-pack-{len(self.artifacts) + 1}",
                "version": 1, "created_on": "2026-07-20T00:00:00Z",
            }
            self.artifacts.append(record)
            return record

        self.intake = RequirementIntakeService(
            JsonMapStore(root / "intake.json"), context_orchestrator=self.context,
            artifact_writer=write_artifact, ingestion_service=self.ingestion, analysis_service=self.analysis,
        )
        self.estimation = EngineeringEstimationEngine(EngineeringEstimationRepository(
            JsonMapStore(root / "estimates.json"), JsonMapStore(root / "outcomes.json"),
        ))
        repository_application = type("RepositoryApplication", (), {
            "get_current_snapshot": lambda _self, repository_id: self.snapshots.get_latest_snapshot(repository_id).to_dict(),
            "get_repository": lambda _self, repository_id: self.repositories.get_repository(repository_id).to_dict(),
            "get_graph": lambda _self, repository_id: {
                "graphId": f"graph-{repository_id}",
                "nodes": [
                    {"id": "module-device", "type": "Module", "name": "Device Health"},
                    {"id": "api-device", "type": "API", "name": "Device Health API"},
                    {"id": "test-device", "type": "Test", "name": "Device Health Filtering Tests"},
                ],
            },
        })()
        planning_engine = IntelligentPlanningEngine(
            work_item_provider=lambda _project: [
                {"workItemId": 88, "workItemType": "Feature", "title": "Device Health Dashboard", "revision": 3, "state": "Active"},
            ],
            iteration_provider=lambda _project: [{"id": "iteration-1", "name": "Sprint 12", "timeFrame": "Current"}],
            memory_provider=lambda _query: {
                "results": [{
                    "id": "memory-1", "title": "Device Health Filtering Pattern",
                    "category": "Planning Memory", "artifactType": "Story",
                    "version": 2, "confidence": 0.91, "searchScore": 94,
                }],
            },
        )
        self.planning_context = PlanningContextService(
            JsonMapStore(root / "planning-contexts.json"),
            requirement_ingestion=self.ingestion,
            requirement_analysis=self.analysis,
            intelligence_engine=planning_engine,
            repository_intelligence=repository_application,
        )
        self.planning_recommendation = PlanningRecommendationService(
            JsonMapStore(root / "planning-recommendations.json"),
            planning_context_service=self.planning_context,
        )
        self.service = RequirementPlanningService(
            JsonMapStore(root / "requirement-planning.json"),
            requirement_ingestion=self.ingestion, requirement_analysis=self.analysis,
            requirement_intake=self.intake, estimation_engine=self.estimation,
            artifact_provider=lambda: {"artifacts": self.artifacts, "count": len(self.artifacts)},
            repository_intelligence=repository_application,
            intelligence_engine=planning_engine,
        )
        self.proposal = PlanningProposalService(
            JsonMapStore(root / "planning-proposals.json"),
            recommendation_service=self.planning_recommendation,
            planning_context_service=self.planning_context,
            requirement_planning_service=self.service,
        )

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, source_type: str, *, title: str = "Device Health", **extra):
        request = {"sourceType": source_type, "projectId": "gridhub", "title": title, **extra}
        if source_type == "PasteRequirement":
            request["content"] = CONTENT
        elif source_type == "UploadDocument":
            request["document"] = {"name": extra.get("fileName", "requirement.md"), "mediaType": "text/markdown", "content": CONTENT}
        elif source_type == "MeetingTranscript":
            request["transcript"] = CONTENT
        elif source_type == "AzureDevOpsWorkItem":
            request["workItemId"] = "245"
        context = self.ingestion.ingest(request)
        self.analysis.analyze(context["requirementId"])
        self.analysis.approve(context["requirementId"], "Product Owner")
        return self.ingestion.get(context["requirementId"])

    def prepare_proposal(self):
        self.service.planning_context_service = self.planning_context
        self.service.planning_recommendation_service = self.planning_recommendation
        requirement = self.prepare("PasteRequirement")
        context = self.planning_context.build({"requirementId": requirement["requirementId"], "actor": "Planner"})
        self.planning_context.analyze({
            "contextId": context["contextId"], "decision": "Accept", "actor": "Product Owner",
        })
        recommendation = self.planning_recommendation.build({"contextId": context["contextId"]})
        recommendation = self.planning_recommendation.approve({
            "recommendationId": recommendation["recommendationId"], "actor": "Product Owner",
        })
        proposal = self.proposal.build({
            "recommendationId": recommendation["recommendationId"], "actor": "Planner",
        })
        return requirement, context, recommendation, proposal

    def test_all_supported_requirement_sources_generate_validated_planning_packs(self):
        sources = [
            ("PasteRequirement", "Manual Requirement", {}),
            ("UploadDocument", "Device Health PRD", {"fileName": "device-health-prd.md"}),
            ("UploadDocument", "Device Health BRD", {"fileName": "device-health-brd.md"}),
            ("MeetingTranscript", "Device Health Review", {}),
            ("AzureDevOpsWorkItem", "Ignored by synchronized work item", {}),
        ]
        for source, title, extra in sources:
            with self.subTest(source=source, title=title):
                requirement = self.prepare(source, title=title, **extra)
                result = self.service.from_requirement({"requirementId": requirement["requirementId"], "actor": "Planner"})
                self.assertEqual("RequirementIntelligence", result["entryPoint"])
                self.assertEqual("RequirementSummary", result["requirementSummary"]["summaryType"])
                self.assertEqual(source, result["requirementSummary"]["sourceType"])
                self.assertTrue(result["planningPackId"])
                self.assertTrue(result["estimateId"])
                self.assertIn(result["planningPreview"]["validation"]["status"], {"ReadyForApproval", "NeedsReview"})

    def test_planning_agent_context_consumes_summary_not_request_text(self):
        requirement = self.prepare("PasteRequirement")
        result = self.service.from_requirement({
            "requirementId": requirement["requirementId"],
            "title": "RAW TITLE MUST NOT WIN", "content": "RAW CONTENT MUST NOT REACH PLANNING",
        })
        artifact = self.context.requests[0].artifact
        self.assertEqual("RequirementSummary", artifact["planningSource"])
        self.assertEqual(result["requirementSummary"], artifact["requirementSummary"])
        self.assertNotIn("RAW CONTENT", artifact["description"])
        self.assertEqual("RequirementSummary", self.artifacts[0]["payload"]["planningSource"])

    def test_repository_detection_reaches_estimation_and_preview(self):
        requirement = self.prepare("PasteRequirement")
        result = self.service.generate({"requirementId": requirement["requirementId"]})
        summary = result["requirementSummary"]
        self.assertEqual("device-repository", summary["repository"]["repositoryId"])
        self.assertGreater(summary["repository"]["confidence"], 0)
        self.assertEqual("snapshot-device-v3", result["engineeringEstimation"]["repositorySnapshot"])
        self.assertEqual("CodeIndexed", result["planningPreview"]["validation"]["repositoryMode"])

    def test_generation_is_idempotent_for_same_approved_summary(self):
        requirement = self.prepare("PasteRequirement")
        first = self.service.generate({"requirementId": requirement["requirementId"]})
        second = self.service.generate({"requirementId": requirement["requirementId"]})
        self.assertEqual(first["planningPackId"], second["planningPackId"])
        self.assertEqual(first["estimateId"], second["estimateId"])
        self.assertEqual(1, len(self.artifacts))

    def test_synchronized_backlog_revision_invalidates_cached_proposal(self):
        work_items = [{"workItemId": 88, "workItemType": "Epic", "title": "Device Health", "revision": 1}]
        self.service.intelligence_engine.work_item_provider = lambda _project: work_items
        requirement = self.prepare("PasteRequirement")
        first = self.service.generate({"requirementId": requirement["requirementId"]})
        work_items[0] = {**work_items[0], "revision": 2}
        second = self.service.generate({"requirementId": requirement["requirementId"]})
        self.assertNotEqual(first["planningPackId"], second["planningPackId"])
        self.assertNotEqual(first["planningContext"]["contextVersion"], second["planningContext"]["contextVersion"])

    def test_raw_planning_input_and_unapproved_summary_are_blocked(self):
        with self.assertRaisesRegex(ValueError, "Raw planning input cannot bypass"):
            self.service.generate({"title": "Bypass", "content": "Do planning directly"})
        requirement = self.ingestion.ingest({
            "sourceType": "PasteRequirement", "projectId": "gridhub", "title": "Unreviewed", "content": CONTENT,
        })
        self.analysis.analyze(requirement["requirementId"])
        with self.assertRaisesRegex(ValueError, "approval is required"):
            self.service.generate({"requirementId": requirement["requirementId"]})

    def test_preview_detects_stale_requirement_summary(self):
        requirement = self.prepare("PasteRequirement")
        result = self.service.generate({"requirementId": requirement["requirementId"]})
        self.analysis.edit(requirement["requirementId"], {
            "title": "Updated Device Health", "content": CONTENT + "\nConstraints:\n- Only approved regions are included.",
        })
        with self.assertRaisesRegex(ValueError, "approval is required|stale"):
            self.service.preview({"planningPackId": result["planningPackId"]})

    def test_required_planning_apis_and_preview_contract(self):
        requirement = self.prepare("PasteRequirement")
        app = FastAPI()
        app.include_router(build_requirement_planning_router(self.service))
        client = TestClient(app)
        generated = client.post("/planning/from-requirement", json={"requirementId": requirement["requirementId"]})
        self.assertEqual(200, generated.status_code)
        preview = client.post("/planning/preview", json={"planningPackId": generated.json()["planningPackId"]})
        self.assertEqual(200, preview.status_code)
        self.assertEqual("RequirementSummary", preview.json()["planningPreview"]["source"])
        context = client.post("/planning/context", json={"requirementId": requirement["requirementId"]})
        self.assertEqual(200, context.status_code)
        self.assertEqual("hei-planning-context-v1", context.json()["schemaVersion"])
        recommendation = client.post("/planning/recommend", json={"requirementId": requirement["requirementId"]})
        self.assertEqual(200, recommendation.status_code)
        planning_diff = client.get(f"/planning/{generated.json()['planningPackId']}/diff")
        self.assertEqual(200, planning_diff.status_code)
        self.assertEqual("hei-planning-diff-v1", planning_diff.json()["diff"]["schemaVersion"])
        approved_diff = client.post(
            f"/planning/{generated.json()['planningPackId']}/diff/approve",
            json={"actor": "Product Owner", "comments": "Reviewed against current ADO work."},
        )
        self.assertEqual("Approved", approved_diff.json()["diff"]["status"])
        direct = client.post("/planning/generate", json={"title": "Bypass"})
        self.assertEqual(400, direct.status_code)
        self.assertEqual("invalid_requirement_planning", direct.json()["error"]["code"])

    def test_planning_context_is_persisted_reviewed_and_required_before_planning(self):
        requirement = self.prepare("PasteRequirement")
        built = self.planning_context.build({"requirementId": requirement["requirementId"], "actor": "Planner"})
        self.assertEqual("Pending", built["reviewStatus"])
        self.assertEqual("device-repository", built["repository"]["repositoryId"])
        self.assertEqual("Sprint 12", built["azureDevOps"]["currentSprint"]["name"])
        self.assertTrue(built["similarWork"])
        self.assertTrue(built["repository"]["affectedModules"])
        self.assertEqual(built, self.planning_context.get(built["contextId"]))

        self.service.planning_context_service = self.planning_context
        with self.assertRaisesRegex(ValueError, "must be completed"):
            self.service.generate({"requirementId": requirement["requirementId"]})
        reviewed = self.planning_context.analyze({
            "contextId": built["contextId"], "decision": "Accept", "actor": "Product Owner",
        })
        self.assertEqual("Completed", reviewed["status"])
        result = self.service.generate({
            "requirementId": requirement["requirementId"], "planningContextId": reviewed["contextId"],
        })
        self.assertEqual(reviewed["contextId"], result["reviewedPlanningContext"]["contextId"])

    def test_planning_context_classification_refresh_and_api_contracts(self):
        requirement = self.prepare("PasteRequirement")
        app = FastAPI()
        app.include_router(build_planning_context_router(self.planning_context))
        client = TestClient(app)
        built = client.post("/planning/context/build", json={"requirementId": requirement["requirementId"]})
        self.assertEqual(200, built.status_code)
        context_id = built.json()["contextId"]
        loaded = client.get(f"/planning/context/{context_id}")
        self.assertEqual(200, loaded.status_code)
        classified = client.post("/planning/context/classify", json={
            "contextId": context_id, "classification": "EXTEND_FEATURE", "actor": "Planner",
        })
        self.assertEqual("ManualOverride", classified.json()["classification"]["source"])
        analyzed = client.post("/planning/context/analyze", json={
            "contextId": context_id, "decision": "Accept", "actor": "Planner",
        })
        self.assertEqual("Reviewed", analyzed.json()["reviewStatus"])
        refreshed = client.post("/planning/context/refresh", json={"contextId": context_id})
        self.assertEqual(200, refreshed.status_code)
        self.assertEqual("Pending", refreshed.json()["reviewStatus"])

    def test_planning_recommendation_requires_reviewed_context_and_contains_diff(self):
        requirement = self.prepare("PasteRequirement")
        planning_context = self.planning_context.build({"requirementId": requirement["requirementId"], "actor": "Planner"})
        with self.assertRaisesRegex(ValueError, "Review the Planning Context"):
            self.planning_recommendation.build({"contextId": planning_context["contextId"]})

        self.planning_context.analyze({
            "contextId": planning_context["contextId"], "decision": "Accept", "actor": "Product Owner",
        })
        recommendation = self.planning_recommendation.build({"contextId": planning_context["contextId"]})

        self.assertEqual("PendingReview", recommendation["status"])
        self.assertEqual("EXTEND_EXISTING_FEATURE", recommendation["strategy"])
        self.assertGreaterEqual(len(recommendation["alternatives"]), 1)
        self.assertGreaterEqual(len(recommendation["reasons"]), 1)
        self.assertGreaterEqual(len(recommendation["diff"]["operations"]), 1)
        self.assertIn("Reuse", recommendation["diff"]["summary"])
        self.assertEqual([], self.artifacts)

    def test_planning_proposal_is_blocked_until_recommendation_is_approved(self):
        requirement = self.prepare("PasteRequirement")
        planning_context = self.planning_context.build({"requirementId": requirement["requirementId"], "actor": "Planner"})
        reviewed = self.planning_context.analyze({
            "contextId": planning_context["contextId"], "decision": "Accept", "actor": "Product Owner",
        })
        recommendation = self.planning_recommendation.build({"contextId": reviewed["contextId"]})
        self.service.planning_context_service = self.planning_context
        self.service.planning_recommendation_service = self.planning_recommendation

        with self.assertRaisesRegex(ValueError, "Approve the Planning Recommendation"):
            self.service.generate({
                "requirementId": requirement["requirementId"],
                "planningContextId": reviewed["contextId"],
                "recommendationId": recommendation["recommendationId"],
            })
        self.assertEqual([], self.artifacts)

        approved = self.planning_recommendation.approve({
            "recommendationId": recommendation["recommendationId"], "actor": "Product Owner",
        })
        generated = self.service.generate({
            "requirementId": requirement["requirementId"],
            "planningContextId": reviewed["contextId"],
            "recommendationId": approved["recommendationId"],
        })
        self.assertEqual(approved["recommendationId"], generated["reviewedPlanningRecommendation"]["recommendationId"])
        self.assertEqual(approved["strategy"], generated["reviewedPlanningRecommendation"]["strategy"])
        self.assertEqual(1, len(self.artifacts))

    def test_planning_recommendation_override_regenerate_and_api_contracts(self):
        requirement = self.prepare("PasteRequirement")
        context_record = self.planning_context.build({"requirementId": requirement["requirementId"]})
        self.planning_context.analyze({
            "contextId": context_record["contextId"], "decision": "Accept", "actor": "Planner",
        })
        app = FastAPI()
        app.include_router(build_planning_recommendation_router(self.planning_recommendation))
        client = TestClient(app)

        created = client.post("/planning/recommendation", json={"contextId": context_record["contextId"]})
        self.assertEqual(200, created.status_code)
        recommendation_id = created.json()["recommendationId"]
        self.assertEqual(200, client.get(f"/planning/recommendation/{recommendation_id}").status_code)

        overridden = client.post("/planning/recommendation/override", json={
            "recommendationId": recommendation_id,
            "strategy": "SPIKE",
            "reason": "Technical uncertainty must be resolved before committed planning.",
            "actor": "Architect",
        })
        self.assertEqual(200, overridden.status_code)
        self.assertEqual("SPIKE", overridden.json()["strategy"])
        self.assertEqual("PendingReview", overridden.json()["status"])

        regenerated = client.post("/planning/recommendation/regenerate", json={
            "recommendationId": recommendation_id, "actor": "Planner",
        })
        self.assertEqual(200, regenerated.status_code)
        self.assertGreater(regenerated.json()["version"], overridden.json()["version"])
        approved = client.post("/planning/recommendation/approve", json={
            "recommendationId": recommendation_id, "actor": "Product Owner",
        })
        self.assertEqual("Approved", approved.json()["status"])

    def test_planning_proposal_requires_approved_recommendation(self):
        requirement = self.prepare("PasteRequirement")
        context = self.planning_context.build({"requirementId": requirement["requirementId"]})
        self.planning_context.analyze({
            "contextId": context["contextId"], "decision": "Accept", "actor": "Product Owner",
        })
        recommendation = self.planning_recommendation.build({"contextId": context["contextId"]})
        with self.assertRaisesRegex(ValueError, "Approve the Planning Recommendation"):
            self.proposal.build({"recommendationId": recommendation["recommendationId"]})
        self.assertEqual([], self.artifacts)

    def test_planning_proposal_contains_rich_hierarchy_traceability_and_tasks(self):
        requirement, context, recommendation, proposal = self.prepare_proposal()
        types = {node["type"] for node in proposal["nodes"]}
        self.assertTrue({"Epic", "Feature", "Story", "Task"}.issubset(types))
        self.assertEqual(requirement["requirementId"], proposal["requirementId"])
        self.assertEqual(context["contextId"], proposal["contextId"])
        self.assertEqual(recommendation["recommendationId"], proposal["recommendationId"])
        for node in proposal["nodes"]:
            self.assertEqual(requirement["requirementId"], node["traceability"]["requirementId"])
            self.assertEqual(recommendation["recommendationId"], node["traceability"]["recommendationId"])
            self.assertTrue(node["reason"])
            self.assertTrue(node["origin"])
            self.assertEqual(1, node["planningVersion"])
        stories = [node for node in proposal["nodes"] if node["type"] == "Story"]
        tasks = [node for node in proposal["nodes"] if node["type"] == "Task"]
        self.assertTrue(stories)
        self.assertTrue(tasks)
        self.assertTrue(all(node["acceptanceCriteria"] for node in stories))
        self.assertTrue(all(node["parentId"] in {story["nodeId"] for story in stories} for node in tasks))
        self.assertEqual(1, len(self.artifacts))

    def test_planning_proposal_edits_are_versioned_and_scoped_regeneration_isolated(self):
        _, _, _, proposal = self.prepare_proposal()
        story = next(node for node in proposal["nodes"] if node["type"] == "Story")
        other = next(node for node in proposal["nodes"] if node["nodeId"] != story["nodeId"])
        edited = self.proposal.update(proposal["proposalId"], {
            "expectedVersion": proposal["version"],
            "nodeId": story["nodeId"],
            "changes": {"title": "Filter Devices by Operational Health"},
            "actor": "Business Analyst",
            "reason": "Clarified the story outcome.",
        })
        self.assertEqual(2, edited["version"])
        self.assertEqual(1, len(edited["history"]))
        self.assertEqual("Filter Devices by Operational Health", next(node for node in edited["nodes"] if node["nodeId"] == story["nodeId"])["title"])
        other_before = next(node for node in edited["nodes"] if node["nodeId"] == other["nodeId"])
        regenerated = self.proposal.regenerate({
            "proposalId": edited["proposalId"], "expectedVersion": edited["version"],
            "scope": "Acceptance Criteria", "nodeId": story["nodeId"], "actor": "Planner",
        })
        other_after = next(node for node in regenerated["nodes"] if node["nodeId"] == other["nodeId"])
        for field in ("title", "description", "acceptanceCriteria", "repositoryModules", "traceability"):
            self.assertEqual(other_before[field], other_after[field])
        self.assertEqual(3, regenerated["version"])

    def test_planning_proposal_node_operations_and_validation(self):
        _, _, _, proposal = self.prepare_proposal()
        story = next(node for node in proposal["nodes"] if node["type"] == "Story")
        duplicated = self.proposal.update(proposal["proposalId"], {
            "operation": "duplicate", "nodeId": story["nodeId"], "title": "Duplicate Story",
            "expectedVersion": proposal["version"], "actor": "Planner",
        })
        self.assertEqual(len(proposal["nodes"]) + 1, len(duplicated["nodes"]))
        duplicate = next(node for node in duplicated["nodes"] if node["title"] == "Duplicate Story")
        invalid = self.proposal.update(duplicated["proposalId"], {
            "nodeId": duplicate["nodeId"], "changes": {"acceptanceCriteria": [], "storyPoints": 0},
            "expectedVersion": duplicated["version"], "actor": "Planner",
        })
        validated = self.proposal.validate({"proposalId": invalid["proposalId"]})
        codes = {finding["code"] for finding in validated["validation"]["findings"]}
        self.assertIn("missing_acceptance_criteria", codes)
        self.assertIn("missing_story_points", codes)
        self.assertFalse(validated["validation"]["mandatoryPassed"])

    def test_planning_proposal_node_approval_and_rejection_are_versioned(self):
        _, _, _, proposal = self.prepare_proposal()
        feature = next(node for node in proposal["nodes"] if node["type"] == "Feature")
        approved = self.proposal.update(proposal["proposalId"], {
            "operation": "approve", "nodeId": feature["nodeId"],
            "expectedVersion": proposal["version"], "actor": "Product Owner",
        })
        self.assertEqual("Approved", next(node for node in approved["nodes"] if node["nodeId"] == feature["nodeId"])["status"])
        rejected = self.proposal.update(approved["proposalId"], {
            "operation": "reject", "nodeId": feature["nodeId"],
            "expectedVersion": approved["version"], "actor": "Product Owner",
        })
        affected = [node for node in rejected["nodes"] if node["nodeId"] == feature["nodeId"] or node["parentId"] == feature["nodeId"]]
        self.assertTrue(affected)
        self.assertTrue(all(node["status"] == "Rejected" for node in affected))

    def test_planning_proposal_review_approval_and_immutability(self):
        _, _, _, proposal = self.prepare_proposal()
        validated = self.proposal.validate({"proposalId": proposal["proposalId"]})
        self.assertTrue(validated["validation"]["mandatoryPassed"])
        reviewed = self.proposal.review({
            "proposalId": proposal["proposalId"], "actor": "Product Owner", "comments": "Scope and traceability reviewed.",
        })
        self.assertEqual("Completed", reviewed["review"]["status"])
        approved = self.proposal.approve({"proposalId": proposal["proposalId"], "actor": "Product Owner"})
        self.assertEqual("Approved", approved["status"])
        self.assertTrue(all(node["status"] == "Approved" for node in approved["nodes"]))
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.proposal.update(approved["proposalId"], {
                "nodeId": approved["nodes"][0]["nodeId"], "changes": {"title": "Forbidden edit"},
            })

    def test_planning_proposal_api_contract_and_history(self):
        _, _, recommendation, _ = self.prepare_proposal()
        app = FastAPI()
        app.include_router(build_planning_proposal_router(self.proposal))
        client = TestClient(app)
        built = client.post("/planning/proposal", json={
            "recommendationId": recommendation["recommendationId"], "actor": "Planner",
        })
        self.assertEqual(200, built.status_code)
        proposal_id = built.json()["proposalId"]
        loaded = client.get(f"/planning/proposal/{proposal_id}")
        self.assertEqual(200, loaded.status_code)
        node = loaded.json()["nodes"][0]
        updated = client.put(f"/planning/proposal/{proposal_id}", json={
            "expectedVersion": loaded.json()["version"], "nodeId": node["nodeId"],
            "changes": {"description": "Reviewed planning description."}, "actor": "Planner",
        })
        self.assertEqual(200, updated.status_code)
        history = client.get("/planning/proposal/history", params={"proposalId": proposal_id})
        self.assertEqual(200, history.status_code)
        self.assertEqual(1, len(history.json()["history"]))
        self.assertEqual(200, client.post("/planning/proposal/validate", json={"proposalId": proposal_id}).status_code)


if __name__ == "__main__":
    unittest.main()
