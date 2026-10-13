"""Deterministic bug hotspot scoring for repo-aware context."""

from __future__ import annotations

from typing import Any


def detect_bug_surface(query: str) -> str | None:
    """Infer the likely bug surface from simple query keywords."""

    normalized = query.lower()
    if any(keyword in normalized for keyword in ("ui", "screen", "page", "layout", "component", "widget", "form")):
        return "ui"
    if any(keyword in normalized for keyword in ("api", "endpoint", "controller")):
        return "controller/api"
    if any(keyword in normalized for keyword in ("service", "logic", "business")):
        return "service"
    if any(keyword in normalized for keyword in ("token", "session", "auth")):
        return "auth/session"
    return None


def score_bug_hotspots(
    query: str,
    detected_flow: str | None,
    related_flows: list[str],
    file_index: list[dict[str, Any]] | dict[str, dict[str, Any]],
    changed_files: dict[str, list[str]],
    current_file: str | None,
    open_files: list[str],
) -> list[dict[str, Any]]:
    """Rank likely bug files using flow, branch, editor, role, and query hints."""

    surface = detect_bug_surface(query)
    changed = set(_norm_path(path) for path in _flatten_changed(changed_files))
    open_set = set(_norm_path(path) for path in open_files if path)
    current = _norm_path(current_file or "")
    query_terms = _query_terms(query)
    primary_flow = (detected_flow or "").lower()
    related_set = {flow.lower() for flow in related_flows}

    hotspots: list[dict[str, Any]] = []
    for record in _values(file_index):
        path = _norm_path(str(record.get("path", "")))
        if not path:
            continue
        flow = str(record.get("flow", "")).lower()
        role = str(record.get("role", "")).lower()
        text = " ".join(
            [
                path,
                str(record.get("summary", "")),
                " ".join(str(symbol) for symbol in record.get("symbols", [])),
            ]
        ).lower()
        score = 0.0
        reasons: list[str] = []

        if current and path == current:
            score += 5
            reasons.append("matches current file")
        if path in open_set:
            score += 3
            reasons.append("open in editor")
        if path in changed:
            score += 4
            reasons.append("recently changed")
        if primary_flow and flow == primary_flow:
            score += 4
            reasons.append("belongs to detected flow")
        elif flow and flow in related_set:
            score += 2
            reasons.append("belongs to related flow")
        if surface and _role_matches_surface(role, surface):
            score += 2
            reasons.append(f"matches {surface} bug surface")
        if query_terms and any(term in text for term in query_terms):
            score += 2
            reasons.append("matches query keywords")

        if score <= 0:
            continue
        hotspots.append(
            {
                "file": path,
                "flow": flow or "unknown",
                "role": role or "unknown",
                "score": score,
                "reasons": reasons,
            }
        )

    return sorted(hotspots, key=lambda item: (-float(item["score"]), item["file"]))[:3]


def _role_matches_surface(role: str, surface: str) -> bool:
    if surface == "ui":
        return role in {"ui", "viewmodel"}
    if surface == "controller/api":
        return role in {"controller", "api"}
    if surface == "service":
        return role == "service"
    if surface == "auth/session":
        return role in {"service", "controller", "api", "data", "unknown"}
    return False


def _flatten_changed(changed_files: dict[str, list[str]]) -> list[str]:
    return [
        *changed_files.get("added", []),
        *changed_files.get("modified", []),
        *changed_files.get("deleted", []),
    ]


def _query_terms(query: str) -> set[str]:
    return {
        part
        for part in query.lower().replace("-", " ").replace("_", " ").split()
        if len(part) >= 3 and part not in {"fix", "bug", "the", "add"}
    }


def _values(records: list[dict[str, Any]] | dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(records, dict):
        return list(records.values())
    return records


def _norm_path(path: str) -> str:
    return path.replace("\\", "/").strip()
