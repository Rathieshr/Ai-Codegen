"""Lightweight deterministic repo indexing for ai-gen."""

from __future__ import annotations

import hashlib
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from backend.repo_context.manager import RepoContextManager
from backend.repo_context.logic_extractor import extract_and_update_logic
from backend.repo_context.storage import read_json, write_json


CODE_EXTENSIONS = {".kt", ".java", ".dart", ".ts", ".js", ".py", ".cs", ".go", ".swift", ".json", ".yaml", ".yml"}
IGNORED_DIRS = {".git", "node_modules", "build", "dist", "out", ".venv", "venv", "__pycache__", ".idea", ".gradle"}
MAX_FILE_SIZE = 200 * 1024
MAX_FILES = 2000
TIME_BUDGET_SECONDS = 2.0


def scan_repo_files(repo_root: str, max_files: int = MAX_FILES, time_budget_seconds: float = TIME_BUDGET_SECONDS) -> list[str]:
    """Recursively scan code files while skipping large/generated areas."""

    root = Path(repo_root)
    started = time.monotonic()
    files: list[str] = []
    if not root.exists():
        return files
    for path in root.rglob("*"):
        if time.monotonic() - started > time_budget_seconds or len(files) >= max_files:
            break
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in relative.parts):
            continue
        if path.suffix.lower() not in CODE_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > MAX_FILE_SIZE:
                continue
        except OSError:
            continue
        files.append(relative.as_posix())
    return files


def analyze_file(file_path: str, full_path: Path) -> dict[str, Any]:
    """Extract lightweight file metadata using regex heuristics."""

    content = _read_text(full_path)
    return {
        "path": file_path,
        "language": language_for_extension(full_path.suffix),
        "module": module_for_path(file_path),
        "symbols": extract_symbols(content),
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "logic_refs": infer_logic_refs(file_path, content),
        "summary_refs": [],
        "graph_nodes": infer_graph_nodes(file_path, content),
    }


def generate_file_summary(file_path: str, content: str) -> str:
    """Generate a concise heuristic file summary."""

    text = f"{file_path} {content}".lower()
    parts: list[str] = []
    if any(keyword in text for keyword in ("login", "auth", "authentication")):
        parts.append("Handles login/auth behavior")
    if "session" in text:
        parts.append("uses session flow")
    if "payment" in text:
        parts.append("handles payment flow")
    if "dashboard" in text:
        parts.append("handles dashboard UI")
    if "controller" in text or "api" in text:
        parts.append("exposes API/controller behavior")
    if "service" in text:
        parts.append("contains service logic")
    if not parts:
        parts.append(f"Contains {language_for_extension(Path(file_path).suffix) or 'code'} implementation")
    return "; ".join(parts[:2]) + "."


def bootstrap_repo_index(
    repo_id: str,
    repo_root: str,
    storage_root: str | Path = ".ai_gen_repo_context",
    max_files: int = MAX_FILES,
    time_budget_seconds: float = TIME_BUDGET_SECONDS,
) -> dict[str, Any]:
    """Build initial file index, summaries, and graph hints."""

    manager = RepoContextManager(storage_root)
    paths = manager.paths(repo_id)
    started = time.monotonic()
    file_records: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    graph = read_json(paths.graph, default={"nodes": [], "edges": []})
    partial = False
    for relative_path in scan_repo_files(repo_root, max_files=max_files, time_budget_seconds=time_budget_seconds):
        if time.monotonic() - started > time_budget_seconds:
            partial = True
            break
        full_path = Path(repo_root) / relative_path
        content = _read_text(full_path)
        record = analyze_file(relative_path, full_path)
        file_records.append(record)
        summaries.append(_summary_record(relative_path, content, record))
        _append_graph_hints(graph, record)

    write_json(paths.file_index, file_records)
    write_json(paths.summaries, summaries)
    logic_result = extract_and_update_logic(
        file_records,
        summaries,
        read_json(paths.logic_store, default=[]),
        graph,
    )
    write_json(paths.file_index, file_records)
    write_json(paths.summaries, summaries)
    write_json(paths.logic_store, logic_result["logic_store"])
    graph = logic_result["graph"]
    write_json(paths.graph, graph)
    return {
        "indexed_files": len(file_records),
        "partial": partial,
        "detected_flows": logic_result["detected_flows"],
    }


