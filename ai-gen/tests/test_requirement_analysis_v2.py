from __future__ import annotations

import unittest

from backend.reasoning.models import ReasoningRequest
from backend.reasoning.services import PromptBuilder
from backend.requirement_analysis import RequirementAnalysisDocumentBuilder, build_requirement_summary


def discovery_report() -> dict:
    evidence = [
        {
            "evidenceId": "ev-module",
            "evidenceType": "Module",
            "title": "Device Health",
            "source": "Repository Intelligence",
            "sourceReference": "repository:repo-1:v7:device-health",
            "reason": "Module matched the device health requirement.",
            "confidence": 94,
            "metadata": {},
        },
        {
            "evidenceId": "ev-service",
            "evidenceType": "Service",
            "title": "DeviceHealthService",
            "source": "Repository Intelligence",
            "sourceReference": "repository:repo-1:v7:device-health-service",
            "reason": "Service reports current device health.",
            "confidence": 91,
            "metadata": {},
        },
        {
            "evidenceId": "ev-api",
            "evidenceType": "API",
            "title": "GET /api/device-health",
            "source": "Repository Intelligence",
            "sourceReference": "repository:repo-1:v7:device-health-api",
            "reason": "API exposes current device health.",
            "confidence": 89,
            "metadata": {},
        },
    ]
    markdown = {
        "evidenceId": "ev-doc",
        "evidenceType": "Documentation",
        "title": "docs/device-health.md · Health States",
        "source": "Repository Markdown",
        "sourceReference": "markdown:repo-1:v7:device-health:health-states",
        "reason": "The section defines operational health states.",
        "confidence": 88,
        "metadata": {"path": "docs/device-health.md"},
    }
    ado = {
        "evidenceId": "ev-ado",
        "evidenceType": "SimilarWork",
        "title": "Device Health Dashboard",
        "source": "Azure DevOps",
        "sourceReference": "ado:work-item:245:revision:4",
        "reason": "The synchronized Feature covers the same operational domain.",
        "confidence": 82,
        "metadata": {"workItemId": "245"},
    }
    return {
        "schemaVersion": "hei-engineering-discovery-v2",
        "status": "Ready",
        "summary": "Relevant engineering knowledge is ready for requirement reasoning.",
        "repositoryEvidence": evidence,
        "relevantDocumentation": [markdown],
        "azureDevOpsEvidence": [ado],
        "reusableComponents": [evidence[1]],
        "architectureEvidence": [],
        "engineeringMemoryEvidence": [],
        "projectIntelligenceEvidence": [],
        "knowledgeEvidence": [],
        "whatIFound": [{"summary": "Repository Intelligence found 3 relevant items.", "count": 3}],
        "unknowns": [],
        "confidence": {"score": 88, "evidenceCount": 5},
    }


def base_analysis() -> dict:
    return {
        "analysisId": "analysis-1",
        "requirementSummary": "Give operators a reliable device health view.",
        "planningRequirement": "Operations users need current device health visibility.",
        "businessGoals": ["Reduce the time required to identify unhealthy devices."],
        "functionalRequirements": ["Display current device health and communication status."],
        "nonFunctionalRequirements": [],
        "acceptanceCriteria": ["Operators can identify unhealthy devices."],
        "actors": ["Operations User"],
        "businessRules": [],
        "constraints": [],
        "dependencies": [],
        "risks": [],
        "assumptions": [],
        "openQuestions": [],
        "fieldOrigins": {
            "businessGoals": "Source",
            "functionalRequirements": "Source",
            "actors": "Source",
        },
        "requirementIntent": {
            "businessGoal": "Reduce the time required to identify unhealthy devices.",
            "primaryActor": "Operations User",
            "capabilities": ["Device Health Overview"],
        },
        "planningReadiness": {
            "status": "ReadyWithRecommendations",
            "readyForPlanning": True,
            "score": 78,
            "blockers": [],
            "warnings": ["Review candidate quality requirements."],
        },
        "requirementQualityScore": 78,
        "confidence": 0.84,
        "statementGovernance": {
            "statements": [{
                "id": "statement-functional-1",
                "category": "Functional Requirement",
                "text": "Display current device health and communication status.",
                "classification": "SOURCE",
                "source": "User Requirement",
                "provider": "",
                "model": "",
                "promptVersion": "",
                "confidence": 1.0,
                "evidenceReferences": ["source:requirement"],
                "generatedAt": "2026-08-04T00:00:00+00:00",
                "approvedStatus": "NotRequired",
                "why": "Directly stated by the requirement.",
            }],
            "suggestedEnhancements": [],
            "governedValues": {},
        },
    }


