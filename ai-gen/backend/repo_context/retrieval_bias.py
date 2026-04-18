"""Deterministic repo/session retrieval bias helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def collect_session_bias_signals(
    effective_context: dict[str, Any],
    current_file: str | None,
    open_files: list[str],
    related_flows: list[str] | None = None,
) -> dict[str, Any]:
    """Collect file, branch, and module hints for repo-aware ranking."""

    changed = effective_context.get("changed_files") or {}
    changed_files = [
        *changed.get("added", []),
        *changed.get("modified", []),
        *changed.get("deleted", []),
    ]
    file_index = effective_context.get("file_index") or []
    current_module = _module_for_file(current_file, file_index)
    current_flow = _flow_for_file(current_file, file_index)
    return {
        "current_file": _norm_path(current_file or ""),
        "open_files": [_norm_path(path) for path in open_files if path],
        "changed_files": [_norm_path(path) for path in changed_files if path],
        "current_module": current_module,
        "current_language": _language_for_file(current_file, file_index),
        "current_flow": current_flow,
        "open_file_flows": [
            flow for flow in (_flow_for_file(path, file_index) for path in open_files)
            if flow
        ],
        "related_flows": [flow.lower() for flow in (related_flows or []) if flow],
    }


def rank_logic_units_with_bias(
    logic_units: list[dict[str, Any]] | dict[str, dict[str, Any]],
    bias_signals: dict[str, Any],
    query: str = "",
) -> list[tuple[str, float]]:
    """Rank logic units by deterministic session/file relevance."""

    units = _values(logic_units)
    query_terms = _query_terms(query)
    scored: list[tuple[str, float]] = []
    for unit in units:
        score = _score_record(unit, bias_signals, query_terms)
        scored.append((str(unit.get("id") or unit.get("name") or unit), score))
    return sorted(scored, key=lambda item: (-item[1], item[0]))


def rank_summaries_with_bias(
    summaries: list[dict[str, Any]] | dict[str, dict[str, Any]],
    bias_signals: dict[str, Any],
    query: str = "",
) -> list[tuple[str, float]]:
    """Rank summaries by deterministic session/file relevance."""

    records = _values(summaries)
    query_terms = _query_terms(query)
    scored: list[tuple[str, float]] = []
    for summary in records:
        score = _score_record(summary, bias_signals, query_terms)
        scored.append((str(summary.get("id") or summary.get("path") or summary), score))
    return sorted(scored, key=lambda item: (-item[1], item[0]))


def _score_record(record: dict[str, Any], bias_signals: dict[str, Any], query_terms: set[str]) -> float:
    files = [_norm_path(path) for path in record.get("files", [])]
    if record.get("path"):
        files.append(_norm_path(record["path"]))
    modules = {str(record.get("module", "")).lower(), *(str(module).lower() for module in record.get("modules", []))}
    text = " ".join(
        str(record.get(key, ""))
        for key in ("id", "name", "summary", "path", "language")
    ).lower()
    score = 0.0
    current_file = bias_signals.get("current_file")
    open_files = set(bias_signals.get("open_files", []))
    changed_files = set(bias_signals.get("changed_files", []))
    if current_file and current_file in files:
        score += 5
    if open_files.intersection(files):
        score += 3
    if changed_files.intersection(files):
        score += 2
    current_module = str(bias_signals.get("current_module") or "").lower()
    if current_module and current_module in modules:
        score += 2
    current_language = str(bias_signals.get("current_language") or "").lower()
    if current_language and current_language == str(record.get("language", "")).lower():
        score += 1
    current_flow = str(bias_signals.get("current_flow") or "").lower()
    record_flow = str(record.get("flow") or record.get("domain") or "").lower()
    logic_id = str(record.get("id") or "").lower()
    if current_flow and (
        current_flow == record_flow
        or current_flow in logic_id
        or current_flow in text
    ):
        score += 4
    related_flows = set(str(flow).lower() for flow in bias_signals.get("related_flows", []))
    if related_flows and (
        record_flow in related_flows
        or any(flow in logic_id or flow in text for flow in related_flows)
    ):
        score += 1.5
    if query_terms and any(term in text for term in query_terms):
        score += 2
    return score


def _module_for_file(path: str | None, file_index: list[dict[str, Any]]) -> str:
    normalized = _norm_path(path or "")
    for record in file_index:
        if _norm_path(record.get("path", "")) == normalized:
            return str(record.get("module", ""))
    return Path(normalized).parts[0] if normalized and Path(normalized).parts else ""


def _language_for_file(path: str | None, file_index: list[dict[str, Any]]) -> str:
    normalized = _norm_path(path or "")
    for record in file_index:
        if _norm_path(record.get("path", "")) == normalized:
            return str(record.get("language", ""))
    suffix = Path(normalized).suffix.lower()
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".kt": "kotlin",
        ".java": "java",
        ".cs": "csharp",
    }.get(suffix, "")


def _flow_for_file(path: str | None, file_index: list[dict[str, Any]]) -> str:
    normalized = _norm_path(path or "")
    for record in file_index:
        if _norm_path(record.get("path", "")) == normalized:
            return str(record.get("flow", ""))
    return ""


def _query_terms(query: str) -> set[str]:
    return {part for part in query.lower().replace("-", " ").split() if len(part) >= 3}


def _values(records: list[dict[str, Any]] | dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(records, dict):
        return list(records.values())
    return list(records)


def _norm_path(path: str) -> str:
    return path.replace("\\", "/").strip()
