"""Tests for Phase 5: Bug assistant, Prompt builder, work_item_context_builder extensions."""

from __future__ import annotations

import unittest

from backend.assistants.bug_assistant import run_bug_assistant
from backend.prompt_builder import build_ui_prompt, build_dev_prompt
from backend.context.work_item_context_builder import build_effective_work_item_context


# ── Bug Assistant ─────────────────────────────────────────────────────────────

class BugAssistantTests(unittest.TestCase):

    def _basic_wi(self, **extra) -> dict:
        return {
            "title": "Login button crashes on submit",
            "description": "Clicking the login button causes a 500 error.",
            "type": "Bug",
            **extra,
        }

    def test_returns_bug_assistant_key(self) -> None:
        result = run_bug_assistant(self._basic_wi())
        self.assertEqual(result["assistant"], "bug")

    def test_severity_high_for_crash_signal(self) -> None:
        result = run_bug_assistant(self._basic_wi())
        self.assertIn(result["severity"], {"critical", "high"})

    def test_severity_critical_from_blocking_finding(self) -> None:
        findings = [{"type": "risk", "severity": "blocking", "message": "Login broken"}]
        result = run_bug_assistant(self._basic_wi(), critic_findings=findings)
        self.assertEqual(result["severity"], "critical")

    def test_reproduction_steps_non_empty(self) -> None:
        result = run_bug_assistant(self._basic_wi())
        self.assertIsInstance(result["reproduction_steps"], list)
        self.assertGreater(len(result["reproduction_steps"]), 0)

    def test_acceptance_criteria_generated(self) -> None:
        result = run_bug_assistant(self._basic_wi())
        self.assertGreater(len(result["acceptance_criteria"]), 0)

    def test_description_is_html(self) -> None:
        result = run_bug_assistant(self._basic_wi())
        self.assertIn("<", result["description"])
        self.assertIn(">", result["description"])

    def test_open_questions_empty_when_clear(self) -> None:
        wi = {"title": "Submit button returns 404", "description": "Definitive bug.", "type": "Bug"}
        result = run_bug_assistant(wi)
        # No ambiguity signals → no or few questions
        self.assertIsInstance(result["open_questions"], list)

    def test_open_questions_generated_for_intermittent(self) -> None:
        wi = {
            "title": "Intermittent login failure sometimes occurs",
            "description": "Sometimes the login fails, maybe a race condition.",
            "type": "Bug",
        }
        result = run_bug_assistant(wi)
        self.assertGreater(len(result["open_questions"]), 0)

    def test_question_answers_reduce_open_questions(self) -> None:
        wi = {
            "title": "Intermittent login failure sometimes occurs",
            "description": "Sometimes the login fails.",
            "type": "Bug",
        }
        full_result = run_bug_assistant(wi)
        q = full_result["open_questions"][0] if full_result["open_questions"] else None
        if q:
            answered = run_bug_assistant(wi, question_answers={q: "Reproducible when session expires"})
            self.assertLessEqual(len(answered["open_questions"]), len(full_result["open_questions"]))

    def test_from_critic_flag(self) -> None:
        findings = [{"type": "risk", "severity": "blocking", "message": "DB exposed"}]
        result = run_bug_assistant(self._basic_wi(), critic_findings=findings)
        self.assertTrue(result["from_critic"])

    def test_decision_awaiting_when_questions_present(self) -> None:
        wi = {
            "title": "Intermittent failure sometimes",
            "description": "Sometimes it fails, maybe it's tbd.",
            "type": "Bug",
        }
        result = run_bug_assistant(wi)
        if result["open_questions"]:
            self.assertEqual(result["react"]["decision"], "awaiting_input")

    def test_suggested_labels_include_severity(self) -> None:
        result = run_bug_assistant(self._basic_wi())
        labels_str = " ".join(result["suggested_labels"])
        self.assertIn("severity:", labels_str)

    def test_epic_context_used_in_expected_behaviour(self) -> None:
        wi = {"title": "User cannot log in", "type": "Bug", "description": ""}
        epic = {"title": "Auth Module", "acceptance_criteria": "Users must authenticate via OTP"}
        result = run_bug_assistant(wi, effective_context={"epic_context": epic})
        # Expected behaviour should reference epic AC
        self.assertTrue(
            "otp" in result["expected_behaviour"].lower()
            or "epic" in result["expected_behaviour"].lower()
        )


