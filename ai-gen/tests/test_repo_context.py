"""Tests for filesystem-backed repo context storage."""

import tempfile
import unittest
from pathlib import Path

from backend.repo_context.manager import (
    RepoContextManager,
    load_repo_registry,
    make_repo_id,
    merge_effective_context,
    normalize_git_remote,
    register_repo_identity,
    resolve_repo_id_from_registry,
)
from backend.repo_context.retrieval_bias import collect_session_bias_signals, rank_logic_units_with_bias
from backend.repo_context.models import BranchMeta, RepoMeta, SessionContext
from backend.repo_context.storage import write_json


class RepoContextTests(unittest.TestCase):
    def test_git_remote_normalization_maps_ssh_and_https(self) -> None:
        self.assertEqual(
            normalize_git_remote("git@github.com:Org/Project.git"),
            "github.com/org/project",
        )
        self.assertEqual(
            normalize_git_remote("https://github.com/org/project.git"),
            "github.com/org/project",
        )
        self.assertEqual(
            normalize_git_remote("https://github.com/org/project"),
            "github.com/org/project",
        )

    def test_repo_id_stable_across_remote_forms(self) -> None:
        ssh_id = make_repo_id("git@github.com:org/project.git", "/tmp/one")
        https_id = make_repo_id("https://github.com/org/project", "/tmp/two")

        self.assertEqual(ssh_id, https_id)

    def test_registry_aliases_prevent_duplicate_repo_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_id = make_repo_id("git@github.com:org/project.git", "/tmp/one")
            register_repo_identity(
                temp_dir,
                repo_id,
                git_remote="git@github.com:org/project.git",
                repo_root="/tmp/project",
                aliases=["https://github.com/org/project.git"],
            )

            self.assertEqual(
                resolve_repo_id_from_registry(temp_dir, git_remote="https://github.com/org/project.git"),
                repo_id,
            )
            self.assertEqual(resolve_repo_id_from_registry(temp_dir, repo_root="/tmp/project"), repo_id)
            registry = load_repo_registry(temp_dir)
            self.assertEqual(registry["by_canonical_remote"]["github.com/org/project"], repo_id)

    def test_repo_initialization_creates_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RepoContextManager(temp_dir)
            meta = RepoMeta(
                repo_id="repo_123",
                repo_name="Project",
                git_remote="https://github.com/org/project.git",
                repo_root="/repo/project",
                languages=["python"],
            )
            paths = manager.init_repo(meta)

            self.assertTrue(paths.repo_meta.exists())
            self.assertTrue(paths.file_index.exists())
            self.assertTrue(paths.summaries.exists())
            self.assertTrue(paths.logic_store.exists())
            self.assertTrue(paths.graph.exists())
            self.assertEqual(manager.load_repo_meta("repo_123")["repo_name"], "Project")

    def test_resolve_or_register_auto_initializes_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RepoContextManager(temp_dir)
            first = manager.resolve_or_register_repo(
                repo_root="/tmp/project",
                git_remote="git@github.com:org/project.git",
                branch_name="feature/login-ui",
            )
            second = manager.resolve_or_register_repo(
                repo_root="/tmp/other",
                git_remote="https://github.com/org/project",
                branch_name="feature/login-ui",
            )

            self.assertEqual(first["repo_id"], second["repo_id"])
            self.assertTrue(manager.paths(first["repo_id"]).repo_meta.exists())
            self.assertTrue(manager.paths(first["repo_id"]).branch_meta("feature/login-ui").exists())
            repo_dirs = list((Path(temp_dir) / "repos").iterdir())
            self.assertEqual(len(repo_dirs), 1)

    def test_path_fallback_lookup_resolves_existing_local_repo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RepoContextManager(temp_dir)
            first = manager.resolve_or_register_repo(repo_root="/tmp/local-only", branch_name="main")
            second = manager.resolve_or_register_repo(repo_root="/tmp/local-only", branch_name="main")

            self.assertEqual(first["repo_id"], second["repo_id"])
            self.assertEqual(first["identity_mode"], "path_fallback")

    def test_branch_initialization_creates_delta_files_with_safe_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RepoContextManager(temp_dir)
            manager.init_repo(RepoMeta(repo_id="repo_123", repo_name="Project"))
            manager.init_branch("repo_123", BranchMeta(repo_id="repo_123", branch_name="feature/login-ui"))
            paths = manager.paths("repo_123")
            branch_dir = paths.branch_dir("feature/login-ui")

            self.assertEqual(branch_dir.name, "feature__login-ui")
            self.assertTrue(paths.branch_meta("feature/login-ui").exists())
            self.assertTrue(paths.changed_files("feature/login-ui").exists())
            self.assertTrue(paths.summaries_delta("feature/login-ui").exists())
            self.assertTrue(paths.logic_delta("feature/login-ui").exists())
            self.assertTrue(paths.graph_delta("feature/login-ui").exists())

    def test_session_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RepoContextManager(temp_dir)
            manager.init_repo(RepoMeta(repo_id="repo_123", repo_name="Project"))
            session = SessionContext(
                session_id="session-1",
                repo_id="repo_123",
                branch_name="main",
                ide="vscode",
                workspace_root="/repo/project",
                open_files=["app.py"],
                selected_text="selected",
                current_task="Fix login bug",
            )

            manager.save_session(session)
            loaded = manager.load_session("repo_123", "session-1")

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["ide"], "vscode")
            self.assertEqual(loaded["open_files"], ["app.py"])

    def test_effective_context_merge_and_edge_removal(self) -> None:
        base = {
            "repo_meta": {"repo_id": "repo_123"},
            "summaries": [
                {"id": "s1", "summary": "base"},
            ],
            "logic_store": [
                {"id": "l1", "name": "Login"},
            ],
            "graph": {
                "nodes": [{"id": "LoginFlow", "type": "flow"}],
                "edges": [
                    {"from": "LoginFlow", "to": "AuthService", "type": "uses"},
                    {"from": "LoginFlow", "to": "OldService", "type": "uses"},
                ],
            },
        }
        branch = {
            "branch_meta": {"branch_name": "feature/login-ui"},
            "changed_files": {"added": ["ui.py"], "modified": [], "deleted": []},
            "summaries_delta": [
                {"id": "s1", "summary": "branch"},
                {"id": "s2", "summary": "new"},
            ],
            "logic_delta": [
                {"id": "l2", "name": "TokenGeneration"},
            ],
            "graph_delta": {
                "added_nodes": [{"id": "TokenGeneration", "type": "flow"}],
                "added_edges": [{"from": "LoginFlow", "to": "TokenGeneration", "type": "depends_on"}],
                "removed_edges": [{"from": "LoginFlow", "to": "OldService", "type": "uses"}],
            },
        }
        session = {"session_id": "session-1"}

        effective = merge_effective_context(base, branch, session)

        self.assertEqual(effective["effective_summaries"][0]["summary"], "branch")
        self.assertEqual(len(effective["effective_summaries"]), 2)
        self.assertEqual(len(effective["effective_logic_units"]), 2)
        self.assertIn({"id": "TokenGeneration", "type": "flow"}, effective["effective_graph"]["nodes"])
        self.assertIn(
            {"from": "LoginFlow", "to": "TokenGeneration", "type": "depends_on"},
            effective["effective_graph"]["edges"],
        )
        self.assertNotIn(
            {"from": "LoginFlow", "to": "OldService", "type": "uses"},
            effective["effective_graph"]["edges"],
        )
        self.assertEqual(effective["session"], session)
        self.assertEqual(effective["changed_files"]["added"], ["ui.py"])

    def test_retrieval_bias_prefers_current_file_and_changed_files(self) -> None:
        effective = {
            "file_index": [
                {"path": "backend/auth.py", "module": "backend", "language": "python"},
                {"path": "frontend/LoginScreen.tsx", "module": "frontend", "language": "typescript"},
            ],
            "changed_files": {"added": [], "modified": ["frontend/LoginScreen.tsx"], "deleted": []},
        }
        signals = collect_session_bias_signals(effective, "frontend/LoginScreen.tsx", ["backend/auth.py"])
        ranked = rank_logic_units_with_bias(
            [
                {"id": "LoginUI", "name": "Login UI", "files": ["frontend/LoginScreen.tsx"], "summary": "login screen"},
                {"id": "LoginBackend", "name": "Login Backend", "files": ["backend/auth.py"], "summary": "auth service"},
            ],
            signals,
            query="fix login ui",
        )

        self.assertEqual(ranked[0][0], "LoginUI")
        self.assertGreater(ranked[0][1], ranked[1][1])

    def test_manager_loads_base_and_branch_overlay_without_optional_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = RepoContextManager(temp_dir)
            manager.init_repo(RepoMeta(repo_id="repo_123", repo_name="Project"))
            paths = manager.paths("repo_123")
            write_json(paths.summaries, [{"id": "s1", "summary": "base"}])

            base = manager.load_base_context("repo_123")
            branch = manager.load_branch_overlay("repo_123", "missing")

            self.assertEqual(base["summaries"], [{"id": "s1", "summary": "base"}])
            self.assertEqual(branch["summaries_delta"], [])
            self.assertEqual(branch["changed_files"], {"added": [], "modified": [], "deleted": []})


if __name__ == "__main__":
    unittest.main()