def reasoning() -> dict:
    return {
        "reasoningMode": "AI",
        "provider": "Phi",
        "recommendation": {
            "executiveSummary": "Provide operations teams with evidence-backed device health visibility.",
            "businessGoal": "Reduce operational response time for unhealthy devices.",
            "problemStatement": "Operators cannot consistently identify unhealthy devices early.",
            "primaryActor": "Operations User",
            "secondaryActors": ["Operations Supervisor"],
            "businessValue": "Earlier intervention reduces avoidable device downtime.",
            "capabilities": ["Device Health Overview", "Health Status Filtering"],
            "functionalRequirements": ["Display current device health and communication status."],
            "candidateNonFunctionalRequirements": ["Present current health without stale status."],
            "businessRules": ["Health states use the documented operational definitions."],
            "constraints": ["Use the existing device health module."],
            "dependencies": ["Current health data depends on DeviceHealthService."],
            "risks": ["Stale health data could cause incorrect operational decisions."],
            "assumptions": ["Device health data is available to the existing service."],
            "openQuestions": ["Which service reports current device health?", "What retention period is required?"],
            "engineeringInsights": ["Existing service and API evidence support reuse."],
        },
        "evidence": [{"referenceId": "repository:repo-1:v7:device-health-service"}],
        "risks": [],
    }


class RequirementAnalysisV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = RequirementAnalysisDocumentBuilder()
        self.requirement = {
            "requirementId": "req-1",
            "contextVersion": "2.0",
            "title": "Device Health Operations",
        }

    def build(self, *, report: dict | None = None, analysis: dict | None = None, ai: dict | None = None) -> dict:
        return self.builder.build(
            self.requirement,
            analysis or base_analysis(),
            {"contextId": "ctx-1", "contextVersion": "v7"},
            {"report": report if report is not None else discovery_report()},
            ai or reasoning(),
        )

    def test_document_separates_business_goal_from_functional_requirement(self) -> None:
        document = self.build()
        self.assertNotEqual(document["businessGoal"], document["functionalRequirements"][0])
        self.assertEqual("Operations User", document["primaryActor"])
        self.assertIn("Device Health Overview", document["capabilities"])
        self.assertTrue(document["validation"]["checks"]["businessGoalDistinct"])
        self.assertEqual("SOURCE", document["statementGovernance"][0]["classification"])
        self.assertIn("strengths", document["planningReadiness"])

    def test_raw_provider_suggestion_is_not_reintroduced_into_canonical_document(self) -> None:
        analysis = base_analysis()
        analysis["suggestedEnhancements"] = [{"text": "Add automatic retry handling."}]
        ai = reasoning()
        ai["recommendation"]["functionalRequirements"].append("Add automatic retry handling.")

        document = self.build(analysis=analysis, ai=ai)

        self.assertNotIn("Add automatic retry handling.", document["functionalRequirements"])

    def test_repository_impact_contains_only_traceable_discovery_evidence(self) -> None:
        document = self.build()
        self.assertEqual(["Device Health"], document["affectedModules"])
        self.assertEqual(["DeviceHealthService"], document["affectedServices"])
        self.assertEqual(["GET /api/device-health"], document["affectedApis"])
        self.assertTrue(all(item["sourceReference"] and item["reason"] for item in document["repositoryFindings"]))
        self.assertNotIn("src/invented.ts", str(document))

    def test_evidence_required_claims_are_removed_when_discovery_has_no_evidence(self) -> None:
        empty_report = {
            "status": "NoRelevantEvidence",
            "repositoryEvidence": [],
            "relevantDocumentation": [],
            "azureDevOpsEvidence": [],
            "reusableComponents": [],
            "confidence": {"score": 0, "evidenceCount": 0},
        }
        document = self.build(report=empty_report)
        self.assertEqual([], document["businessRules"])
        self.assertEqual([], document["constraints"])
        self.assertEqual([], document["dependencies"])

    def test_source_provided_rule_remains_without_repository_evidence(self) -> None:
        analysis = base_analysis()
        analysis["businessRules"] = ["Only active devices are included."]
        analysis["fieldOrigins"]["businessRules"] = "Source"
        document = self.build(report={"status": "NoRelevantEvidence", "confidence": {}}, analysis=analysis)
        self.assertEqual(["Only active devices are included."], document["businessRules"])

    def test_open_questions_exclude_questions_answered_by_evidence(self) -> None:
        document = self.build()
        self.assertNotIn("Which service reports current device health?", document["openQuestions"])
        self.assertIn("What retention period is required?", document["openQuestions"])

    def test_requirement_summary_and_prompt_consume_canonical_document(self) -> None:
        document = self.build()
        analysis = {**base_analysis(), "analysisDocument": document, "reviewStatus": "Approved"}
        summary = build_requirement_summary(
            {**self.requirement, "sourceType": "PasteRequirement", "metadata": {}},
            analysis,
        )
        self.assertEqual(document, summary["canonicalRequirementAnalysis"])
        self.assertEqual([document["businessGoal"]], summary["businessGoals"])

        context = {
            "contextId": "ctx-1",
            "contextVersion": "v7",
            "requirement": {
                "title": document["title"],
                "analysisDocument": document,
                "functionalRequirements": ["legacy value"],
            },
            "repository": {},
            "engineeringMemory": {},
            "similarWork": {},
            "architecture": {},
            "dependencies": {},
            "readiness": {},
        }
        built = PromptBuilder().build(
            ReasoningRequest("Planning Recommendation", context),
            provider="GPT",
            model="gpt-test",
        )
        intent_section = next(item for item in built.sections if item["id"] == "current_intent")
        self.assertEqual(document, intent_section["content"]["canonicalRequirementAnalysis"])
        self.assertEqual(document["functionalRequirements"], intent_section["content"]["functionalRequirements"])


if __name__ == "__main__":
    unittest.main()