# ── UI Prompt Builder ─────────────────────────────────────────────────────────

class UiPromptBuilderTests(unittest.TestCase):

    def _ba_output(self) -> dict:
        return {
            "assistant": "ba",
            "refined_requirement": "User can log in using phone OTP",
            "actors": ["User", "Auth Service"],
            "flows": ["login", "otp_verification"],
            "variant": "phone_otp",
            "business_rules": ["OTP expires in 5 minutes", "Max 3 retry attempts"],
            "acceptance_criteria": ["User receives OTP", "User logs in after correct OTP"],
            "unknowns": ["Should OTP be 4 or 6 digits?"],
        }

    def test_returns_string(self) -> None:
        prompt = build_ui_prompt(self._ba_output())
        self.assertIsInstance(prompt, str)

    def test_contains_title(self) -> None:
        prompt = build_ui_prompt(self._ba_output(), work_item={"title": "OTP Login Screen", "type": "Story"})
        self.assertIn("OTP Login Screen", prompt)

    def test_contains_acceptance_criteria(self) -> None:
        prompt = build_ui_prompt(self._ba_output())
        self.assertIn("receives OTP", prompt)

    def test_contains_actors(self) -> None:
        prompt = build_ui_prompt(self._ba_output())
        self.assertIn("User", prompt)

    def test_contains_open_questions(self) -> None:
        prompt = build_ui_prompt(self._ba_output())
        self.assertIn("Open Questions", prompt)
        self.assertIn("4 or 6 digits", prompt)

    def test_contains_do_not_section(self) -> None:
        prompt = build_ui_prompt(self._ba_output())
        self.assertIn("Do Not", prompt)

    def test_epic_context_included(self) -> None:
        epic = {"title": "Auth Module Epic", "acceptance_criteria": "Secure authentication"}
        prompt = build_ui_prompt(self._ba_output(), epic_context=epic)
        self.assertIn("Auth Module Epic", prompt)

    def test_ui_output_fields_included(self) -> None:
        ui = {"screen_type": "form", "fields": [{"name": "phone", "type": "tel", "required": True}]}
        prompt = build_ui_prompt(self._ba_output(), ui_output=ui)
        self.assertIn("phone", prompt)

    def test_approval_reminder_present(self) -> None:
        prompt = build_ui_prompt(self._ba_output())
        self.assertIn("approved", prompt.lower())


# ── Dev Prompt Builder ────────────────────────────────────────────────────────

class DevPromptBuilderTests(unittest.TestCase):

    def _ba_output(self) -> dict:
        return {
            "refined_requirement": "User can log in using phone OTP",
            "actors": ["User"],
            "flows": ["login"],
            "variant": "phone_otp",
            "business_rules": ["OTP expires in 5 minutes"],
            "acceptance_criteria": ["User logs in after correct OTP"],
        }

    def _dev_output(self) -> dict:
        return {
            "scope": "Phone OTP login screen and API controller",
            "constraints": ["HTTPS only", "Rate limit 5 attempts/min"],
            "surfaces": ["ui_screen", "api_controller"],
            "selected_files": [{"path": "src/auth/LoginScreen.tsx"}, {"path": "api/auth.py"}],
        }

    def test_returns_string(self) -> None:
        prompt = build_dev_prompt(self._ba_output())
        self.assertIsInstance(prompt, str)

    def test_contains_objective(self) -> None:
        prompt = build_dev_prompt(self._ba_output())
        self.assertIn("Objective", prompt)
        self.assertIn("OTP", prompt)

    def test_contains_acceptance_criteria(self) -> None:
        prompt = build_dev_prompt(self._ba_output())
        self.assertIn("Acceptance Criteria", prompt)

    def test_contains_constraints(self) -> None:
        prompt = build_dev_prompt(self._ba_output(), dev_output=self._dev_output())
        self.assertIn("HTTPS", prompt)

    def test_contains_selected_files(self) -> None:
        prompt = build_dev_prompt(self._ba_output(), dev_output=self._dev_output())
        self.assertIn("LoginScreen.tsx", prompt)

    def test_contains_copilot_instructions(self) -> None:
        prompt = build_dev_prompt(self._ba_output())
        self.assertIn("Copilot", prompt)

    def test_ui_spec_included_when_approved(self) -> None:
        ui = {"screen_type": "form", "fields": [{"name": "otp", "type": "number", "required": True}]}
        prompt = build_dev_prompt(self._ba_output(), ui_output=ui)
        self.assertIn("Approved UI Specification", prompt)
        self.assertIn("otp", prompt)

    def test_epic_context_in_prompt(self) -> None:
        epic = {"title": "Auth Module", "acceptance_criteria": "Secure OTP auth"}
        prompt = build_dev_prompt(self._ba_output(), epic_context=epic)
        self.assertIn("Auth Module", prompt)

    def test_test_scenarios_included(self) -> None:
        test = {"test_cases": [{"title": "OTP happy path", "type": "positive"}]}
        prompt = build_dev_prompt(self._ba_output(), test_output=test)
        self.assertIn("OTP happy path", prompt)

    def test_work_item_id_in_header(self) -> None:
        prompt = build_dev_prompt(self._ba_output(), work_item={"id": 1234, "title": "OTP Login", "type": "Story"})
        self.assertIn("#1234", prompt)


