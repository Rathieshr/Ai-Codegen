"""Tests for lightweight repo indexing."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.repo_context.indexer import (
    analyze_file,
    bootstrap_repo_index,
    generate_file_summary,
    get_changed_files,
    scan_repo_files,
    update_changed_files,
)
from backend.repo_context.manager import RepoContextManager
from backend.repo_context.models import BranchMeta, RepoMeta
from backend.repo_context.storage import read_json


class RepoIndexerTests(unittest.TestCase):
    def test_scan_repo_files_skips_ignored_folders(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "LoginScreen.kt").write_text("class LoginScreen", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "ignored.js").write_text("function ignored() {}", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("config", encoding="utf-8")

            files = scan_repo_files(temp_dir)

        self.assertEqual(files, ["src/LoginScreen.kt"])

    def test_scan_repo_files_respects_file_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for index in range(3):
                (root / f"file_{index}.py").write_text("def f(): pass", encoding="utf-8")

            files = scan_repo_files(temp_dir, max_files=2)

        self.assertEqual(len(files), 2)

    def test_analyze_file_extracts_language_symbols_hash_and_logic_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "app" / "LoginController.py"
            path.parent.mkdir()
            path.write_text("class LoginController:\n    def authenticate(self):\n        session = True\n", encoding="utf-8")

            record = analyze_file("app/LoginController.py", path)

        self.assertEqual(record["language"], "python")
        self.assertEqual(record["module"], "app")
        self.assertIn("LoginController", record["symbols"])
        self.assertIn("authenticate", record["symbols"])
        self.assertIn("logic_auth_login", record["logic_refs"])
        self.assertIn("logic_session", record["logic_refs"])
        self.assertTrue(record["sha256"])

    def test_summary_generation_uses_keywords(self) -> None:
        summary = generate_file_summary("ui/Dashboard.ts", "function Dashboard() { callApi(); }")

        self.assertIn("dashboard UI", summary)

    def test_bootstrap_repo_index_creates_file_index_summaries_and_graph(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as storage:
            root = Path(temp_dir)
            (root / "backend").mkdir()
            (root / "backend" / "AuthController.py").write_text(
                "class AuthController:\n    def login(self):\n        session = True\n",
                encoding="utf-8",
            )
            manager = RepoContextManager(storage)
            manager.init_repo(RepoMeta(repo_id="repo_123", repo_name="Project", repo_root=temp_dir))

            result = bootstrap_repo_index("repo_123", temp_dir, storage_root=storage)
            paths = manager.paths("repo_123")

            file_index = read_json(paths.file_index, [])
            summaries = read_json(paths.summaries, [])
            logic_store = read_json(paths.logic_store, [])
            graph = read_json(paths.graph, {})

        self.assertEqual(result["indexed_files"], 1)
        self.assertEqual(result["detected_flows"], ["login"])
        self.assertEqual(file_index[0]["path"], "backend/AuthController.py")
        self.assertEqual(file_index[0]["flow"], "login")
        self.assertEqual(file_index[0]["role"], "controller")
        self.assertIn("login/auth", summaries[0]["summary"])
        self.assertIn("logic_auth_login", [unit["id"] for unit in logic_store])
        self.assertIn({"id": "AuthService", "type": "service"}, graph["nodes"])
        self.assertIn({"id": "LoginFlow", "type": "flow"}, graph["nodes"])

    def test_get_changed_files_uses_git_diff(self) -> None:
        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = "src/LoginScreen.kt\nREADME.md\n"
        with patch("subprocess.run", return_value=completed):
            changed = get_changed_files("/repo", "main")

        self.assertEqual(changed, ["src/LoginScreen.kt"])

    def test_incremental_update_modifies_only_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as storage:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "LoginScreen.kt").write_text("class LoginScreen", encoding="utf-8")
            (root / "src" / "Other.kt").write_text("class Other", encoding="utf-8")
            manager = RepoContextManager(storage)
            manager.init_repo(RepoMeta(repo_id="repo_123", repo_name="Project", repo_root=temp_dir))
            manager.init_branch("repo_123", BranchMeta(repo_id="repo_123", branch_name="main"))
            bootstrap_repo_index("repo_123", temp_dir, storage_root=storage)
            (root / "src" / "LoginScreen.kt").write_text("class LoginScreenViewModel", encoding="utf-8")

            with patch("backend.repo_context.indexer.get_changed_files", return_value=["src/LoginScreen.kt"]):
                result = update_changed_files("repo_123", "main", temp_dir, storage_root=storage)

            paths = manager.paths("repo_123")
            file_index = read_json(paths.file_index, [])
            changed_files = read_json(paths.changed_files("main"), {})
            logic_store = read_json(paths.logic_store, [])

        self.assertEqual(result["updated_files"], 1)
        self.assertEqual(result["detected_flows"], ["login"])
        self.assertEqual(len(file_index), 2)
        self.assertEqual(file_index[0]["flow"], "login")
        self.assertEqual(changed_files["modified"], ["src/LoginScreen.kt"])
        self.assertIn("logic_auth_login", [unit["id"] for unit in logic_store])


if __name__ == "__main__":
    unittest.main()
