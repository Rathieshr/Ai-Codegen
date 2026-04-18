"""Tests for /context routing metadata."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from backend.app import ContextRequest, ExecutionValidationRequest, build_context, capabilities, validate_execution_result
    from backend.repo_context.manager import RepoContextManager
    from backend.repo_context.models import BranchMeta, RepoMeta
    from backend.repo_context.storage import write_json
except ModuleNotFoundError:
    ContextRequest = None
    ExecutionValidationRequest = None
    build_context = None
    capabilities = None
    validate_execution_result = None
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


if __name__ == "__main__":
    unittest.main()
