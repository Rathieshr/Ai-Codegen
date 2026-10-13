from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.engineering_intelligence import EngineeringIntelligenceService
from backend.engineering_intelligence.services.markdown_service import MarkdownService
from backend.planning_recommendation.service import _missing_information
from backend.reasoning.models import ReasoningRequest
from backend.reasoning.services.prompt_builder import PromptBuilder


class LocalRepositoryProvider:
    def __init__(self, root: Path):
        self.root = root

    def get_repository(self, repository_id):
        return {
            "repositoryId": repository_id,
            "name": "Line Defender",
            "defaultBranch": "main",
            "status": "Active",
            "metadata": {"localPath": str(self.root), "commitId": "commit-42"},
        }

    def get_current_snapshot(self, _repository_id):
        return {
            "snapshotId": "snapshot-42",
            "version": "42",
            "modules": ["Fault Monitoring"],
        }

    def get_graph(self, _repository_id):
        return {
            "nodes": [
                {"nodeId": "module-fault", "nodeType": "Module", "name": "Fault Monitoring"},
                {"nodeId": "service-legacy", "nodeType": "Service", "name": "Legacy Service"},
                {"nodeId": "api-fault", "nodeType": "API", "name": "Fault API"},
            ],
            "relationships": [],
        }


class ProjectFacts:
    def get_profile(self):
        return {
            "onboarding_completed": True,
            "project_id": "project-1",
            "project_name": "Line Defender",
            "domain": "Operations",
        }

    def get_knowledge_cache(self):
        return {
            "exists": True,
            "status": "fresh",
            "cache": {
                "project_id": "project-1",
                "knowledge_version": "knowledge-8",
                "source_files": ["knowledge/approved-faults.md"],
                "knowledge_registry": {
                    "modules": ["Fault Monitoring"],
                    "flows": ["Fault Review"],
                },
            },
        }

    def list_artifacts(self):
        return {
            "artifacts": [
                {
                    "artifact_id": "approved-story",
                    "artifact_type": "Story",
                    "state": "locked",
                    "title": "Review Critical Faults",
                    "payload": {"description": "Review fault severity."},
                    "version": 2,
                },
                {
                    "artifact_id": "draft-story",
                    "artifact_type": "Story",
                    "state": "draft",
                    "title": "Unapproved Firmware Work",
                    "payload": {},
                },
            ],
        }


