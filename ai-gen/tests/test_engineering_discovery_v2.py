from __future__ import annotations

import unittest

from backend.engineering_intelligence import EngineeringDiscoveryService


class EngineeringDiscoveryV2Tests(unittest.TestCase):
    def setUp(self):
        self.service = EngineeringDiscoveryService()

    def context(self) -> dict:
        return {
            "contextId": "context-device-health",
            "contextVersion": "context-v4",
            "requirement": {
                "title": "Add device health filtering",
                "planningRequirement": "Operators filter unhealthy devices.",
                "requirementIntent": {
                    "capabilities": ["Device Health"],
                    "possibleRepositoryTerms": ["device health"],
                    "possibleMarkdownSearchTerms": ["device health architecture"],
                    "possibleAzureDevOpsSearchTerms": ["device health dashboard"],
                },
            },
            "repository": {
                "repositoryId": "repo-1",
                "repositoryName": "Device Operations",
                "mode": "CodeIndexed",
                "repositorySnapshotVersion": "snapshot-v4",
                "affectedModules": ["Device Health"],
                "services": ["Device Health Service", "Firmware Service"],
                "apiEndpoints": ["Device Health API", "Firmware API"],
                "sharedComponents": ["Device Health Grid", "Firmware Updater"],
                "tests": ["Device Health Tests"],
                "files": [
                    {"path": "src/device/DeviceHealthService.ts", "confidence": 91, "reason": "Ranked by repository graph."},
                    {"path": "src/firmware/FirmwareUpdater.ts", "confidence": 90},
                ],
                "confidence": 92,
            },
            "repository_markdown_context": {
                "selected": [{
                    "evidenceId": "markdown:repo-1:device-health",
                    "path": "docs/device-health.md",
                    "heading": "Architecture",
                    "classification": "architecture",
                    "selectionReason": "Matched device health and filtering.",
                    "confidence": 0.92,
                    "repositoryRevision": "commit-4",
                }],
                "conflicts": [],
                "diagnostics": {"filesScanned": 12, "sectionsIndexed": 40},
            },
            "azureDevOps": {
                "available": True,
                "projectId": "project-1",
                "existingPlanning": [{
                    "id": "42", "type": "Feature", "title": "Device Health Dashboard",
                    "state": "Active", "revision": 3,
                }],
            },
            "engineeringMemory": {
                "available": True,
                "matches": [{
                    "id": "memory-test", "title": "Device health permission tests",
                    "artifactType": "Test", "version": 2, "confidence": 0.84,
                }],
            },
            "similarWork": {
                "matches": [{
                    "workItem": {"id": "42", "type": "Feature", "title": "Device Health Dashboard", "revision": 3},
                    "confidence": 0.88,
                    "reason": "The existing Feature covers the same device health domain.",
                }],
            },
            "architecture": {
                "evidence": [{
                    "evidenceId": "graph:layer:device",
                    "title": "Device domain service layer",
                    "reason": "Repository graph links the API to the service.",
                    "confidence": 90,
                }],
            },
            "reuse": {
                "apis": [{"name": "Device Health API", "confidence": 90}],
                "tests": [{"name": "Device Health Tests", "confidence": 88}],
            },
            "projectIntelligence": {
                "available": True,
                "approvedArtifacts": [{
                    "id": "artifact-7", "title": "Filter Device Health",
                    "artifactType": "Story", "state": "approved", "version": 3,
                    "confidence": 82,
                    "reason": "Approved planning artifact matches device health filtering.",
                }],
                "knowledge": {
                    "version": "knowledge-v7",
                    "modules": ["Device Health"],
                    "flows": ["Device Health Review"],
                    "applications": [],
                    "components": ["Device Health Grid"],
                    "standards": ["Device health authorization"],
                    "architectureNotes": ["Device health queries use the telemetry read model."],
                },
            },
            "knowledge_synthesis": {"unresolvedInformation": ["dependencies"], "conflicts": []},
            "relevantDocumentation": [],
        }

    def test_report_combines_relevant_sources_with_traceable_reasons(self):
        report = self.service.build_report(self.context())

        self.assertEqual("hei-engineering-discovery-v2", report["schemaVersion"])
        self.assertEqual("Ready", report["status"])
        self.assertTrue(report["repositoryEvidence"])
        self.assertTrue(report["relevantDocumentation"])
        self.assertTrue(report["azureDevOpsEvidence"])
        self.assertTrue(report["engineeringMemoryEvidence"])
        self.assertTrue(report["projectIntelligenceEvidence"])
        self.assertTrue(report["knowledgeEvidence"])
        self.assertTrue(all(item["sourceReference"] for item in report["repositoryEvidence"]))
        self.assertTrue(all(item["reason"] for item in report["relevantDocumentation"]))

    def test_repository_hints_select_real_files_without_inventing_paths(self):
        context = self.context()
        context["requirement"]["requirementIntent"]["possibleRepositoryTerms"] = ["fault service"]
        context["repository"]["affectedModules"] = []
        context["repository"]["files"] = [
            {"path": "src/fault/FaultService.ts", "confidence": 86},
            {"path": "src/firmware/FirmwareUpdater.ts", "confidence": 90},
        ]

        report = self.service.build_report(context)
        files = [item["title"] for item in report["repositoryEvidence"] if item["evidenceType"] == "File"]

        self.assertEqual(["src/fault/FaultService.ts"], files)
        self.assertNotIn("src/fault/FaultController.ts", files)

    def test_pending_sources_are_distinct_from_completed_searches_without_matches(self):
        pending = self.service.build_report({
            "contextId": "pending", "contextVersion": "1", "requirement": {},
            "repository": {}, "repository_markdown_context": {"diagnostics": {}},
            "azureDevOps": {"available": False}, "engineeringMemory": {"available": False},
            "projectIntelligence": {"available": False, "knowledge": {}},
        })
        completed = self.service.build_report({
            "contextId": "complete", "contextVersion": "1", "requirement": {},
            "repository": {"repositoryId": "repo", "repositorySnapshotVersion": "v1"},
            "repository_markdown_context": {"diagnostics": {"filesScanned": 5, "sectionsIndexed": 10}},
            "azureDevOps": {"available": True, "projectId": "project"},
            "engineeringMemory": {"available": True, "matches": []},
            "projectIntelligence": {"available": True, "knowledge": {"version": "v1"}},
        })

        self.assertEqual("DiscoveryPending", pending["status"])
        self.assertEqual("NoRelevantEvidence", completed["status"])
        self.assertTrue(all(item["status"] == "NoRelevantEvidence" for item in completed["sourceStatus"]))

    def test_conflicts_and_unknowns_are_separate(self):
        context = self.context()
        context["repository_markdown_context"]["conflicts"] = [{
            "conflictId": "conflict-1",
            "path": "docs/architecture.md",
            "reason": "Documentation deprecates a service still present in code.",
        }]

        report = self.service.build_report(context)

        self.assertEqual("conflict-1", report["conflicts"][0]["conflictId"])
        self.assertEqual("Dependencies", report["unknowns"][0]["area"])
        self.assertEqual("UnresolvedRequirementInformation", report["unknowns"][0]["classification"])


if __name__ == "__main__":
    unittest.main()
