"""Repo-aware context manager backed by local JSON files."""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from backend.repo_context.models import BranchMeta, RepoMeta, SessionContext
from backend.repo_context.storage import read_json, write_json


def normalize_git_remote(remote: str) -> str:
    """Normalize common SSH/HTTPS git remotes into a stable comparable string."""

    value = remote.strip()
    if not value:
        return ""
    if value.startswith("git@") and ":" in value:
        host, path = value[4:].split(":", 1)
        normalized = f"{host.lower()}/{path}"
    else:
        parsed = urlparse(value)
        if parsed.scheme and parsed.netloc:
            host = (parsed.hostname or parsed.netloc).lower()
            normalized = f"{host}{parsed.path}"
        else:
            normalized = value.lower()
    normalized = normalized.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized.lower()


def make_repo_id(git_remote: str | None, repo_root: str) -> str:
    """Create a short stable repo id from normalized remote or repo root."""

    source = normalize_git_remote(git_remote or "") or str(Path(repo_root).expanduser().resolve())
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:12]
    return f"repo_{digest}"


def load_repo_registry(storage_root: str | Path) -> dict[str, Any]:
    """Load repo identity registry."""

    registry = read_json(registry_path(storage_root), default=_empty_registry())
    defaults = _empty_registry()
    for key, value in defaults.items():
        registry.setdefault(key, value)
    return registry


def save_repo_registry(storage_root: str | Path, registry: dict[str, Any]) -> None:
    """Persist repo identity registry."""

    write_json(registry_path(storage_root), registry)


def registry_path(storage_root: str | Path) -> Path:
    return Path(storage_root) / "repo_registry.json"


def resolve_repo_id_from_registry(
    storage_root: str | Path,
    git_remote: str | None = None,
    repo_root: str | None = None,
    repo_id: str | None = None,
) -> str | None:
    """Resolve repo id using canonical remote, aliases, then path fallback."""

    if repo_id:
        return repo_id
    registry = load_repo_registry(storage_root)
    canonical = normalize_git_remote(git_remote or "")
    if canonical and canonical in registry["by_canonical_remote"]:
        return registry["by_canonical_remote"][canonical]
    if git_remote and git_remote in registry["by_alias"]:
        return registry["by_alias"][git_remote]
    if repo_root:
        fallback = str(Path(repo_root).expanduser().resolve())
        return registry["by_path_fallback"].get(fallback)
    return None


def register_repo_identity(
    storage_root: str | Path,
    repo_id: str,
    git_remote: str | None = None,
    repo_root: str | None = None,
    aliases: list[str] | None = None,
) -> None:
    """Register canonical remote, aliases, and path fallback for a repo."""

    registry = load_repo_registry(storage_root)
    canonical = normalize_git_remote(git_remote or "")
    if canonical:
        registry["by_canonical_remote"][canonical] = repo_id
    for alias in [git_remote or "", *(aliases or [])]:
        if alias:
            registry["by_alias"][alias] = repo_id
    if repo_root:
        registry["by_path_fallback"][str(Path(repo_root).expanduser().resolve())] = repo_id
    save_repo_registry(storage_root, registry)


def detect_git_remote(repo_root: str) -> str | None:
    """Best-effort git remote detection."""

    return _run_git(repo_root, ["config", "--get", "remote.origin.url"])


def detect_git_branch(repo_root: str) -> str | None:
    """Best-effort git branch detection."""

    return _run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"])


