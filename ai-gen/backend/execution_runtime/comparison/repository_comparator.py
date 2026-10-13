"""Metadata-only comparison of interpreted artifacts against a supplied baseline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.token_intelligence.models import stable_hash


class RepositoryComparator:
    def compare(self, session: dict[str, Any], artifacts: list[dict[str, Any]]) -> dict[str, Any]:
        context = session.get("runtimeContext") if isinstance(session.get("runtimeContext"), dict) else {}
        baseline = context.get("repositoryBaseline") if isinstance(context.get("repositoryBaseline"), list) else []
        known_paths = {_path(item) for item in baseline if _path(item)}
        added: list[str] = []
        modified: list[str] = []
        deleted: list[str] = []
        unchanged: list[str] = []
        for artifact in artifacts:
            path = str(artifact.get("path") or "")
            if not path:
                continue
            change = str(artifact.get("changeType") or "Proposed")
            if change == "Deleted":
                deleted.append(path)
            elif change == "Added" or path not in known_paths:
                added.append(path)
            elif change in {"Modified", "Proposed"}:
                modified.append(path)
            else:
                unchanged.append(path)
        core = {
            "sessionId": session["sessionId"],
            "snapshot": session["repositorySnapshotVersion"],
            "artifacts": [artifact["artifactId"] for artifact in artifacts],
            "added": added,
            "modified": modified,
            "deleted": deleted,
        }
        confidence = 0.92 if known_paths and all(artifact.get("path") for artifact in artifacts) else 0.7 if artifacts else 0.45
        return {
            "diffId": f"engineeringdiff_{stable_hash(core)[:12]}",
            "sessionId": session["sessionId"],
            "repositorySnapshotVersion": session["repositorySnapshotVersion"],
            "commitBefore": session["commitBefore"],
            "commitAfter": session["commitAfter"],
            "added": list(dict.fromkeys(added)),
            "modified": list(dict.fromkeys(modified)),
            "deleted": list(dict.fromkeys(deleted)),
            "unchanged": list(dict.fromkeys(unchanged)),
            "artifactIds": [artifact["artifactId"] for artifact in artifacts],
            "summary": {"added": len(set(added)), "modified": len(set(modified)), "deleted": len(set(deleted)), "unchanged": len(set(unchanged))},
            "confidence": confidence,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "comparisonMode": "caller_supplied_metadata",
            "repositoryRead": False,
            "gitUsed": False,
        }


def _path(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("path") or value.get("file") or "").strip()
    return ""