def get_changed_files(repo_root: str, branch_name: str) -> list[str]:
    """Return changed files via git diff, or [] if unavailable."""

    try:
        completed = subprocess.run(
            ["git", "diff", "--name-only", branch_name],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    return [
        path.strip()
        for path in completed.stdout.splitlines()
        if path.strip() and Path(path.strip()).suffix.lower() in CODE_EXTENSIONS
    ]


def update_changed_files(
    repo_id: str,
    branch_name: str,
    repo_root: str,
    storage_root: str | Path = ".ai_gen_repo_context",
) -> dict[str, Any]:
    """Incrementally update index and summaries for changed files."""

    manager = RepoContextManager(storage_root)
    paths = manager.paths(repo_id)
    changed = get_changed_files(repo_root, branch_name)
    if not changed:
        return {"changed_files": [], "updated_files": 0}

    file_index = read_json(paths.file_index, default=[])
    summaries = read_json(paths.summaries, default=[])
    graph = read_json(paths.graph, default={"nodes": [], "edges": []})
    file_by_path = {record.get("path"): record for record in file_index}
    summary_by_id = {record.get("id"): record for record in summaries}
    updated: list[str] = []

    for relative_path in changed:
        full_path = Path(repo_root) / relative_path
        if not _is_indexable(full_path, relative_path):
            continue
        content = _read_text(full_path)
        record = analyze_file(relative_path, full_path)
        file_by_path[relative_path] = record
        summary_by_id[relative_path] = _summary_record(relative_path, content, record)
        _append_graph_hints(graph, record)
        updated.append(relative_path)

    ordered_paths = [record.get("path") for record in file_index if record.get("path") in file_by_path]
    for path in updated:
        if path not in ordered_paths:
            ordered_paths.append(path)
    updated_file_index = [file_by_path[path] for path in ordered_paths]
    updated_summaries = list(summary_by_id.values())
    logic_result = extract_and_update_logic(
        updated_file_index,
        updated_summaries,
        read_json(paths.logic_store, default=[]),
        graph,
        affected_files=updated,
    )
    write_json(paths.file_index, updated_file_index)
    write_json(paths.summaries, updated_summaries)
    write_json(paths.logic_store, logic_result["logic_store"])
    graph = logic_result["graph"]
    write_json(paths.graph, graph)
    write_json(paths.changed_files(branch_name), {"added": [], "modified": updated, "deleted": []})
    return {
        "changed_files": updated,
        "updated_files": len(updated),
        "detected_flows": logic_result["detected_flows"],
    }


def language_for_extension(extension: str) -> str:
    return {
        ".kt": "kotlin",
        ".java": "java",
        ".dart": "dart",
        ".ts": "typescript",
        ".js": "javascript",
        ".py": "python",
        ".cs": "csharp",
        ".go": "go",
        ".swift": "swift",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
    }.get(extension.lower(), "")


def module_for_path(file_path: str) -> str:
    parts = Path(file_path).parts
    return parts[0] if len(parts) > 1 else ""


def extract_symbols(content: str) -> list[str]:
    symbols: list[str] = []
    patterns = [
        r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\bfun\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, content):
            if match not in symbols:
                symbols.append(match)
    return symbols


def infer_logic_refs(file_path: str, content: str) -> list[str]:
    text = f"{file_path} {content}".lower()
    refs: list[str] = []
    if "login" in text:
        refs.append("logic_auth_login")
    if "payment" in text:
        refs.append("logic_payment")
    if "session" in text:
        refs.append("logic_session")
    return refs


def infer_graph_nodes(file_path: str, content: str) -> list[dict[str, str]]:
    text = f"{file_path} {content}"
    nodes: list[dict[str, str]] = []
    if "Login" in text:
        nodes.append({"id": "LoginFlow", "type": "flow"})
    if "Auth" in text:
        nodes.append({"id": "AuthService", "type": "service"})
    if "Controller" in text:
        nodes.append({"id": Path(file_path).stem, "type": "controller"})
    if "ViewModel" in text:
        nodes.append({"id": Path(file_path).stem, "type": "viewmodel"})
    return nodes


def _summary_record(file_path: str, content: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": file_path,
        "path": file_path,
        "summary": generate_file_summary(file_path, content),
        "symbols": record.get("symbols", []),
        "logic_refs": record.get("logic_refs", []),
    }


def _append_graph_hints(graph: dict[str, Any], record: dict[str, Any]) -> None:
    nodes = graph.setdefault("nodes", [])
    for node in record.get("graph_nodes", []):
        if node not in nodes:
            nodes.append(node)


def _is_indexable(full_path: Path, relative_path: str) -> bool:
    if any(part in IGNORED_DIRS for part in Path(relative_path).parts):
        return False
    if full_path.suffix.lower() not in CODE_EXTENSIONS:
        return False
    try:
        return full_path.exists() and full_path.stat().st_size <= MAX_FILE_SIZE
    except OSError:
        return False


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