class RepositoryMarkdownIntelligenceTests(unittest.TestCase):
    def _repository(self, root: Path) -> None:
        (root / "README.md").write_text(
            "# Fault Operations\n"
            "Business rule: operators must acknowledge critical faults within five minutes.\n",
            encoding="utf-8",
        )
        (root / "docs" / "features").mkdir(parents=True)
        (root / "docs" / "features" / "fault-review.md").write_text(
            "# Fault Review\n"
            "## Permissions\n"
            "Security requirement: only Operations Supervisors may close critical faults.\n"
            "The Fault API provides the integration contract.\n",
            encoding="utf-8",
        )
        (root / "adr").mkdir()
        (root / "adr" / "004-services.md").write_text(
            "# ADR 004\n"
            "The Legacy Service is deprecated and must not be used for new fault workflows.\n",
            encoding="utf-8",
        )
        (root / "docs" / "firmware.md").write_text(
            "# Firmware Rollout\nUse staged firmware deployment rings.\n",
            encoding="utf-8",
        )
        (root / "node_modules" / "dependency").mkdir(parents=True)
        (root / "node_modules" / "dependency" / "README.md").write_text(
            "# Dependency Manual\nFault implementation internals.",
            encoding="utf-8",
        )
        (root / "dist").mkdir()
        (root / "dist" / "generated.md").write_text(
            "# Generated Fault Documentation\nIgnore this.",
            encoding="utf-8",
        )

    def _context(self, root: Path) -> dict:
        service = EngineeringIntelligenceService(
            repository_intelligence=LocalRepositoryProvider(root),
            project_intelligence=ProjectFacts(),
        )
        return service.generate_planning_context({
            "requirementId": "requirement-1",
            "contextVersion": "1",
            "analysisId": "analysis-1",
            "projectId": "project-1",
            "repositoryId": "repo-1",
            "title": "Improve fault review",
            "planningRequirement": "Improve fault review.",
            "functionalRequirements": ["Review critical faults."],
        })["engineeringContext"]

    def test_minimal_requirement_discovers_nested_rules_and_ignores_generated_content(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            context = self._context(root)
            markdown = context["repository_markdown_context"]

            paths = {item["path"] for item in markdown["selected"]}
            self.assertIn("README.md", paths)
            self.assertIn("docs/features/fault-review.md", paths)
            self.assertNotIn("node_modules/dependency/README.md", paths)
            self.assertNotIn("dist/generated.md", paths)
            self.assertEqual(4, markdown["diagnostics"]["filesScanned"])
            self.assertGreater(markdown["diagnostics"]["sectionsIndexed"], 3)

    def test_irrelevant_markdown_is_excluded_from_reasoning_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            context = self._context(root)
            prompt = PromptBuilder().build(
                ReasoningRequest(
                    workflowType="Planning Recommendation",
                    engineeringContext=context,
                    userRequirement="Improve fault review.",
                ),
                provider="deterministic",
            )
            serialized = json.dumps(prompt.sections)

            self.assertIn("docs/features/fault-review.md", serialized)
            self.assertNotIn("docs/firmware.md", serialized)
            self.assertNotIn("node_modules", serialized)

    def test_project_scope_and_repository_scope_are_enforced(self):
        service = MarkdownService()
        service.index_repository_documents(
            [{"path": "docs/fault.md", "content": "# Fault\nFault rule for project one."}],
            repository_id="repo-1",
            project_id="project-1",
        )
        service.index_repository_documents(
            [{"path": "docs/fault.md", "content": "# Fault\nFault rule for project two."}],
            repository_id="repo-2",
            project_id="project-2",
        )

        result = service.retrieve(
            "fault rule",
            repository_id="repo-1",
            project_id="project-1",
        )

        self.assertTrue(result["selected"])
        self.assertTrue(all(item["repositoryId"] == "repo-1" for item in result["selected"]))
        self.assertTrue(any(item["reason"] == "different_project" for item in result["rejected"]))

    def test_markdown_and_approved_project_artifacts_remain_separate_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            context = self._context(root)

            self.assertTrue(context["repository_markdown_context"]["selected"])
            self.assertEqual(
                ["approved-story"],
                [item["id"] for item in context["project_intelligence_context"]["approvedArtifacts"]],
            )
            self.assertEqual(
                context["projectIntelligence"],
                context["project_intelligence_context"],
            )

    def test_adr_and_current_code_conflict_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            context = self._context(root)
            conflicts = context["repository_markdown_context"]["conflicts"]

            self.assertEqual(1, len(conflicts))
            self.assertEqual("current_implementation", conflicts[0]["claimType"])
            self.assertIn("Legacy Service", conflicts[0]["repositoryCodeEvidence"])

    def test_markdown_resolves_clarification_and_preserves_evidence_lineage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._repository(root)
            context = self._context(root)
            missing = _missing_information(context)
            selected = context["repository_markdown_context"]["selected"]
            lineage = context["sourceVersions"]["repositoryMarkdown"]

            self.assertEqual([], missing["missingBusinessRules"])
            self.assertTrue(all(item["evidenceId"] for item in selected))
            self.assertTrue(all(item["path"] and item["heading"] for item in selected))
            self.assertEqual("commit-42", lineage["repositoryRevision"])
            self.assertTrue(all(item["contentHash"] for item in lineage["evidence"]))


if __name__ == "__main__":
    unittest.main()