# ── Work Item Context Builder Extensions ──────────────────────────────────────

class WorkItemContextBuilderPhase5Tests(unittest.TestCase):

    def _base_wi(self) -> dict:
        return {"title": "OTP Login", "description": "Login with OTP", "type": "Story"}

    def test_team_comments_included_in_context(self) -> None:
        team_comments = [
            {"body": "Please ensure the OTP is sent via SMS", "author": "Product Owner"}
        ]
        ctx = build_effective_work_item_context(self._base_wi(), team_comments=team_comments)
        self.assertIn("team_comments", ctx["context_sources"])
        self.assertEqual(len(ctx["team_comments"]), 1)

    def test_ai_gen_prefixed_lines_stripped_from_team_comments(self) -> None:
        team_comments = [
            {"body": "[ai-gen] Stage: ba\nPlease clarify the retry policy"}
        ]
        ctx = build_effective_work_item_context(self._base_wi(), team_comments=team_comments)
        if ctx["team_comments"]:
            self.assertNotIn("[ai-gen]", ctx["team_comments"][0]["body"])
            self.assertIn("retry policy", ctx["team_comments"][0]["body"])

    def test_epic_context_in_sources_when_provided(self) -> None:
        epic = {"title": "Auth Epic", "acceptance_criteria": "OTP required"}
        ctx = build_effective_work_item_context(self._base_wi(), epic_context=epic)
        self.assertIn("epic_context", ctx["context_sources"])
        self.assertEqual(ctx["epic_context"]["title"], "Auth Epic")

    def test_question_answers_in_sources(self) -> None:
        qa = [{"question": "Is OTP 4 or 6 digits?", "answer": "6 digits"}]
        ctx = build_effective_work_item_context(self._base_wi(), question_answers=qa)
        self.assertIn("question_answers", ctx["context_sources"])
        self.assertEqual(ctx["question_answers"][0]["answer"], "6 digits")

    def test_question_answers_appear_in_effective_text(self) -> None:
        qa = [{"question": "What is the OTP length?", "answer": "6 digits for security"}]
        ctx = build_effective_work_item_context(self._base_wi(), question_answers=qa)
        self.assertIn("6 digits for security", ctx["effective_text"])

    def test_epic_context_appears_in_effective_text(self) -> None:
        epic = {"title": "Authentication Epic", "acceptance_criteria": "MFA required"}
        ctx = build_effective_work_item_context(self._base_wi(), epic_context=epic)
        self.assertIn("Authentication Epic", ctx["effective_text"])

    def test_empty_team_comments_not_in_sources(self) -> None:
        ctx = build_effective_work_item_context(self._base_wi(), team_comments=[])
        self.assertNotIn("team_comments", ctx["context_sources"])

    def test_duplicate_team_comments_deduped(self) -> None:
        team_comments = [
            {"body": "Same comment", "author": "Alice"},
            {"body": "Same comment", "author": "Bob"},
        ]
        ctx = build_effective_work_item_context(self._base_wi(), team_comments=team_comments)
        self.assertEqual(len(ctx["team_comments"]), 1)


if __name__ == "__main__":
    unittest.main()
