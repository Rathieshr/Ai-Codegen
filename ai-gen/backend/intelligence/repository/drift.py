from __future__ import annotations

from typing import Any

from .repository_snapshot import RepositorySnapshot


DRIFT_FIELDS = {
    "applications": "Applications",
    "modules": "Modules",
    "flows": "Flows",
    "architecture": "Architecture",
    "patterns": "Patterns",
    "dependencies": "Dependencies",
    "standards": "Standards",
}


def calculate_repository_drift(previous: RepositorySnapshot | None, current: RepositorySnapshot) -> dict[str, Any]:
    if previous is None:
        return {
            "status": "initial_snapshot",
            "fromVersion": None,
            "toVersion": current.scan_version,
            "added": {label: _names(getattr(current, key)) for key, label in DRIFT_FIELDS.items()},
            "removed": {label: [] for label in DRIFT_FIELDS.values()},
            "modified": {},
            "repositoryHealthScore": _health_score(current, 0),
        }
    added: dict[str, list[str]] = {}
    removed: dict[str, list[str]] = {}
    for key, label in DRIFT_FIELDS.items():
        before = set(_names(getattr(previous, key)))
        after = set(_names(getattr(current, key)))
        added[label] = sorted(after - before)
        removed[label] = sorted(before - after)
    changed_files = _changed_files(previous, current)
    change_count = sum(len(values) for values in [*added.values(), *removed.values()]) + len(changed_files)
    return {
        "status": "changed" if change_count else "unchanged",
        "fromVersion": previous.scan_version,
        "toVersion": current.scan_version,
        "added": added,
        "removed": removed,
        "modified": {"Files": changed_files},
        "repositoryHealthScore": _health_score(current, change_count),
    }


def _names(items: list[Any]) -> list[str]:
    return sorted({str(getattr(item, "name", "")).strip() for item in items if str(getattr(item, "name", "")).strip()})


def _changed_files(previous: RepositorySnapshot, current: RepositorySnapshot) -> list[str]:
    before = {file.path: file.hash for file in previous.files}
    after = {file.path: file.hash for file in current.files}
    return sorted(path for path, digest in after.items() if before.get(path) and before[path] != digest)


def _health_score(snapshot: RepositorySnapshot, change_count: int) -> int:
    coverage = 0
    for section in [snapshot.technologies, snapshot.applications, snapshot.modules, snapshot.flows, snapshot.architecture, snapshot.standards]:
        if section:
            coverage += 15
    coverage += 10 if snapshot.files else 0
    penalty = min(change_count * 2, 20)
    return max(0, min(100, coverage - penalty))
