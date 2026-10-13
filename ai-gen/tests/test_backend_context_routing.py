"""Tests for /context routing metadata."""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from backend.app import (
        ContextRequest,
        ExecutionValidationRequest,
        PipelineCreateRequest,
        PipelineStageRequest,
        build_context,
        capabilities,
        create_assistant_pipeline,
        get_handoff_markdown,
        refinement_config,
        refinement_debug_curl,
        refinement_raw_http_test,
        refinement_test,
        run_pipeline_epic_plan,
        run_pipeline_stage,
        validate_execution_result,
    )
    from backend.orchestrator.react_controller import PipelineController
    from backend.repo_context.manager import RepoContextManager
    from backend.repo_context.models import BranchMeta, RepoMeta
    from backend.repo_context.storage import write_json
except ModuleNotFoundError:
    ContextRequest = None
    ExecutionValidationRequest = None
    build_context = None
    capabilities = None
    get_handoff_markdown = None
    refinement_config = None
    refinement_debug_curl = None
    refinement_raw_http_test = None
    refinement_test = None
    validate_execution_result = None
    PipelineCreateRequest = None
    PipelineStageRequest = None
    create_assistant_pipeline = None
    run_pipeline_epic_plan = None
    run_pipeline_stage = None
    PipelineController = None
    RepoContextManager = None
    BranchMeta = None
    RepoMeta = None
    write_json = None


class BackendContextRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        if ContextRequest is None or build_context is None:
            self.skipTest("FastAPI is not installed in this Python interpreter")

    def test_context_response_includes_routing_metadata(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value="/usr/bin/codex"):
            response = build_context(ContextRequest(query="Fix login bug"))

        data = response.model_dump() if hasattr(response, "model_dump") else response.dict()
        self.assertEqual(data["execution_target"], "codex")
        self.assertIn("execution_reason", data)
        self.assertEqual(data["available_targets"]["codex"], True)
        self.assertIn("optimized_prompt", data)
        self.assertIn("planning_enabled", data)
        self.assertIn("plan", data)
        self.assertIn("plan_summary", data)
        self.assertTrue(data["planning_enabled"])
        self.assertEqual(data["prompt_mode"], "execute")
        self.assertIn("Do not repeat broad repo analysis unless necessary.", data["optimized_prompt"])
        self.assertNotIn("## Plan", data["optimized_prompt"])
        self.assertEqual(data["execution_validation"], None)
        self.assertEqual(data["drift_detected"], False)
        self.assertEqual(data["constraint_violations"], [])
        self.assertEqual(data["risky_changes"], [])
        self.assertEqual(data["semantic_mapping_applied"], False)
        self.assertEqual(data["refinement_used"], False)
        self.assertEqual(data["refinement_source"], "none")

    def test_forced_codex_unavailable_returns_preview_only(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value=None):
            response = build_context(ContextRequest(query="Fix login bug", routing_mode="codex"))

        data = response.model_dump() if hasattr(response, "model_dump") else response.dict()
        self.assertEqual(data["execution_target"], "preview_only")

    def test_capabilities_includes_status_metadata(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value=None):
            data = capabilities()

        self.assertEqual(data["backend_up"], True)
        self.assertIn("codex_available", data)
        self.assertIn("local_enabled", data)
        self.assertIn("local_available", data)
        self.assertIn("warnings", data)

    def test_repo_aware_fields_do_not_break_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "backend.app.repo_context_manager",
            RepoContextManager(temp_dir),
        ), patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value="/usr/bin/codex"):
            response = build_context(
                ContextRequest(
                    query="Fix login bug",
                    repo_id="repo_123",
                    branch_name="feature/login-ui",
                    session_id="session-1",
                    ide="vscode",
                    workspace_root="/repo/project",
                    open_files=["backend/auth.py"],
                    current_file="backend/auth.py",
                )
            )

        data = response.model_dump() if hasattr(response, "model_dump") else response.dict()
        self.assertIn("optimized_prompt", data)
        self.assertEqual(data["execution_target"], "codex")

    def test_context_auto_derives_repo_id_and_saves_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "backend.app.repo_context_manager",
            RepoContextManager(temp_dir),
        ), patch("backend.repo_context.manager.detect_git_remote", return_value="git@github.com:org/project.git"), patch(
            "backend.repo_context.manager.detect_git_branch", return_value="feature/login-ui"
        ), patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value="/usr/bin/codex"):
            response = build_context(
                ContextRequest(
                    query="Fix login bug",
                    workspace_root="/repo/project",
                    session_id="session-1",
                    ide="vscode",
                    open_files=["backend/auth.py"],
                    current_file="backend/auth.py",
                )
            )

            data = response.model_dump() if hasattr(response, "model_dump") else response.dict()
            manager = RepoContextManager(temp_dir)
            session = manager.load_session(data["resolved_repo_id"], "session-1")

        self.assertTrue(data["resolved_repo_id"].startswith("repo_"))
        self.assertEqual(data["resolved_branch_name"], "feature/login-ui")
        self.assertEqual(data["repo_identity_mode"], "git_remote")
        self.assertIsNotNone(session)
        self.assertEqual(session["current_file"], "backend/auth.py")

    def test_git_detection_failure_falls_back_to_path_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "backend.app.repo_context_manager",
            RepoContextManager(temp_dir),
        ), patch("backend.repo_context.manager.detect_git_remote", return_value=None), patch(
            "backend.repo_context.manager.detect_git_branch", return_value=None
        ), patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value="/usr/bin/codex"):
            response = build_context(ContextRequest(query="Fix login bug", workspace_root="/repo/project"))

        data = response.model_dump() if hasattr(response, "model_dump") else response.dict()
        self.assertEqual(data["repo_identity_mode"], "path_fallback")
        self.assertEqual(data["resolved_branch_name"], "default")

    def test_context_response_reports_retrieval_bias_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RepoContextManager(temp_dir)
            paths = manager.init_repo(RepoMeta(repo_id="repo_123", repo_name="Project"))
            manager.init_branch("repo_123", BranchMeta(repo_id="repo_123", branch_name="main"))
            write_json(paths.logic_store, [{"id": "Login", "name": "Login Flow", "files": ["backend/auth.py"]}])
            write_json(paths.file_index, [{"path": "backend/auth.py", "module": "backend", "language": "python"}])

            with patch("backend.app.repo_context_manager", manager), patch.dict(os.environ, {}, clear=True), patch(
                "shutil.which", return_value="/usr/bin/codex"
            ):
                response = build_context(
                    ContextRequest(
                        query="Fix login bug",
                        repo_id="repo_123",
                        branch_name="main",
                        session_id="session-1",
                        workspace_root="/repo/project",
                        current_file="backend/auth.py",
                        open_files=["backend/auth.py"],
                    )
                )

        data = response.model_dump() if hasattr(response, "model_dump") else response.dict()
        self.assertEqual(data["retrieval_bias_applied"], True)
        self.assertEqual(data["session_bias_summary"]["current_file"], "backend/auth.py")

    def test_context_bootstraps_repo_index_on_first_use(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as storage:
            root = Path(temp_dir)
            (root / "backend").mkdir()
            (root / "backend" / "AuthController.py").write_text("class LoginAuth:\n    def login(self): pass\n", encoding="utf-8")
            manager = RepoContextManager(storage)

            with patch("backend.app.repo_context_manager", manager), patch(
                "backend.repo_context.manager.detect_git_remote", return_value=None
            ), patch("backend.repo_context.manager.detect_git_branch", return_value="main"), patch.dict(
                os.environ, {}, clear=True
            ), patch("shutil.which", return_value="/usr/bin/codex"):
                response = build_context(
                    ContextRequest(
                        query="Fix login bug",
                        workspace_root=temp_dir,
                        session_id="s1",
                        current_file="backend/AuthController.py",
                    )
                )

            data = response.model_dump() if hasattr(response, "model_dump") else response.dict()
            paths = manager.paths(data["resolved_repo_id"])

            self.assertEqual(data["indexing_performed"], True)
            self.assertEqual(data["detected_flow"], "login")
            self.assertIn("login", data["related_flows"])
            self.assertIn("session", data["related_flows"])
            self.assertEqual(data["flow_files_count"], 1)
            self.assertEqual(data["bug_surface"], None)
            self.assertEqual(data["likely_bug_hotspots"][0]["file"], "backend/AuthController.py")
            self.assertEqual(data["prompt_mode"], "execute")
            self.assertEqual(data["execution_confidence_level"], "high")
            self.assertIn("backend/AuthController.py", data["selected_execution_files"])
            self.assertIn("# Likely Breakpoints", data["optimized_prompt"])
            self.assertIn("Related:", data["optimized_prompt"])
            self.assertTrue(paths.file_index.exists())
            self.assertTrue(paths.summaries.exists())

    def test_non_bug_context_omits_bug_hotspots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as storage:
            root = Path(temp_dir)
            (root / "backend").mkdir()
            (root / "backend" / "AuthController.py").write_text("class LoginAuth:\n    def login(self): pass\n", encoding="utf-8")
            manager = RepoContextManager(storage)

            with patch("backend.app.repo_context_manager", manager), patch(
                "backend.repo_context.manager.detect_git_remote", return_value=None
            ), patch("backend.repo_context.manager.detect_git_branch", return_value="main"), patch.dict(
                os.environ, {}, clear=True
            ), patch("shutil.which", return_value="/usr/bin/codex"):
                response = build_context(
                    ContextRequest(
                        query="Add login feature",
                        workspace_root=temp_dir,
                        session_id="s1",
                        current_file="backend/AuthController.py",
                    )
                )

            data = response.model_dump() if hasattr(response, "model_dump") else response.dict()

            self.assertEqual(data["likely_bug_hotspots"], [])
            self.assertIsNone(data["bug_surface"])
            self.assertNotIn("# Likely Breakpoints", data["optimized_prompt"])

    def test_explain_context_uses_respond_prompt_mode(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value="/usr/bin/codex"):
            response = build_context(ContextRequest(query="Explain login flow"))

        data = response.model_dump() if hasattr(response, "model_dump") else response.dict()
        self.assertEqual(data["prompt_mode"], "respond")
        self.assertIn("Instructions:", data["optimized_prompt"])
        self.assertIn("Keep answer concise.", data["optimized_prompt"])

    def test_ambiguous_architecture_context_uses_explore_prompt_mode(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value="/usr/bin/codex"):
            response = build_context(ContextRequest(query="Design new system architecture"))

        data = response.model_dump() if hasattr(response, "model_dump") else response.dict()
        self.assertEqual(data["prompt_mode"], "explore")
        self.assertIn("# Exploration Task", data["optimized_prompt"])

    def test_execution_validation_endpoint_reports_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            response = validate_execution_result(
                ExecutionValidationRequest(
                    repo_root=temp_dir,
                    selected_files=["src/LoginScreen.kt"],
                    changed_files=["src/LoginScreen.kt", "docs/readme.md"],
                    prompt_mode="execute",
                )
            )

        self.assertEqual(response["drift_detected"], True)
        self.assertEqual(response["execution_validation"]["out_of_scope_files"], ["docs/readme.md"])
        self.assertEqual(response["retry_required"], True)
        self.assertEqual(response["retry_plan"]["strategy"], "narrow_scope")
        self.assertIn("Do not modify files outside this list.", response["corrected_execution_prompt"])

    def test_handoff_markdown_endpoint_returns_readable_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_HANDOFF_ROOT": temp_dir}, clear=False):
            from backend.handoff.storage import save_handoff

            save_handoff(
                {
                    "handoff_id": "handoff_123_dev_v1",
                    "pipeline_id": "pipeline_1",
                    "work_item_id": "123",
                    "stage": "dev",
                    "version": 1,
                    "status": "approved",
                    "created_at": "now",
                    "approved_at": "now",
                    "source_stage": "dev",
                    "target_stages": ["test"],
                    "summary": "Fix login validation",
                    "content": {"execution_packet": "Fix the login validation safely."},
                    "refinement": {},
                    "repo_context": {},
                    "constraints": ["Do not bypass credential validation."],
                    "open_questions": [],
                    "next_actions": [],
                }
            )

            markdown = get_handoff_markdown("handoff_123_dev_v1")

        self.assertIn("# DEV Handoff", markdown)
        self.assertIn("Fix login validation", markdown)

    def test_handoff_by_id_returns_execution_packet_and_selected_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {"AI_GEN_HANDOFF_ROOT": temp_dir}, clear=False):
            from backend.app import get_handoff_by_id
            from backend.handoff.storage import save_handoff

            save_handoff(
                {
                    "handoff_id": "handoff_123_dev_v1",
                    "pipeline_id": "pipeline_1",
                    "work_item_id": "123",
                    "stage": "dev",
                    "version": 1,
                    "status": "approved",
                    "created_at": "now",
                    "approved_at": "now",
                    "source_stage": "dev",
                    "target_stages": ["test"],
                    "summary": "Fix login validation",
                    "content": {
                        "execution_packet": "Fix the login validation safely.",
                        "selected_files": ["src/LoginScreen.tsx"],
                    },
                    "refinement": {"variants": ["phone_otp"]},
                    "repo_context": {},
                    "constraints": ["Do not bypass credential validation."],
                    "open_questions": ["Is OTP required?"],
                    "next_actions": [],
                }
            )

            handoff = get_handoff_by_id("handoff_123_dev_v1")

        self.assertEqual(handoff["execution_packet"], "Fix the login validation safely.")
        self.assertEqual(handoff["selected_files"], ["src/LoginScreen.tsx"])
        self.assertEqual(handoff["refinement"]["variants"], ["phone_otp"])

    def test_run_stage_regenerate_can_apply_feedback_inline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "backend.app.pipeline_controller",
            PipelineController(temp_dir),
        ):
            pipeline = create_assistant_pipeline(
                PipelineCreateRequest(
                    source="azure_devops",
                    work_item={
                        "id": 123,
                        "title": "Ai Gen Extension Test",
                        "description": "Focus first on phone number input and otp verification step.",
                        "acceptanceCriteria": "Phone number input is required.",
                        "tags": ["Android"],
                    },
                    refinement={
                        "base_flows": ["login", "otp_verification"],
                        "variants": ["phone_otp"],
                        "surfaces": ["ui_screen"],
                        "fields": ["phone_number", "otp"],
                        "validations": ["auth_required"],
                    },
                )
            )
            pipeline = run_pipeline_stage(
                pipeline["pipeline_id"],
                PipelineStageRequest(stage="ba"),
            )
            pipeline = run_pipeline_stage(
                pipeline["pipeline_id"],
                PipelineStageRequest(
                    stage="ba",
                    regenerate=True,
                    feedback_comment="yes retry policy 3 times max. second factor needed after primary input succeeds. yes otp is needed",
                    feedback_author="azure_devops",
                ),
            )

        self.assertIn("Review clarifications", pipeline["stages"]["ba"]["output"]["refined_requirement"])
        self.assertNotIn(
            "Clarify OTP retry and expiry policy.",
            pipeline["stages"]["ba"]["output"]["unknowns"],
        )
        self.assertNotIn(
            "Is OTP or a second-factor step required after the primary input succeeds?",
            pipeline["stages"]["ba"]["output"]["unknowns"],
        )

    def test_context_includes_refinement_metadata_when_provider_returns_data(self) -> None:
        refinement_result = {
            "semantic_mapping_applied": True,
            "refinement_used": True,
            "refinement_source": "phi",
            "refinement_provider": "azure_phi",
            "refinement_reason": "provider returned structured refinement",
            "phi_used": True,
            "phi_status": "used",
            "refinement": {
                "base_flows": ["login", "otp_verification"],
                "variants": ["phone_otp"],
                "surfaces": ["ui_screen", "authentication"],
                "fields": ["phone_number", "otp"],
                "validations": ["required", "format", "length_limit"],
                "scope_hints": ["login screen input", "phone validation", "submit action"],
                "unknowns": ["Is OTP required after phone submission?"],
                "confidence": "medium",
                "base_flow": "login",
                "variant": "phone_otp",
                "surface": "ui_screen",
                "first_pass_scope": ["login screen input", "phone validation", "submit action"],
            },
        }
        with patch.dict(
            os.environ,
            {
                "AI_GEN_REFINER_ENABLED": "1",
                "AI_GEN_REFINER_PROVIDER": "azure_phi",
                "AI_GEN_REFINER_ENDPOINT": "https://example.test",
                "AI_GEN_REFINER_API_KEY": "secret",
                "AI_GEN_REFINER_MODEL": "Phi-4-mini-instruct",
            },
            clear=True,
        ), patch("backend.app.refine_task", return_value=refinement_result), patch(
            "shutil.which", return_value="/usr/bin/codex"
        ):
            response = build_context(
                ContextRequest(
                    query="Add a login screen with phone number",
                    source="azure_devops",
                    work_item={"title": "Add a login screen with phone number", "type": "User Story"},
                )
            )

        data = response.model_dump() if hasattr(response, "model_dump") else response.dict()
        self.assertEqual(data["refinement_used"], True)
        self.assertEqual(data["semantic_mapping_applied"], True)
        self.assertEqual(data["refinement_source"], "phi")
        self.assertEqual(data["phi_status"], "used")
        self.assertEqual(data["refined_variant"], "phone_otp")
        self.assertEqual(data["refined_base_flows"], ["login", "otp_verification"])
        self.assertEqual(data["refined_surface"], "ui_screen")
        self.assertIn("phone_number", data["optimized_prompt"])
        self.assertIn("otp", data["optimized_prompt"])
        self.assertIn("# Unknowns", data["optimized_prompt"])

    def test_context_incremental_refresh_reports_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as storage:
            root = Path(temp_dir)
            (root / "backend").mkdir()
            (root / "backend" / "auth.py").write_text("class LoginAuth:\n    def login(self): pass\n", encoding="utf-8")
            manager = RepoContextManager(storage)
            resolved = manager.resolve_or_register_repo(repo_root=temp_dir, branch_name="main")
            from backend.repo_context.indexer import bootstrap_repo_index

            bootstrap_repo_index(resolved["repo_id"], temp_dir, storage_root=storage)
            (root / "backend" / "auth.py").write_text("class LoginAuth:\n    def login(self):\n        session=True\n", encoding="utf-8")

            with patch("backend.app.repo_context_manager", manager), patch(
                "backend.repo_context.indexer.get_changed_files", return_value=["backend/auth.py"]
            ), patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value="/usr/bin/codex"):
                response = build_context(
                    ContextRequest(
                        query="Fix login bug",
                        repo_id=resolved["repo_id"],
                        branch_name="main",
                        workspace_root=temp_dir,
                        current_file="backend/auth.py",
                    )
                )

        data = response.model_dump() if hasattr(response, "model_dump") else response.dict()
        self.assertEqual(data["incremental_update_performed"], True)
        self.assertEqual(data["changed_files_count"], 1)
        self.assertIn("login", data["related_flows"])

    def test_stage_feedback_endpoint_stores_feedback(self) -> None:
        from backend.app import (
            PipelineCreateRequest,
            PipelineStageFeedbackRequest,
            add_pipeline_stage_feedback,
            create_assistant_pipeline,
            run_pipeline_stage,
            PipelineStageRequest,
        )

        with tempfile.TemporaryDirectory() as temp_dir, patch("backend.app.pipeline_controller", pipeline_controller := type("Holder", (), {})()):
            from backend.orchestrator.react_controller import PipelineController

            controller = PipelineController(temp_dir)
            pipeline_controller.create_pipeline = controller.create_pipeline
            pipeline_controller.run_stage = controller.run_stage
            pipeline_controller.add_stage_feedback = controller.add_stage_feedback
            pipeline = create_assistant_pipeline(PipelineCreateRequest(work_item={"id": 123, "title": "Add login screen"}))
            run_pipeline_stage(pipeline["pipeline_id"], PipelineStageRequest(stage="ba"))
            updated = add_pipeline_stage_feedback(
                pipeline["pipeline_id"],
                PipelineStageFeedbackRequest(stage="ba", comment="Clarify acceptance criteria", author="reviewer"),
            )

        self.assertEqual(updated["stages"]["ba"]["review_feedback"][0]["comment"], "Clarify acceptance criteria")

    def test_run_epic_plan_endpoint_executes_internal_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch("backend.app.pipeline_controller", pipeline_controller := type("Holder", (), {})()):
            controller = PipelineController(temp_dir)
            pipeline_controller.create_pipeline = controller.create_pipeline
            pipeline_controller.run_epic_plan = controller.run_epic_plan
            pipeline = create_assistant_pipeline(PipelineCreateRequest(work_item={"id": 777, "type": "Epic", "title": "Identity modernization"}))
            updated = run_pipeline_epic_plan(
                pipeline["pipeline_id"],
                PipelineStageRequest(stage="epic_analysis"),
            )

        self.assertEqual(updated["workflow_state"], "review_ready")
        self.assertTrue(updated["draft_work_items"])
        self.assertTrue(updated["stages"]["review"]["output"])
        self.assertTrue(updated["stages"]["feature_generation"]["approved"])
        self.assertTrue(updated["stages"]["story_generation"]["approved"])
        self.assertNotEqual(updated["stages"]["feature_generation"]["status"], "locked")

    def test_phi_diagnostic_endpoint_returns_parse_status_safely(self) -> None:
        class FakeProvider:
            def is_enabled(self) -> bool:
                return True

            def status_snapshot(self) -> dict:
                return {
                    "backend_status": "ok",
                    "provider": "azure_phi",
                    "configured": True,
                    "enabled": True,
                    "endpoint_present": True,
                    "api_key_present": True,
                    "model": "Phi-4-mini-instruct",
                    "api_version": "2024-05-01-preview",
                    "endpoint_host": "example.test",
                    "endpoint_path": "/models",
                    "final_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "method": "POST",
                    "timeout_seconds": 60,
                    "ping_timeout_seconds": 60,
                    "diagnostic_timeout_seconds": 180,
                    "max_tokens": 300,
                    "response_format_enabled": True,
                }

            def probe_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 800) -> dict:
                return {
                    "backend_status": "ok",
                    "provider": "azure_phi",
                    "configured": True,
                    "enabled": True,
                    "endpoint_present": True,
                    "api_key_present": True,
                    "model": "Phi-4-mini-instruct",
                    "api_version": "2024-05-01-preview",
                    "endpoint_host": "example.test",
                    "endpoint_path": "/models",
                    "final_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "method": "POST",
                    "http_status": 200,
                    "raw_content": '{"base_flows":["login"]}',
                    "parsed_json": {"base_flows": ["login"]},
                    "parse_error": "",
                    "elapsed_ms": 25,
                    "timeout_seconds": 8,
                    "attempted_url_preview": "https://example.test/chat/completions",
                    "attempted_method": "POST",
                    "max_tokens": max_tokens,
                    "response_format_enabled": True,
                    "json_mode_attempted": True,
                    "json_mode_retry_without_response_format": False,
                    "attempts": [],
                    "failure_reason": "",
                    "failure_message": "",
                }

        request = type("Req", (), {"query": "sign in", "context": {}})()
        with patch("backend.app.get_refinement_provider", return_value=FakeProvider()), patch(
            "backend.app.get_refiner_status",
            return_value={"provider": "azure_phi", "configured": True},
        ):
            data = refinement_test(request)

        self.assertEqual(data["provider"], "azure_phi")
        self.assertEqual(data["phi_status"], "used")
        self.assertIn("login", data["validated_refinement"]["base_flows"])
        self.assertIn("base_flows", data["raw_response_preview"])
        self.assertEqual(data["max_tokens"], 300)
        self.assertTrue(data["response_format_enabled"])

    def test_phi_diagnostic_endpoint_times_out_cleanly(self) -> None:
        class SlowProvider:
            def is_enabled(self) -> bool:
                return True

            def status_snapshot(self) -> dict:
                return {
                    "backend_status": "ok",
                    "provider": "azure_phi",
                    "configured": True,
                    "enabled": True,
                    "endpoint_present": True,
                    "api_key_present": True,
                    "model": "Phi-4-mini-instruct",
                    "api_version": "2024-05-01-preview",
                    "endpoint_host": "example.test",
                    "endpoint_path": "/models",
                    "final_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "method": "POST",
                    "timeout_seconds": 60,
                    "ping_timeout_seconds": 60,
                    "diagnostic_timeout_seconds": 180,
                    "max_tokens": 300,
                    "response_format_enabled": True,
                }

            def probe_json(
                self,
                system_prompt: str,
                user_prompt: str,
                max_tokens: int = 800,
                timeout_seconds=None,
            ) -> dict:
                time.sleep(2.2)
                return {
                    "configured": True,
                    "http_status": 200,
                    "raw_content": '{"base_flows":["login"]}',
                    "parsed_json": {"base_flows": ["login"]},
                    "parse_error": "",
                }

        request = type("Req", (), {"query": "sign in", "context": {}})()
        with patch("backend.app.get_refinement_provider", return_value=SlowProvider()), patch(
            "backend.app.get_refiner_status",
            return_value={"provider": "azure_phi", "configured": True},
        ), patch.dict(
            os.environ,
            {
                "AI_GEN_REFINER_TIMEOUT_SECONDS": "1",
                "AI_GEN_REFINER_DIAGNOSTIC_TIMEOUT_SECONDS": "2",
            },
            clear=False,
        ):
            started = time.time()
            data = refinement_test(request)
            elapsed = time.time() - started

        self.assertLess(elapsed, 2.35)
        self.assertEqual(data["phi_status"], "diagnostic_timeout")
        self.assertEqual(data["parse_error"], "DiagnosticTimeout")
        self.assertEqual(data["fallback_used"], True)
        self.assertEqual(data["provider_timeout_seconds"], 1)
        self.assertEqual(data["timeout_seconds"], 2)
        self.assertEqual(data["diagnostic_timeout_seconds"], 2)
        self.assertEqual(data["attempts"][0]["status"], "diagnostic_timeout")

    def test_phi_ping_mode_uses_small_request(self) -> None:
        captured = {}

        class PingProvider:
            def is_enabled(self) -> bool:
                return True

            def status_snapshot(self) -> dict:
                return {
                    "backend_status": "ok",
                    "provider": "azure_phi",
                    "configured": True,
                    "enabled": True,
                    "endpoint_present": True,
                    "api_key_present": True,
                    "model": "Phi-4-mini-instruct",
                    "api_version": "2024-05-01-preview",
                    "endpoint_host": "example.test",
                    "endpoint_path": "/models",
                    "final_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "method": "POST",
                    "timeout_seconds": 60,
                    "ping_timeout_seconds": 60,
                    "diagnostic_timeout_seconds": 180,
                    "max_tokens": 300,
                    "response_format_enabled": True,
                }

            def probe_json(
                self,
                system_prompt: str,
                user_prompt: str,
                max_tokens: int = 800,
                timeout_seconds=None,
                response_format_enabled=None,
                allow_retry_without_response_format=True,
            ) -> dict:
                captured["response_format_enabled"] = response_format_enabled
                captured["allow_retry_without_response_format"] = allow_retry_without_response_format
                return {
                    "backend_status": "ok",
                    "provider": "azure_phi",
                    "configured": True,
                    "enabled": True,
                    "endpoint_present": True,
                    "api_key_present": True,
                    "model": "Phi-4-mini-instruct",
                    "api_version": "2024-05-01-preview",
                    "endpoint_host": "example.test",
                    "endpoint_path": "/models",
                    "final_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "method": "POST",
                    "http_status": 200,
                    "raw_content": '{"status":"ok"}',
                    "parsed_json": {"status": "ok"},
                    "parse_error": "",
                    "elapsed_ms": 42,
                    "timeout_seconds": timeout_seconds,
                    "attempted_url_preview": "https://example.test/chat/completions",
                    "attempted_method": "POST",
                    "max_tokens": max_tokens,
                    "response_format_enabled": False,
                    "json_mode_attempted": False,
                    "json_mode_retry_without_response_format": False,
                    "attempts": [],
                    "failure_reason": "",
                    "failure_message": "",
                }

        request = type("Req", (), {"query": "ping", "context": {}, "mode": "ping"})()
        with patch("backend.app.get_refinement_provider", return_value=PingProvider()), patch(
            "backend.app.get_refiner_status",
            return_value={"provider": "azure_phi", "configured": True},
        ):
            data = refinement_test(request)

        self.assertEqual(data["mode"], "ping")
        self.assertEqual(data["max_tokens"], 50)
        self.assertEqual(data["phi_status"], "success")
        self.assertEqual(data["parsed_json"]["status"], "ok")
        self.assertFalse(captured["response_format_enabled"])
        self.assertFalse(captured["allow_retry_without_response_format"])

    def test_phi_small_refine_mode_returns_parsed_json(self) -> None:
        class SmallProvider:
            def is_enabled(self) -> bool:
                return True

            def status_snapshot(self) -> dict:
                return {
                    "backend_status": "ok",
                    "provider": "azure_phi",
                    "configured": True,
                    "enabled": True,
                    "endpoint_present": True,
                    "api_key_present": True,
                    "model": "Phi-4-mini-instruct",
                    "api_version": "2024-05-01-preview",
                    "endpoint_host": "example.test",
                    "endpoint_path": "/models",
                    "final_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "method": "POST",
                    "timeout_seconds": 60,
                    "ping_timeout_seconds": 60,
                    "diagnostic_timeout_seconds": 180,
                    "max_tokens": 300,
                    "response_format_enabled": True,
                }

            def probe_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 800, timeout_seconds=None) -> dict:
                return {
                    "backend_status": "ok",
                    "provider": "azure_phi",
                    "configured": True,
                    "enabled": True,
                    "endpoint_present": True,
                    "api_key_present": True,
                    "model": "Phi-4-mini-instruct",
                    "api_version": "2024-05-01-preview",
                    "endpoint_host": "example.test",
                    "endpoint_path": "/models",
                    "final_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "method": "POST",
                    "http_status": 200,
                    "raw_content": '{"domain":"travel","features":["booking","payments"]}',
                    "parsed_json": {"domain": "travel", "features": ["booking", "payments"]},
                    "parse_error": "",
                    "elapsed_ms": 55,
                    "timeout_seconds": timeout_seconds,
                    "attempted_url_preview": "https://example.test/chat/completions",
                    "attempted_method": "POST",
                    "max_tokens": max_tokens,
                    "response_format_enabled": True,
                    "json_mode_attempted": True,
                    "json_mode_retry_without_response_format": False,
                    "attempts": [],
                    "failure_reason": "",
                    "failure_message": "",
                }

        request = type("Req", (), {"query": "WhatsApp Hotel Booking Platform", "context": {}, "mode": "small_refine"})()
        with patch("backend.app.get_refinement_provider", return_value=SmallProvider()), patch(
            "backend.app.get_refiner_status",
            return_value={"provider": "azure_phi", "configured": True},
        ):
            data = refinement_test(request)

        self.assertEqual(data["mode"], "small_refine")
        self.assertEqual(data["phi_status"], "used")
        self.assertEqual(data["parsed_json"]["domain"], "travel")

    def test_small_refine_uses_diagnostic_timeout_env(self) -> None:
        captured = {}

        class SmallProvider:
            def is_enabled(self) -> bool:
                return True

            def status_snapshot(self) -> dict:
                return {
                    "backend_status": "ok",
                    "provider": "azure_phi",
                    "configured": True,
                    "enabled": True,
                    "endpoint_present": True,
                    "api_key_present": True,
                    "model": "Phi-4-mini-instruct",
                    "api_version": "2024-05-01-preview",
                    "endpoint_host": "example.test",
                    "endpoint_path": "/models",
                    "final_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "method": "POST",
                    "timeout_seconds": 60,
                    "ping_timeout_seconds": 60,
                    "diagnostic_timeout_seconds": 180,
                    "max_tokens": 300,
                    "response_format_enabled": True,
                }

            def probe_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 800, timeout_seconds=None, **kwargs) -> dict:
                captured["timeout_seconds"] = timeout_seconds
                return {
                    "backend_status": "ok",
                    "provider": "azure_phi",
                    "configured": True,
                    "enabled": True,
                    "endpoint_present": True,
                    "api_key_present": True,
                    "model": "Phi-4-mini-instruct",
                    "api_version": "2024-05-01-preview",
                    "endpoint_host": "example.test",
                    "endpoint_path": "/models",
                    "final_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "method": "POST",
                    "http_status": 200,
                    "raw_content": '{"domain":"travel","features":["booking"]}',
                    "parsed_json": {"domain": "travel", "features": ["booking"]},
                    "parse_error": "",
                    "elapsed_ms": 50,
                    "timeout_seconds": timeout_seconds,
                    "attempted_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "attempted_method": "POST",
                    "max_tokens": max_tokens,
                    "response_format_enabled": True,
                    "json_mode_attempted": True,
                    "json_mode_retry_without_response_format": False,
                    "attempts": [],
                    "failure_reason": "",
                    "failure_message": "",
                }

        request = type("Req", (), {"query": "WhatsApp Hotel Booking Platform", "context": {}, "mode": "small_refine"})()
        with patch("backend.app.get_refinement_provider", return_value=SmallProvider()), patch.dict(
            os.environ,
            {
                "AI_GEN_REFINER_TIMEOUT_SECONDS": "60",
                "AI_GEN_REFINER_DIAGNOSTIC_TIMEOUT_SECONDS": "180",
            },
            clear=False,
        ):
            data = refinement_test(request)

        self.assertEqual(captured["timeout_seconds"], 60)
        self.assertEqual(data["diagnostic_timeout_seconds"], 180)

    def test_ping_uses_ping_timeout_env(self) -> None:
        captured = {}

        class PingProvider:
            def is_enabled(self) -> bool:
                return True

            def status_snapshot(self) -> dict:
                return {
                    "backend_status": "ok",
                    "provider": "azure_phi",
                    "configured": True,
                    "enabled": True,
                    "endpoint_present": True,
                    "api_key_present": True,
                    "model": "Phi-4-mini-instruct",
                    "api_version": "2024-05-01-preview",
                    "endpoint_host": "example.test",
                    "endpoint_path": "/models",
                    "final_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "method": "POST",
                    "timeout_seconds": 60,
                    "ping_timeout_seconds": 44,
                    "diagnostic_timeout_seconds": 180,
                    "max_tokens": 300,
                    "response_format_enabled": True,
                }

            def probe_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 800, timeout_seconds=None, **kwargs) -> dict:
                captured["timeout_seconds"] = timeout_seconds
                return {
                    "backend_status": "ok",
                    "provider": "azure_phi",
                    "configured": True,
                    "enabled": True,
                    "endpoint_present": True,
                    "api_key_present": True,
                    "model": "Phi-4-mini-instruct",
                    "api_version": "2024-05-01-preview",
                    "endpoint_host": "example.test",
                    "endpoint_path": "/models",
                    "final_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "method": "POST",
                    "http_status": 200,
                    "raw_content": '{"status":"ok"}',
                    "parsed_json": {"status": "ok"},
                    "parse_error": "",
                    "elapsed_ms": 40,
                    "timeout_seconds": timeout_seconds,
                    "attempted_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "attempted_method": "POST",
                    "max_tokens": max_tokens,
                    "response_format_enabled": False,
                    "json_mode_attempted": False,
                    "json_mode_retry_without_response_format": False,
                    "attempts": [],
                    "failure_reason": "",
                    "failure_message": "",
                }

        request = type("Req", (), {"query": "ping", "context": {}, "mode": "ping"})()
        with patch("backend.app.get_refinement_provider", return_value=PingProvider()), patch.dict(
            os.environ,
            {
                "AI_GEN_REFINER_PING_TIMEOUT_SECONDS": "44",
            },
            clear=False,
        ):
            data = refinement_test(request)

        self.assertEqual(captured["timeout_seconds"], 44)
        self.assertEqual(data["provider_timeout_seconds"], 44)

    def test_refinement_debug_curl_hides_api_key(self) -> None:
        class DebugProvider:
            def debug_curl(self, mode: str = "ping") -> str:
                return "curl -H 'api-key: <REDACTED>'"

        with patch("backend.app.get_refinement_provider", return_value=DebugProvider()):
            data = refinement_debug_curl("ping")

        self.assertEqual(data["mode"], "ping")
        self.assertIn("<REDACTED>", data["curl"])

    def test_refinement_config_returns_safe_provider_snapshot(self) -> None:
        class ConfigProvider:
            def safe_config(self) -> dict:
                return {
                    "enabled": True,
                    "provider": "azure_phi",
                    "configured": True,
                    "endpoint_host": "example.test",
                    "endpoint_path": "/models",
                    "model": "Phi-4-mini-instruct",
                    "api_version": "2024-05-01-preview",
                    "timeout_seconds": 60,
                    "ping_timeout_seconds": 60,
                    "diagnostic_timeout_seconds": 180,
                    "response_format_enabled": True,
                    "missing_env": [],
                }

        with patch("backend.app.get_refinement_provider", return_value=ConfigProvider()):
            data = refinement_config()

        self.assertTrue(data["configured"])
        self.assertEqual(data["endpoint_host"], "example.test")

    def test_refinement_raw_http_test_supports_with_and_without_model(self) -> None:
        captured = []

        class RawProvider:
            def is_enabled(self) -> bool:
                return True

            def status_snapshot(self) -> dict:
                return {
                    "backend_status": "ok",
                    "provider": "azure_phi",
                    "configured": True,
                    "enabled": True,
                    "endpoint_present": True,
                    "api_key_present": True,
                    "model": "Phi-4-mini-instruct",
                    "api_version": "2024-05-01-preview",
                    "endpoint_host": "example.test",
                    "endpoint_path": "/models",
                    "final_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "method": "POST",
                    "timeout_seconds": 60,
                    "ping_timeout_seconds": 60,
                    "diagnostic_timeout_seconds": 180,
                    "include_model_field": True,
                    "max_tokens": 300,
                    "response_format_enabled": True,
                }

            def raw_http_test(self, **kwargs) -> dict:
                captured.append(kwargs)
                return {
                    **self.status_snapshot(),
                    "http_status": 200,
                    "response_headers": {"content-type": "application/json"},
                    "response_body_preview": '{"status":"ok"}',
                    "elapsed_ms": 25,
                    "timeout_seconds": kwargs["timeout_seconds"],
                    "include_model_field": kwargs["include_model_field"],
                    "api_version": kwargs.get("api_version_override") or "2024-05-01-preview",
                    "final_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "failure_reason": "",
                    "failure_message": "",
                    "error_type": "",
                    "error_message": "",
                }

        with patch("backend.app.get_refinement_provider", return_value=RawProvider()):
            with_model = refinement_raw_http_test(type("Req", (), {"query": "ping", "mode": "with_model", "include_model_field": None, "api_version": None, "max_tokens": 50})())
            without_model = refinement_raw_http_test(type("Req", (), {"query": "ping", "mode": "without_model", "include_model_field": None, "api_version": None, "max_tokens": 50})())

        self.assertTrue(captured[0]["include_model_field"])
        self.assertFalse(captured[1]["include_model_field"])
        self.assertEqual(with_model["http_status"], 200)
        self.assertEqual(without_model["http_status"], 200)

    def test_refinement_raw_http_test_supports_api_version_override(self) -> None:
        class RawProvider:
            def is_enabled(self) -> bool:
                return True

            def status_snapshot(self) -> dict:
                return {
                    "backend_status": "ok",
                    "provider": "azure_phi",
                    "configured": True,
                    "enabled": True,
                    "endpoint_present": True,
                    "api_key_present": True,
                    "model": "Phi-4-mini-instruct",
                    "api_version": "2024-05-01-preview",
                    "endpoint_host": "example.test",
                    "endpoint_path": "/models",
                    "final_url_preview": "https://example.test/models/chat/completions?api-version=2024-05-01-preview",
                    "method": "POST",
                    "timeout_seconds": 60,
                    "ping_timeout_seconds": 60,
                    "diagnostic_timeout_seconds": 180,
                    "include_model_field": True,
                    "max_tokens": 300,
                    "response_format_enabled": True,
                }

            def raw_http_test(self, **kwargs) -> dict:
                return {
                    **self.status_snapshot(),
                    "http_status": 404,
                    "response_headers": {"x-test": "1"},
                    "response_body_preview": "not found",
                    "elapsed_ms": 40,
                    "timeout_seconds": kwargs["timeout_seconds"],
                    "include_model_field": kwargs["include_model_field"],
                    "api_version": kwargs.get("api_version_override"),
                    "final_url_preview": f"https://example.test/models/chat/completions?api-version={kwargs.get('api_version_override')}",
                    "failure_reason": "http_404_wrong_endpoint_or_model",
                    "failure_message": "Azure Phi endpoint or model path was not found.",
                    "error_type": "HTTPError",
                    "error_message": "404",
                }

        with patch("backend.app.get_refinement_provider", return_value=RawProvider()):
            data = refinement_raw_http_test(type("Req", (), {"query": "ping", "mode": "with_model", "include_model_field": True, "api_version": "2024-10-21", "max_tokens": 50})())

        self.assertEqual(data["api_version"], "2024-10-21")
        self.assertIn("2024-10-21", data["final_url_preview"])


if __name__ == "__main__":
    unittest.main()
