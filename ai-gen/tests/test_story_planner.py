from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.story_planner.service import StoryPlannerService


class FakePhiProvider:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def is_enabled(self) -> bool:
        return True

    def probe_json(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt, **kwargs})
        return {"parsed_json": self.responses.pop(0) if self.responses else {}}


class StoryPlannerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = StoryPlannerService()

    def test_start_session_generates_refined_story_stage(self) -> None:
        session = self.service.start_session("As a customer, I want OTP login so I can securely access my account.")
        self.assertEqual(session["current_stage"], "refined_story")
        self.assertTrue(session["story"]["title"])
        self.assertTrue(session["story"]["description"])
        self.assertTrue(session["story"]["business_value"])

    def test_stage_transition_requires_approval(self) -> None:
        session = self.service.start_session("As a customer, I want OTP login so I can securely access my account.")
        self.assertEqual(session["current_stage"], "refined_story")
        session = self.service.approve_stage(session["session_id"], "refined_story")
        self.assertEqual(session["current_stage"], "acceptance_criteria")
        session = self.service.approve_stage(session["session_id"], "acceptance_criteria")
        self.assertEqual(session["current_stage"], "tasks")

    def test_regenerate_acceptance_updates_criteria(self) -> None:
        session = self.service.start_session("As a customer, I want OTP login so I can securely access my account.")
        session = self.service.approve_stage(session["session_id"], "refined_story")
        session = self.service.regenerate_stage(session["session_id"], "acceptance_criteria", "OTP should expire after 120 seconds.")
        self.assertIn("120 seconds", " ".join(session["acceptance_criteria"]))

    def test_copy_prompt_source_is_final_code_generation_prompt(self) -> None:
        session = self.service.start_session("As a customer, I want OTP login so I can securely access my account.")
        session = self.service.approve_stage(session["session_id"], "refined_story")
        session = self.service.approve_stage(session["session_id"], "acceptance_criteria")
        session = self.service.approve_stage(session["session_id"], "tasks")
        self.assertEqual(session["current_stage"], "azure_devops_creation")
        self.assertTrue(session["code_generation_prompt"].startswith("# Task"))
        self.assertNotIn("routing", session["code_generation_prompt"].lower())

    def test_tasks_are_not_marked_created_before_devops_success(self) -> None:
        session = self.service.start_session("As a customer, I want OTP login so I can securely access my account.")
        session = self.service.approve_stage(session["session_id"], "refined_story")
        session = self.service.approve_stage(session["session_id"], "acceptance_criteria")
        for task in session["tasks"]:
            self.assertEqual(task["status"], "pending")
            self.assertIsNone(task["azure_work_item_id"])

    def test_create_work_items_updates_statuses_only_on_success(self) -> None:
        session = self.service.start_session("As a customer, I want OTP login so I can securely access my account.")
        session = self.service.approve_stage(session["session_id"], "refined_story")
        session = self.service.approve_stage(session["session_id"], "acceptance_criteria")
        session = self.service.approve_stage(session["session_id"], "tasks")
        with patch("backend.story_planner.service._create_story_work_item", return_value={"id": 101}), patch(
            "backend.story_planner.service._create_child_task_work_item",
            side_effect=[{"id": 201}, ValueError("Azure DevOps unavailable"), {"id": 203}],
        ):
            updated = self.service.create_work_items(session["session_id"])
        self.assertEqual(updated["created_story_id"], 101)
        statuses = [task["status"] for task in updated["tasks"]]
        self.assertIn("created", statuses)
        self.assertIn("failed", statuses)

    def test_story_failure_is_not_reported_as_created(self) -> None:
        session = self.service.start_session("As a customer, I want OTP login so I can securely access my account.")
        session = self.service.approve_stage(session["session_id"], "refined_story")
        session = self.service.approve_stage(session["session_id"], "acceptance_criteria")
        session = self.service.approve_stage(session["session_id"], "tasks")
        with patch("backend.story_planner.service._create_story_work_item", side_effect=ValueError("PAT invalid")):
            updated = self.service.create_work_items(session["session_id"])
        self.assertEqual(updated["current_stage"], "azure_devops_creation")
        self.assertEqual(updated["created_summary"]["story"]["status"], "failed")
        self.assertIn("PAT invalid", updated["created_summary"]["story"]["error"])

    def test_creation_preview_uses_approved_story_and_tasks(self) -> None:
        session = self.service.start_session("As a customer, I want OTP login so I can securely access my account.")
        session = self.service.approve_stage(session["session_id"], "refined_story")
        session = self.service.approve_stage(session["session_id"], "acceptance_criteria")
        session = self.service.approve_stage(session["session_id"], "tasks")
        preview = self.service.get_creation_preview(session["session_id"])
        self.assertEqual(preview["preview"]["story"]["type"], "User Story")
        self.assertGreater(len(preview["preview"]["tasks"]), 0)

    def test_task_creation_preview_does_not_send_story_points(self) -> None:
        session = self.service.start_session("As a customer, I want OTP login so I can securely access my account.")
        session = self.service.approve_stage(session["session_id"], "refined_story")
        session = self.service.approve_stage(session["session_id"], "acceptance_criteria")
        session = self.service.approve_stage(session["session_id"], "tasks")
        preview = self.service.get_creation_preview(session["session_id"])
        task_fields = preview["preview"]["tasks"][0]["fields"]
        self.assertNotIn("Microsoft.VSTS.Scheduling.StoryPoints", task_fields)

    def test_user_story_session_creates_child_task_preview_only(self) -> None:
        session = self.service.start_session(
            "Login Screen with OTP and validation",
            work_item_id=12,
            work_item_type="User Story",
        )
        self.assertEqual(session["planner_kind"], "user_story")
        self.assertEqual(session["source_work_item_id"], 12)
        session = self.service.approve_stage(session["session_id"], "refined_story")
        session = self.service.approve_stage(session["session_id"], "acceptance_criteria")
        session = self.service.approve_stage(session["session_id"], "tasks")
        preview = self.service.get_creation_preview(session["session_id"])
        self.assertIsNone(preview["preview"]["story"])
        self.assertEqual(preview["preview"]["parent_work_item_id"], 12)
        self.assertGreater(len(preview["preview"]["tasks"]), 0)

    def test_epic_fallback_does_not_leak_structured_seed_labels(self) -> None:
        session = self.service.start_session(
            "Work Item Type: Epic\n\nTitle: Launch for User\n\nDescription: Release customer-facing launch capabilities.",
            work_item_id=25,
            work_item_type="Epic",
        )

        self.assertEqual(session["planner_kind"], "epic")
        self.assertNotIn("Work Item Type", session["story"]["title"])
        self.assertNotIn("Title:", session["story"]["title"])
        self.assertIn("Launch", session["story"]["title"])

    def test_epic_generates_user_stories_from_approved_features(self) -> None:
        session = self.service.start_session(
            "Launch iOS and Android mobile e-commerce applications",
            work_item_id=25,
            work_item_type="Epic",
        )
        session = self.service.approve_stage(session["session_id"], "refined_story")
        features = session["acceptance_criteria"]
        self.assertGreaterEqual(len(features), 4)

        session = self.service.approve_stage(session["session_id"], "acceptance_criteria")

        self.assertGreaterEqual(len(session["tasks"]), len(features) * 2)
        self.assertIn(features[0], session["tasks"][0]["title"])
        self.assertIn("As a", session["tasks"][0]["description"])
        self.assertNotIn("Backend / API integration", session["tasks"][0]["title"])

    def test_epic_regeneration_preserves_epic_prompting(self) -> None:
        session = self.service.start_session("Launch mobile apps", work_item_type="Epic")
        session = self.service.regenerate_stage(session["session_id"], "refined_story", "Include iOS and Android launch readiness.")

        self.assertEqual(session["planner_kind"], "epic")
        self.assertNotIn("for User", session["story"]["title"])

    def test_creation_result_marks_real_created_statuses(self) -> None:
        session = self.service.start_session("As a customer, I want OTP login so I can securely access my account.")
        session = self.service.approve_stage(session["session_id"], "refined_story")
        session = self.service.approve_stage(session["session_id"], "acceptance_criteria")
        session = self.service.approve_stage(session["session_id"], "tasks")
        task_id = session["tasks"][0]["id"]
        updated = self.service.store_creation_result(
            session["session_id"],
            {"azure_work_item_id": 4001, "status": "created"},
            [{"id": task_id, "title": session["tasks"][0]["title"], "azure_work_item_id": 4002, "status": "created"}],
        )
        self.assertEqual(updated["created_story_id"], 4001)
        self.assertEqual(updated["tasks"][0]["status"], "created")

    def test_phi_refines_story_acceptance_tasks_and_prompt(self) -> None:
        provider = FakePhiProvider(
            [
                {
                    "title": "OTP Login",
                    "description": "As a customer, I want OTP login so I can securely access my account.",
                    "business_value": "Customers can access accounts safely without passwords.",
                },
                {
                    "acceptance_criteria": [
                        "Given a valid phone number, when OTP is requested, then an OTP is sent.",
                        "Given a valid OTP, when submitted before expiry, then the customer is authenticated.",
                    ]
                },
                {
                    "tasks": [
                        {
                            "title": "Build OTP login form",
                            "description": "Create the phone number and OTP entry experience.",
                            "estimated_effort": "M",
                        },
                        {
                            "title": "Validate OTP authentication",
                            "description": "Implement OTP submit, expiry, and retry handling.",
                            "estimated_effort": "M",
                        },
                    ]
                },
                {
                    "code_generation_prompt": "# Task\nImplement OTP login using the approved acceptance criteria."
                },
            ]
        )
        with patch("backend.story_planner.service.get_refinement_provider", return_value=provider):
            session = self.service.start_session("OTP login")
            self.assertEqual(session["story"]["title"], "OTP Login")
            session = self.service.approve_stage(session["session_id"], "refined_story")
            self.assertEqual(session["acceptance_criteria"][0], "Given a valid phone number, when OTP is requested, then an OTP is sent.")
            session = self.service.approve_stage(session["session_id"], "acceptance_criteria")
            self.assertEqual(session["tasks"][0]["title"], "Build OTP login form")
            session = self.service.approve_stage(session["session_id"], "tasks")
            self.assertIn("Implement OTP login", session["code_generation_prompt"])
        self.assertEqual(len(provider.calls), 4)
        self.assertTrue(all(call["response_format_enabled"] is False for call in provider.calls))
        self.assertTrue(all(call["timeout_seconds"] == 10 for call in provider.calls))


if __name__ == "__main__":
    unittest.main()
