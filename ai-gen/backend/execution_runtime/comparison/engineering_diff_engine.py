"""Semantic Engineering Diff Engine. This module performs no Git operations."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.token_intelligence.models import stable_hash

from .semantic_snapshot import CATEGORIES, project_execution_result, project_snapshot


class EngineeringDiffEngine:
    def compare(self, before: dict[str, Any], after: dict[str, Any], execution_result: dict[str, Any]) -> dict[str, Any]:
        _validate_inputs(before, after, execution_result)
        before_projection = project_snapshot(before, "RepositorySnapshotBefore")
        after_projection = project_snapshot(after, "RepositorySnapshotAfter")
        execution_projection = project_execution_result(execution_result)

        deltas = {category: _delta(before_projection[category], after_projection[category]) for category in CATEGORIES}
        _apply_renames(deltas, after_projection.get("renamed") or [])
        _merge_execution_claims(deltas, execution_projection)
        refactorings = _claim_delta(execution_projection.get("refactorings") or [])
        breaking_changes = _claim_delta(execution_projection.get("breakingChanges") or [])
        graph_changes = _graph_delta(before_projection["graph"], after_projection["graph"])
        impact = _impact(deltas, graph_changes, refactorings, breaking_changes)
        warnings = _warnings(before, after, execution_result)
        confidence = _overall_confidence(deltas, before, after, execution_result, warnings)
        core = {
            "before": _snapshot_id(before),
            "after": _snapshot_id(after),
            "result": execution_result.get("resultId") or execution_result.get("interpretationId"),
            "changes": deltas,
            "graph": graph_changes,
        }
        return {
            "diffId": f"engineering_diff_{stable_hash(core)[:12]}",
            "diffVersion": "5.3",
            "status": "Completed",
            "repositorySnapshotBefore": _lineage(before),
            "repositorySnapshotAfter": _lineage(after),
            "executionResultId": str(execution_result.get("resultId") or execution_result.get("interpretationId") or ""),
            "sessionId": str(execution_result.get("sessionId") or ""),
            "newAPIs": deepcopy(deltas["apis"]["added"]),
            "modifiedAPIs": deepcopy(deltas["apis"]["modified"]),
            "removedAPIs": deepcopy(deltas["apis"]["removed"]),
            "apiChanges": deepcopy(deltas["apis"]),
            "moduleChanges": deepcopy(deltas["modules"]),
            "serviceChanges": deepcopy(deltas["services"]),
            "dependencyChanges": deepcopy(deltas["dependencies"]),
            "architectureChanges": deepcopy(deltas["architecture"]),
            "testChanges": deepcopy(deltas["tests"]),
            "securityChanges": deepcopy(deltas["security"]),
            "configurationChanges": deepcopy(deltas["configuration"]),
            "databaseChanges": deepcopy(deltas["database"]),
            "documentationChanges": deepcopy(deltas["documentation"]),
            "refactoringChanges": refactorings,
            "breakingChanges": breaking_changes,
            "dependencyGraphChanges": graph_changes,
            "impact": impact,
            "warnings": warnings,
            "confidence": confidence,
            "summary": _summary(deltas, graph_changes, refactorings, breaking_changes),
            "diagnostics": {
                "comparisonMode": "semantic",
                "gitDiffUsed": False,
                "repositoryRead": False,
                "repositoryWrites": 0,
                "executionEvidenceUsed": sum(len(value) for value in execution_projection.values()),
                "beforeFactCount": sum(len(before_projection[key]) for key in CATEGORIES),
                "afterFactCount": sum(len(after_projection[key]) for key in CATEGORIES),
                "graphNodeChanges": len(graph_changes["nodesAdded"]) + len(graph_changes["nodesRemoved"]) + len(graph_changes["nodesModified"]),
                "graphEdgeChanges": len(graph_changes["edgesAdded"]) + len(graph_changes["edgesRemoved"]) + len(graph_changes["edgesModified"]),
            },
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }


def _delta(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    left = {item["key"]: item for item in before}
    right = {item["key"]: item for item in after}
    added = [_change("Added", None, right[key]) for key in sorted(right.keys() - left.keys())]
    removed = [_change("Removed", left[key], None) for key in sorted(left.keys() - right.keys())]
    modified: list[dict[str, Any]] = []
    moved: list[dict[str, Any]] = []
    for key in sorted(left.keys() & right.keys()):
        if left[key]["path"] != right[key]["path"] and left[key]["path"] and right[key]["path"]:
            moved.append(_change("Moved", left[key], right[key]))
        elif left[key]["signature"] != right[key]["signature"]:
            modified.append(_change("Modified", left[key], right[key]))
    return {"added": added, "modified": modified, "removed": removed, "moved": moved}


def _change(change_type: str, before: dict[str, Any] | None, after: dict[str, Any] | None, *, reason: str = "") -> dict[str, Any]:
    active = after or before or {}
    evidence = list(dict.fromkeys([*(before or {}).get("evidence", []), *(after or {}).get("evidence", [])]))
    confidence_values = [float(value.get("confidence") or 0) for value in (before, after) if value]
    return {
        "changeType": change_type,
        "name": active.get("name") or "",
        "kind": active.get("kind") or "Unknown",
        "before": _public(before),
        "after": _public(after),
        "source": " + ".join(value for value in ((before or {}).get("source"), (after or {}).get("source")) if value),
        "evidence": evidence,
        "reason": reason or f"Semantic identity was {change_type.casefold()} between repository snapshots.",
        "confidence": round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.5,
    }


def _claim_delta(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result = {"added": [], "modified": [], "removed": [], "moved": []}
    for record in records:
        change_type = record.get("changeType") or "Modified"
        bucket = {"Added": "added", "Removed": "removed", "Moved": "moved"}.get(change_type, "modified")
        result[bucket].append(_change(change_type, None if change_type == "Added" else record, record if change_type != "Removed" else None, reason="Explicitly reported by the structured Execution Result."))
    return result


def _merge_execution_claims(deltas: dict[str, dict[str, list[dict[str, Any]]]], claims: dict[str, list[dict[str, Any]]]) -> None:
    for category in CATEGORIES:
        for record in claims.get(category) or []:
            change_type = record.get("changeType") or "Modified"
            bucket = {"Added": "added", "Removed": "removed", "Moved": "moved"}.get(change_type, "modified")
            existing = {item["name"].casefold() for item in deltas[category][bucket]}
            if record["name"].casefold() not in existing:
                deltas[category][bucket].append(_change(change_type, None if change_type == "Added" else record, record if change_type != "Removed" else None, reason="Explicitly reported by the structured Execution Result and not duplicated from snapshot comparison."))


def _apply_renames(deltas: dict[str, dict[str, list[dict[str, Any]]]], renamed: list[Any]) -> None:
    for value in renamed:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            old_path, new_path = str(value[0]), str(value[1])
        elif isinstance(value, dict):
            old_path, new_path = str(value.get("oldPath") or value.get("from") or ""), str(value.get("newPath") or value.get("to") or "")
        else:
            continue
        if not old_path or not new_path:
            continue
        name = new_path.rsplit("/", 1)[-1]
        record = {"key": name.casefold(), "name": name, "path": old_path, "kind": "ModuleMember", "signature": "", "source": "RepositorySnapshotBefore", "evidence": [f"Repository snapshot rename: {old_path} -> {new_path}."], "confidence": 0.94}
        updated = {**record, "path": new_path, "source": "RepositorySnapshotAfter"}
        deltas["modules"]["moved"].append(_change("Moved", record, updated, reason="Repository snapshot metadata reports a move between module paths."))


def _graph_delta(before: dict[str, list[dict[str, Any]]], after: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    node_delta = _delta(before.get("nodes") or [], after.get("nodes") or [])
    edge_delta = _edge_delta(before.get("edges") or [], after.get("edges") or [])
    return {
        "nodesAdded": node_delta["added"],
        "nodesRemoved": node_delta["removed"],
        "nodesModified": node_delta["modified"],
        "edgesAdded": edge_delta["added"],
        "edgesRemoved": edge_delta["removed"],
        "edgesModified": edge_delta["modified"],
    }


def _edge_delta(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    left = {item["key"]: item for item in before}
    right = {item["key"]: item for item in after}
    return {
        "added": [_edge_change("Added", None, right[key]) for key in sorted(right.keys() - left.keys())],
        "removed": [_edge_change("Removed", left[key], None) for key in sorted(left.keys() - right.keys())],
        "modified": [_edge_change("Modified", left[key], right[key]) for key in sorted(left.keys() & right.keys()) if left[key].get("raw") != right[key].get("raw")],
    }


def _edge_change(change_type: str, before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:
    active = after or before or {}
    return {"changeType": change_type, "from": active.get("from"), "to": active.get("to"), "type": active.get("type"), "before": deepcopy((before or {}).get("raw")), "after": deepcopy((after or {}).get("raw")), "source": "Repository Snapshot Graph", "evidence": list(dict.fromkeys([*(before or {}).get("evidence", []), *(after or {}).get("evidence", [])])), "confidence": round(sum(float(value.get("confidence") or 0) for value in (before, after) if value) / max(1, len([value for value in (before, after) if value])), 2)}


def _impact(deltas: dict[str, dict[str, list[dict[str, Any]]]], graph: dict[str, list[dict[str, Any]]], refactorings: dict[str, list[dict[str, Any]]], breaking: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    points = 0
    reasons: list[str] = []
    weights = {"apis": (20, 30, 45), "modules": (12, 18, 25), "services": (15, 22, 30), "dependencies": (20, 25, 35), "architecture": (20, 30, 35), "tests": (8, 12, 20), "security": (30, 45, 60), "configuration": (12, 18, 25), "database": (25, 35, 50), "documentation": (3, 5, 8)}
    for category, (added_weight, modified_weight, removed_weight) in weights.items():
        delta = deltas[category]
        category_points = min(60, len(delta["added"]) * added_weight + len(delta["modified"]) * modified_weight + len(delta["removed"]) * removed_weight + len(delta["moved"]) * modified_weight)
        if category_points:
            points += category_points
            reasons.append(f"{category_points} points from {category} changes.")
    graph_count = sum(len(value) for value in graph.values())
    if graph_count:
        graph_points = min(30, graph_count * 8)
        points += graph_points
        reasons.append(f"{graph_points} points from dependency graph changes.")
    refactor_count = sum(len(value) for value in refactorings.values())
    if refactor_count:
        points += min(25, refactor_count * 15)
        reasons.append("Refactoring was explicitly reported by the Execution Result.")
    breaking_count = sum(len(value) for value in breaking.values())
    if breaking_count:
        points += 70
        reasons.append("Breaking changes were explicitly reported.")
    score = min(100, points)
    level = "Critical" if score >= 70 else "High" if score >= 40 else "Medium" if score >= 15 else "Low"
    return {"level": level, "score": score, "reasons": reasons or ["No semantic engineering changes were detected."]}


def _summary(deltas: dict[str, dict[str, list[dict[str, Any]]]], graph: dict[str, list[dict[str, Any]]], refactorings: dict[str, list[dict[str, Any]]], breaking: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    category_counts = {category: sum(len(value) for value in delta.values()) for category, delta in deltas.items()}
    return {"totalChanges": sum(category_counts.values()) + sum(len(value) for value in graph.values()) + sum(len(value) for value in refactorings.values()) + sum(len(value) for value in breaking.values()), "categoryCounts": category_counts, "graphChanges": sum(len(value) for value in graph.values()), "refactorings": sum(len(value) for value in refactorings.values()), "breakingChanges": sum(len(value) for value in breaking.values())}


def _warnings(before: dict[str, Any], after: dict[str, Any], result: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if not _snapshot_id(before):
        warnings.append("Before snapshot identity is missing.")
    if not _snapshot_id(after):
        warnings.append("After snapshot identity is missing.")
    if not (result.get("engineeringArtifacts") or result.get("artifacts") or result.get("structuredExecutionResult") or result.get("structuredResponse")):
        warnings.append("Execution Result contains no semantic artifact evidence.")
    return warnings


def _overall_confidence(deltas: dict[str, dict[str, list[dict[str, Any]]]], before: dict[str, Any], after: dict[str, Any], result: dict[str, Any], warnings: list[str]) -> float:
    values = [item["confidence"] for delta in deltas.values() for bucket in delta.values() for item in bucket]
    base = sum(values) / len(values) if values else 0.72
    if not _snapshot_id(before) or not _snapshot_id(after):
        base -= 0.15
    if not result:
        base -= 0.1
    return round(max(0.1, min(0.98, base - len(warnings) * 0.04)), 2)


def _public(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not value:
        return None
    return {key: deepcopy(value.get(key)) for key in ("name", "path", "kind", "signature", "module", "source", "evidence", "confidence")}


def _lineage(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {"snapshotId": _snapshot_id(snapshot), "version": snapshot.get("version"), "repositoryId": snapshot.get("repositoryId"), "branch": snapshot.get("branch"), "commitId": snapshot.get("commitId")}


def _snapshot_id(snapshot: dict[str, Any]) -> str:
    return str(snapshot.get("snapshotId") or snapshot.get("id") or "")


def _validate_inputs(before: Any, after: Any, execution_result: Any) -> None:
    if not isinstance(before, dict):
        raise ValueError("repositorySnapshotBefore is required.")
    if not isinstance(after, dict):
        raise ValueError("repositorySnapshotAfter is required.")
    if not isinstance(execution_result, dict):
        raise ValueError("executionResult is required.")
