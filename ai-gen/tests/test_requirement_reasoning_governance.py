from __future__ import annotations

import unittest

from backend.requirement_analysis import RequirementGovernanceEngine


class RequirementReasoningGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = RequirementGovernanceEngine()
        self.requirement = {
            "title": "Offline Firmware Update",
            "normalizedRequirement": (
                "Allow a maintenance engineer to install firmware on a device while it is offline."
            ),
        }
        self.reasoning = {
            "provider": "Azure Phi",
            "model": "phi-4-mini",
            "promptVersion": "requirement-evidence-v3",
            "recommendation": {
                "businessGoal": "Allow a maintenance engineer to install firmware on a device while it is offline.",
                "problemStatement": "Allow a maintenance engineer to install firmware on a device while it is offline.",
                "businessValue": "Allow a maintenance engineer to install firmware on a device while it is offline.",
                "primaryActor": "Maintenance Engineer",
                "capabilities": ["Offline Firmware Update"],
            },
        }

    def test_unsupported_provider_patterns_are_suggestions_not_requirements(self) -> None:
        self.reasoning["recommendation"]["suggestedEnhancements"] = [{
            "text": "Add deployment recovery diagnostics.",
            "reason": "Useful operational enhancement, but not requested.",
        }]
        analysis = {
            "functionalRequirements": [
                "Install firmware on an offline device.",
                "Provide automatic rollback after a failed firmware update.",
                "Require role-based authorization for firmware installation.",
            ],
            "nonFunctionalRequirements": [],
            "actors": ["Maintenance Engineer"],
            "requirementIntent": {"capabilities": ["Offline Firmware Update"]},
        }

        result = self.engine.govern(self.requirement, analysis, {"report": {}}, self.reasoning)

        self.assertEqual(["Install firmware on an offline device."], result["acceptedFunctionalRequirements"])
        suggestions = [item["text"] for item in result["suggestedEnhancements"]]
        self.assertIn("Provide automatic rollback after a failed firmware update.", suggestions)
        self.assertIn("Require role-based authorization for firmware installation.", suggestions)
        self.assertIn("Add deployment recovery diagnostics.", suggestions)

    def test_business_concepts_are_distinct_and_useful(self) -> None:
        analysis = {
            "functionalRequirements": ["Install firmware on an offline device."],
            "actors": [],
            "requirementIntent": {"capabilities": ["Offline Firmware Update"]},
        }

        result = self.engine.govern(self.requirement, analysis, {"report": {}}, self.reasoning)
        values = result["governedValues"]

        self.assertNotEqual(values["businessGoal"], values["problemStatement"])
        self.assertNotEqual(values["businessGoal"], "Install firmware on an offline device.")
        self.assertIn("maintenance", values["businessValue"].casefold())
        self.assertEqual("Maintenance Engineer", values["primaryActor"])

    def test_every_governed_statement_has_provenance(self) -> None:
        analysis = {
            "functionalRequirements": ["Install firmware on an offline device."],
            "nonFunctionalRequirements": ["Firmware installation completes within 10 minutes."],
            "actors": [],
            "risks": ["A failed installation may leave the device unavailable."],
            "openQuestions": ["Which firmware formats are supported?"],
            "requirementIntent": {"capabilities": ["Offline Firmware Update"]},
        }

        result = self.engine.govern(self.requirement, analysis, {"report": {}}, self.reasoning)

        self.assertTrue(result["statements"])
        required = {
            "id", "category", "classification", "source", "provider", "model",
            "promptVersion", "confidence", "evidenceReferences", "generatedAt",
            "approvedStatus", "why",
        }
        for statement in result["statements"]:
            self.assertTrue(required.issubset(statement))
            self.assertIn(statement["classification"], {
                "SOURCE", "EVIDENCE", "AI_INFERRED", "AI_SUGGESTION", "UNKNOWN",
            })

    def test_engineering_evidence_can_support_otherwise_guarded_behavior(self) -> None:
        analysis = {
            "functionalRequirements": ["Require authorization for firmware installation."],
            "actors": [],
            "requirementIntent": {"capabilities": ["Offline Firmware Update"]},
        }
        discovery = {"report": {"repositoryEvidence": [{
            "title": "FirmwareAuthorizationPolicy",
            "reason": "Authorization policy controls firmware installation.",
            "sourceReference": "repository:firmware:authorization",
        }]}}

        result = self.engine.govern(self.requirement, analysis, discovery, self.reasoning)

        self.assertEqual(
            ["Require authorization for firmware installation."],
            result["acceptedFunctionalRequirements"],
        )
        statement = next(item for item in result["statements"] if item["category"] == "Functional Requirement")
        self.assertEqual("EVIDENCE", statement["classification"])


if __name__ == "__main__":
    unittest.main()