def _run_git(repo_root: str, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    if completed.returncode != 0 or not value or value == "HEAD":
        return None
    return value


def _empty_registry() -> dict[str, dict[str, str]]:
    return {"by_canonical_remote": {}, "by_alias": {}, "by_path_fallback": {}}


class RepoPaths:
    """Centralized filesystem paths for one repo context."""

    def __init__(self, storage_root: str | Path, repo_id: str) -> None:
        self.storage_root = Path(storage_root)
        self.repo_id = repo_id
        self.repo_dir = self.storage_root / "repos" / repo_id
        self.base_dir = self.repo_dir / "base"
        self.branches_dir = self.repo_dir / "branches"
        self.sessions_dir = self.repo_dir / "sessions"

    @property
    def repo_meta(self) -> Path:
        return self.repo_dir / "repo_meta.json"

    @property
    def modules(self) -> Path:
        return self.repo_dir / "modules.json"

    @property
    def constraints(self) -> Path:
        return self.repo_dir / "constraints.json"

    @property
    def file_index(self) -> Path:
        return self.base_dir / "file_index.json"

    @property
    def summaries(self) -> Path:
        return self.base_dir / "summaries.json"

    @property
    def logic_store(self) -> Path:
        return self.base_dir / "logic_store.json"

    @property
    def graph(self) -> Path:
        return self.base_dir / "graph.json"

    def branch_dir(self, branch_name: str) -> Path:
        return self.branches_dir / safe_branch_name(branch_name)

    def branch_meta(self, branch_name: str) -> Path:
        return self.branch_dir(branch_name) / "branch_meta.json"

    def changed_files(self, branch_name: str) -> Path:
        return self.branch_dir(branch_name) / "changed_files.json"

    def summaries_delta(self, branch_name: str) -> Path:
        return self.branch_dir(branch_name) / "summaries_delta.json"

    def logic_delta(self, branch_name: str) -> Path:
        return self.branch_dir(branch_name) / "logic_delta.json"

    def graph_delta(self, branch_name: str) -> Path:
        return self.branch_dir(branch_name) / "graph_delta.json"

    def session(self, session_id: str) -> Path:
        return self.sessions_dir / f"{safe_file_part(session_id)}.json"


class RepoContextManager:
    """Manage repo, branch, and session JSON context."""

    def __init__(self, storage_root: str | Path) -> None:
        self.storage_root = Path(storage_root)

    def paths(self, repo_id: str) -> RepoPaths:
        return RepoPaths(self.storage_root, repo_id)

    def resolve_or_register_repo(
        self,
        repo_id: str | None = None,
        repo_root: str | None = None,
        git_remote: str | None = None,
        repo_name: str | None = None,
        branch_name: str | None = None,
    ) -> dict[str, Any]:
        """Resolve repo id through registry, auto-initializing when absent."""

        detected_remote = git_remote or (detect_git_remote(repo_root) if repo_root else None)
        detected_branch = branch_name or (detect_git_branch(repo_root) if repo_root else None) or "default"
        resolved_repo_id = resolve_repo_id_from_registry(
            self.storage_root,
            git_remote=detected_remote,
            repo_root=repo_root,
            repo_id=repo_id,
        )
        created = False
        if not resolved_repo_id:
            resolved_repo_id = make_repo_id(detected_remote, repo_root or "")
            created = True

        identity_mode = "git_remote" if normalize_git_remote(detected_remote or "") else "path_fallback"
        canonical_remote = normalize_git_remote(detected_remote or "") or None
        register_repo_identity(
            self.storage_root,
            resolved_repo_id,
            git_remote=detected_remote,
            repo_root=repo_root,
            aliases=[detected_remote] if detected_remote else [],
        )
        paths = self.paths(resolved_repo_id)
        if not paths.repo_meta.exists():
            with self._init_guard(resolved_repo_id):
                if not paths.repo_meta.exists():
                    self.init_repo(
                        RepoMeta(
                            repo_id=resolved_repo_id,
                            repo_name=repo_name or (Path(repo_root).name if repo_root else resolved_repo_id),
                            git_remote=detected_remote,
                            repo_root=repo_root or "",
                            default_branch=detected_branch,
                            identity_mode=identity_mode,
                            canonical_remote=canonical_remote,
                            aliases=[detected_remote] if detected_remote else [],
                        )
                    )
        if detected_branch:
            branch_path = paths.branch_meta(detected_branch)
            if not branch_path.exists():
                self.init_branch(resolved_repo_id, BranchMeta(repo_id=resolved_repo_id, branch_name=detected_branch))

        return {
            "repo_id": resolved_repo_id,
            "branch_name": detected_branch,
            "identity_mode": identity_mode,
            "identity_source": canonical_remote or (str(Path(repo_root).expanduser().resolve()) if repo_root else ""),
            "created": created,
        }

    def init_repo(self, meta: RepoMeta) -> RepoPaths:
        paths = self.paths(meta.repo_id)
        write_json(paths.repo_meta, meta)
        write_json(paths.modules, [module for module in meta.modules])
        self._ensure_file(paths.constraints, [])
        self._ensure_file(paths.file_index, [])
        self._ensure_file(paths.summaries, [])
        self._ensure_file(paths.logic_store, [])
        self._ensure_file(paths.graph, {"nodes": [], "edges": []})
        paths.sessions_dir.mkdir(parents=True, exist_ok=True)
        paths.branches_dir.mkdir(parents=True, exist_ok=True)
        return paths

    def init_branch(self, repo_id: str, branch_meta: BranchMeta) -> None:
        paths = self.paths(repo_id)
        branch_dir = paths.branch_dir(branch_meta.branch_name)
        branch_dir.mkdir(parents=True, exist_ok=True)
        write_json(paths.branch_meta(branch_meta.branch_name), branch_meta)
        self._ensure_file(paths.changed_files(branch_meta.branch_name), {"added": [], "modified": [], "deleted": []})
        self._ensure_file(paths.summaries_delta(branch_meta.branch_name), [])
        self._ensure_file(paths.logic_delta(branch_meta.branch_name), [])
        self._ensure_file(
            paths.graph_delta(branch_meta.branch_name),
            {"added_nodes": [], "added_edges": [], "removed_edges": []},
        )

    def save_session(self, session: SessionContext) -> None:
        write_json(self.paths(session.repo_id).session(session.session_id), session)

    def load_session(self, repo_id: str, session_id: str) -> dict[str, Any] | None:
        return read_json(self.paths(repo_id).session(session_id), default=None)

    def load_repo_meta(self, repo_id: str) -> dict[str, Any] | None:
        return read_json(self.paths(repo_id).repo_meta, default=None)

    def load_base_context(self, repo_id: str) -> dict[str, Any]:
        paths = self.paths(repo_id)
        return {
            "repo_meta": self.load_repo_meta(repo_id),
            "file_index": read_json(paths.file_index, default=[]),
            "summaries": read_json(paths.summaries, default=[]),
            "logic_store": read_json(paths.logic_store, default=[]),
            "graph": read_json(paths.graph, default={"nodes": [], "edges": []}),
            "constraints": read_json(paths.constraints, default=[]),
        }

    def load_branch_overlay(self, repo_id: str, branch_name: str) -> dict[str, Any]:
        paths = self.paths(repo_id)
        return {
            "branch_meta": read_json(paths.branch_meta(branch_name), default=None),
            "changed_files": read_json(paths.changed_files(branch_name), default={"added": [], "modified": [], "deleted": []}),
            "summaries_delta": read_json(paths.summaries_delta(branch_name), default=[]),
            "logic_delta": read_json(paths.logic_delta(branch_name), default=[]),
            "graph_delta": read_json(
                paths.graph_delta(branch_name),
                default={"added_nodes": [], "added_edges": [], "removed_edges": []},
            ),
        }

    def _ensure_file(self, path: Path, default: Any) -> None:
        if not path.exists():
            write_json(path, default)

    def _init_guard(self, repo_id: str) -> "_InitGuard":
        return _InitGuard(self.storage_root / "repos" / repo_id / ".init.lock")


class _InitGuard:
    """Tiny lock-file guard for best-effort repo initialization."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.acquired = False

    def __enter__(self) -> "_InitGuard":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("x", encoding="utf-8") as handle:
                handle.write("locked\n")
            self.acquired = True
        except FileExistsError:
            self.acquired = False
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except OSError:
                pass


def merge_effective_context(base: dict[str, Any], branch: dict[str, Any], session: dict[str, Any] | None) -> dict[str, Any]:
    """Merge base context with branch deltas and optional live session context."""

    graph = base.get("graph") or {"nodes": [], "edges": []}
    graph_delta = branch.get("graph_delta") or {}
    return {
        "repo_meta": base.get("repo_meta"),
        "file_index": base.get("file_index", []),
        "effective_summaries": merge_records(base.get("summaries", []), branch.get("summaries_delta", [])),
        "effective_logic_units": merge_records(base.get("logic_store", []), branch.get("logic_delta", [])),
        "effective_graph": merge_graph(graph, graph_delta),
        "changed_files": branch.get("changed_files") or {"added": [], "modified": [], "deleted": []},
        "branch_meta": branch.get("branch_meta"),
        "session": session,
    }


def merge_records(base_records: list[Any], delta_records: list[Any]) -> list[Any]:
    """Merge id/path keyed records with delta values replacing base records."""

    output: list[Any] = []
    index: dict[str, int] = {}
    for record in base_records + delta_records:
        key = _record_key(record)
        if key in index:
            output[index[key]] = record
            continue
        index[key] = len(output)
        output.append(record)
    return output


def merge_graph(graph: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    """Apply graph node/edge additions and edge removals."""

    nodes = merge_records(graph.get("nodes", []), delta.get("added_nodes", []))
    edges = merge_records(graph.get("edges", []), delta.get("added_edges", []))
    removed = {_edge_key(edge) for edge in delta.get("removed_edges", [])}
    edges = [edge for edge in edges if _edge_key(edge) not in removed]
    return {"nodes": nodes, "edges": edges}


def safe_branch_name(branch_name: str) -> str:
    return safe_file_part(branch_name.replace("/", "__"))


def safe_file_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()) or "default"


def _record_key(record: Any) -> str:
    data = _as_dict(record)
    return str(data.get("id") or data.get("path") or data.get("name") or data)


def _edge_key(edge: Any) -> str:
    data = _as_dict(edge)
    return f"{data.get('from') or data.get('from_id')}->{data.get('to') or data.get('to_id')}:{data.get('type')}"


def _as_dict(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        if hasattr(value, "to_dict"):
            return value.to_dict()
        return asdict(value)
    if isinstance(value, dict):
        return value
    return {"value": value}
