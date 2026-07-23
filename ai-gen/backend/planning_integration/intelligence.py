"""Deterministic, evidence-first planning analysis and proposal construction."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Callable


PLANNING_MODES = {
    "NEW_INITIATIVE", "NEW_FEATURE", "EXTEND_FEATURE", "MODIFY_EXISTING",
    "BUG_OR_ENHANCEMENT", "AI_RECOMMENDED",
}
TYPE_ORDER = {"Epic": 0, "Feature": 1, "Story": 2, "Task": 3, "Bug": 4}


class IntelligentPlanningEngine:
    """Compares approved requirements with synchronized engineering evidence."""

    def __init__(
        self,
        *,
        work_item_provider: Callable[[str], list[dict[str, Any]]] | None = None,
        iteration_provider: Callable[[str], list[dict[str, Any]]] | None = None,
        memory_provider: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.work_item_provider = work_item_provider or (lambda _project_id: [])
        self.iteration_provider = iteration_provider or (lambda _project_id: [])
        self.memory_provider = memory_provider or (lambda _query: {"results": [], "count": 0})

    def build_context(self, summary: dict[str, Any], repository: dict[str, Any]) -> dict[str, Any]:
        project_id = _text(summary.get("projectId"))
        requirement_text = " ".join([
            _text(summary.get("title")), _text(summary.get("planningRequirement")),
            *_strings(summary.get("businessGoals")), *_strings(summary.get("functionalRequirements")),
            *_strings(summary.get("acceptanceCriteria")),
        ])
        work_items = [_normalize_work_item(item) for item in self.work_item_provider(project_id) if isinstance(item, dict)]
        work_items = [item for item in work_items if item["type"] in TYPE_ORDER]
        memories = self.memory_provider({
            "text": requirement_text, "projectId": project_id,
            "repository": [repository.get("repositoryId"), repository.get("repositoryName")],
            "limit": 12,
        }) or {}
        memory_results = [
            {
                "id": _text(item.get("id")), "title": _text(item.get("title")),
                "category": _text(item.get("category")), "artifactType": _text(item.get("artifactType")),
                "version": int(item.get("version") or 1), "updatedAt": _text(item.get("updatedAt")),
                "confidence": _percent(item.get("confidence")), "score": int(item.get("searchScore") or 0),
                "reasons": _strings(item.get("matchReasons")),
            }
            for item in list(memories.get("results") or []) if isinstance(item, dict)
        ]
        context_seed = {
            "requirementContextVersion": summary.get("contextVersion"),
            "analysisId": summary.get("analysisId"),
            "projectId": project_id,
            "repositorySnapshotVersion": repository.get("repositorySnapshotVersion"),
            "workItemRevisions": {item["id"]: item["revision"] for item in work_items},
            "memoryVersions": [{"id": item["id"], "version": item["version"], "updatedAt": item["updatedAt"]} for item in memory_results],
        }
        context_id = "planning-context-" + _digest(context_seed)
        return {
            "schemaVersion": "hei-planning-context-v1",
            "contextId": context_id,
            "contextVersion": _digest(context_seed),
            "requirement": {
                "id": _text(summary.get("requirementId")), "title": _text(summary.get("title")),
                "businessGoals": _strings(summary.get("businessGoals")),
                "functionalRequirements": _strings(summary.get("functionalRequirements")),
                "acceptanceCriteria": _strings(summary.get("acceptanceCriteria")),
                "dependencies": _strings(summary.get("dependencies")), "risks": _strings(summary.get("risks")),
            },
            "projectId": project_id,
            "repository": repository,
            "azureDevOps": {
                "source": "HEI Platform SDK synchronized cache", "workItems": work_items,
                "currentIterations": list(self.iteration_provider(project_id) or []),
                "counts": _counts(work_items), "workItemRevisions": context_seed["workItemRevisions"],
                "existingHierarchy": _hierarchy(work_items),
            },
            "engineeringMemory": {"matches": memory_results, "count": len(memory_results)},
            "generatedAt": _now(),
        }

    def analyze(self, context: dict[str, Any]) -> dict[str, Any]:
        requirement = context["requirement"]
        title = requirement["title"]
        work_items = context["azureDevOps"]["workItems"]
        matches = []
        for item in work_items:
            confidence = _similarity(title, item["title"])
            if confidence < 0.28:
                continue
            matches.append({
                "workItem": item, "confidence": round(confidence, 3),
                "reason": _match_reason(title, item["title"], confidence),
                "isPotentialDuplicate": confidence >= (0.66 if item["type"] in {"Epic", "Feature"} else 0.78),
            })
        matches.sort(key=lambda item: item["confidence"], reverse=True)
        repository = context.get("repository") or {}
        modules = _strings(repository.get("modules"))
        return {
            "schemaVersion": "hei-planning-analysis-v1",
            "contextId": context["contextId"],
            "existingWorkItems": work_items,
            "similarWork": matches[:20],
            "duplicates": [item for item in matches if item["isPotentialDuplicate"]],
            "repositoryMatch": {
                "repositoryId": repository.get("repositoryId"), "snapshotVersion": repository.get("repositorySnapshotVersion"),
                "mode": repository.get("mode"), "modules": modules,
                "confidence": 92 if repository.get("mode") == "CodeIndexed" else 45 if repository.get("mode") == "KnowledgeSnapshot" else 20,
                "reason": "Completed Repository Intelligence snapshot matches the approved repository selection." if repository.get("mode") == "CodeIndexed" else "Repository evidence is incomplete; recommendations carry reduced confidence.",
            },
            "memorySuggestions": context.get("engineeringMemory", {}).get("matches", []),
            "analyzedAt": _now(),
        }

    def recommend(self, context: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
        title = context["requirement"]["title"]
        lowered = title.casefold()
        matches = analysis.get("similarWork") or []
        best = matches[0] if matches else None
        best_type = (best or {}).get("workItem", {}).get("type")
        if any(term in lowered for term in ("bug", "fix", "defect", "error", "issue")):
            mode = "BUG_OR_ENHANCEMENT"
        elif best and best["confidence"] >= 0.78:
            mode = "MODIFY_EXISTING"
        elif best_type == "Feature":
            mode = "EXTEND_FEATURE"
        elif best_type == "Epic":
            mode = "NEW_FEATURE"
        elif not analysis.get("existingWorkItems"):
            mode = "NEW_INITIATIVE"
        else:
            mode = "AI_RECOMMENDED"
        confidence = min(98, max(35, int(analysis["repositoryMatch"]["confidence"] * 0.45 + (85 if best else 60) * 0.35 + (85 if analysis.get("memorySuggestions") else 60) * 0.2)))
        reasons = [
            f"Planning mode {mode.replace('_', ' ').title()} was selected from synchronized backlog similarity.",
            analysis["repositoryMatch"]["reason"],
        ]
        if best:
            reasons.append(f"Closest work item is {best['workItem']['type']} #{best['workItem']['id']} at {round(best['confidence'] * 100)}% similarity.")
        return {
            "schemaVersion": "hei-planning-recommendation-v1", "contextId": context["contextId"],
            "mode": mode if mode in PLANNING_MODES else "AI_RECOMMENDED", "confidence": confidence,
            "reason": reasons, "existingItems": [item["workItem"] for item in matches[:8]],
            "repositoryMatch": analysis["repositoryMatch"], "memorySuggestions": analysis.get("memorySuggestions", [])[:8],
            "recommendedStrategy": _strategy(mode), "requiresHumanApproval": True, "generatedAt": _now(),
        }

    def build_proposal(self, context: dict[str, Any], recommendation: dict[str, Any], hierarchy: dict[str, Any]) -> dict[str, Any]:
        candidates = _flatten_hierarchy(context["requirement"], hierarchy)
        existing = context["azureDevOps"]["workItems"]
        changes = []
        items = []
        for index, candidate in enumerate(candidates):
            match = _best_match(candidate, existing)
            action = _planning_action(candidate, match)
            external = match[0] if match else None
            alias = f"proposal-{index + 1}"
            change = {
                "changeId": f"change-{_digest([context['contextId'], index, candidate['type'], candidate['title']])}",
                "action": action, "artifactType": candidate["type"], "title": candidate["title"],
                "parentTitle": candidate.get("parentTitle", ""), "confidence": round((match[1] if match else recommendation["confidence"] / 100) * 100),
                "reason": _change_reason(action, external, match[1] if match else 0),
                "existingWorkItem": external, "fieldChanges": _field_changes(candidate, external),
                "selected": action in {"Create", "Modify", "Link", "Merge", "Split"},
            }
            changes.append(change)
            if action in {"Create", "Modify"}:
                items.append({
                    "alias": alias, "type": candidate["type"], "title": candidate["title"],
                    "description": candidate.get("description", ""), "acceptanceCriteria": candidate.get("acceptanceCriteria", []),
                    "parentAlias": candidate.get("parentAlias", ""),
                    "externalId": external["id"] if action == "Modify" and external else "",
                    "revision": external["revision"] if action == "Modify" and external else 0,
                })
        return {
            "schemaVersion": "hei-planning-proposal-v1", "proposalId": "planning-proposal-" + _digest([context["contextId"], changes]),
            "contextId": context["contextId"], "mode": recommendation["mode"], "confidence": recommendation["confidence"],
            "changes": changes, "items": items, "impact": _impact(changes),
            "sourceRevisions": context["azureDevOps"].get("workItemRevisions", {item["id"]: item["revision"] for item in existing}),
            "approval": {"status": "Pending", "approvedBy": "", "approvedAt": ""}, "generatedAt": _now(),
        }

    @staticmethod
    def build_diff(proposal: dict[str, Any]) -> dict[str, Any]:
        changes = list(proposal.get("changes") or [])
        return {
            "schemaVersion": "hei-planning-diff-v1", "diffId": "planning-diff-" + _digest([proposal.get("proposalId"), changes]),
            "proposalId": proposal.get("proposalId"), "status": proposal.get("approval", {}).get("status", "Pending"),
            "summary": {action: sum(1 for item in changes if item.get("action") == action) for action in ("Create", "Modify", "Keep", "Replace", "Merge", "Split", "Ignore", "Link")},
            "changes": changes, "sourceRevisions": proposal.get("sourceRevisions", {}),
            "approval": dict(proposal.get("approval") or {}), "generatedAt": _now(),
        }


def _normalize_work_item(item: dict[str, Any]) -> dict[str, Any]:
    kind = _normalize_type(item.get("workItemType") or item.get("type"))
    return {
        "id": _text(item.get("workItemId") or item.get("id")), "type": kind,
        "title": _text(item.get("title")) or f"{kind} {_text(item.get('workItemId') or item.get('id'))}",
        "description": _text(item.get("description")), "state": _text(item.get("state")) or "New",
        "revision": int(item.get("revision") or item.get("rev") or 0),
        "parentId": _text(item.get("parentId") or item.get("parentWorkItemId")),
        "storyPoints": item.get("storyPoints"), "areaPath": _text(item.get("areaPath")),
        "iterationPath": _text(item.get("iterationPath")), "tags": _strings(item.get("tags")),
        "assignedTo": _text(item.get("assignedTo") or item.get("assignedUser")),
        "completionState": _text(item.get("completionState") or item.get("completedState")),
        "changedAt": _text(item.get("changedAt") or item.get("updatedAt")),
    }


def _flatten_hierarchy(requirement: dict[str, Any], hierarchy: dict[str, Any]) -> list[dict[str, Any]]:
    root = hierarchy.get("epic") if isinstance(hierarchy.get("epic"), dict) else {}
    result = [{
        "type": "Epic", "title": _text(root.get("title")) or requirement["title"],
        "description": _text(root.get("description")) or " ".join(requirement.get("businessGoals") or []),
        "acceptanceCriteria": requirement.get("acceptanceCriteria") or [], "parentAlias": "", "parentTitle": "",
    }]
    aliases = {result[0]["title"]: "proposal-1"}
    if not hierarchy.get("features"):
        hierarchy = {**hierarchy, "features": [
            {"title": _title_from_sentence(value), "description": value, "epic": result[0]["title"]}
            for value in (requirement.get("functionalRequirements") or [])[:8]
        ]}
    if not hierarchy.get("stories") and hierarchy.get("features"):
        first_feature = hierarchy["features"][0]
        first_feature_title = _text(first_feature.get("title") if isinstance(first_feature, dict) else first_feature)
        hierarchy = {**hierarchy, "stories": [
            {"title": _title_from_sentence(value), "description": value, "acceptanceCriteria": [value], "feature": first_feature_title}
            for value in (requirement.get("acceptanceCriteria") or [])[:12]
        ]}
    for kind, key in (("Feature", "features"), ("Story", "stories"), ("Task", "tasks")):
        values = hierarchy.get(key) or []
        for value in values:
            item = value if isinstance(value, dict) else {"title": value}
            title = _text(item.get("title") or item.get("name"))
            if not title:
                continue
            parent_title = _text(item.get("parentTitle") or item.get("feature") or item.get("story") or item.get("epic"))
            result.append({
                "type": kind, "title": title, "description": _text(item.get("description")),
                "acceptanceCriteria": _strings(item.get("acceptanceCriteria")), "parentTitle": parent_title,
                "parentAlias": aliases.get(parent_title, "proposal-1" if kind == "Feature" else ""),
            })
            aliases[title] = f"proposal-{len(result)}"
    return result


def _best_match(candidate: dict[str, Any], existing: list[dict[str, Any]]) -> tuple[dict[str, Any], float] | None:
    matches = [(item, _similarity(candidate["title"], item["title"])) for item in existing if item["type"] == candidate["type"]]
    return max(matches, key=lambda item: item[1]) if matches else None


def _planning_action(candidate: dict[str, Any], match: tuple[dict[str, Any], float] | None) -> str:
    if not match:
        return "Create"
    item, score = match
    duplicate_threshold = 0.66 if candidate["type"] in {"Epic", "Feature"} else 0.80
    if score >= 0.94 and not _field_changes(candidate, item):
        return "Keep"
    if score >= duplicate_threshold:
        return "Modify" if _field_changes(candidate, item) else "Keep"
    return "Create"


def _field_changes(candidate: dict[str, Any], existing: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not existing:
        return []
    changes = []
    for field in ("title", "description"):
        proposed = _text(candidate.get(field)); current = _text(existing.get(field))
        if proposed and proposed != current:
            changes.append({"field": field, "before": current, "after": proposed})
    return changes


def _change_reason(action: str, existing: dict[str, Any] | None, score: float) -> str:
    if action == "Create": return "No sufficiently similar synchronized work item exists."
    if action == "Keep": return f"Existing {existing['type']} #{existing['id']} already satisfies this proposal."
    if action == "Modify": return f"Existing {existing['type']} #{existing['id']} matches at {round(score * 100)}%; only the displayed fields will change after approval."
    return "Planning Intelligence selected this action from current engineering evidence."


def _strategy(mode: str) -> dict[str, Any]:
    strategies = {
        "NEW_INITIATIVE": ("Create a new Epic and decompose it without duplicating existing Features.", ["Create", "Link"]),
        "NEW_FEATURE": ("Reuse the matching Epic and add only missing Features and Stories.", ["Keep", "Create", "Link"]),
        "EXTEND_FEATURE": ("Extend the matching Feature with missing Stories and Tasks.", ["Keep", "Modify", "Create"]),
        "MODIFY_EXISTING": ("Propose bounded field changes to existing work; preserve unaffected items.", ["Modify", "Keep"]),
        "BUG_OR_ENHANCEMENT": ("Prefer a bounded Bug or enhancement under the closest existing capability.", ["Create", "Link", "Keep"]),
        "AI_RECOMMENDED": ("Review the evidence-ranked proposal before selecting a planning boundary.", ["Create", "Modify", "Keep"]),
    }
    description, actions = strategies[mode]
    return {"description": description, "allowedActions": actions}


def _impact(changes: list[dict[str, Any]]) -> dict[str, Any]:
    writes = [item for item in changes if item.get("action") in {"Create", "Modify", "Replace", "Merge", "Split", "Link"}]
    return {
        "writeOperations": len(writes), "existingItemsAffected": sum(1 for item in writes if item.get("existingWorkItem")),
        "newItems": sum(1 for item in writes if item.get("action") == "Create"),
        "risk": "High" if len(writes) > 15 else "Medium" if len(writes) > 5 else "Low",
    }


def _counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {kind: sum(1 for item in items if item["type"] == kind) for kind in TYPE_ORDER}


def _hierarchy(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_parent: dict[str, list[str]] = {}
    for item in items:
        if item.get("parentId"):
            by_parent.setdefault(item["parentId"], []).append(item["id"])
    return [{**item, "childIds": by_parent.get(item["id"], [])} for item in sorted(items, key=lambda value: (TYPE_ORDER.get(value["type"], 99), value["title"].casefold()))]


def _title_from_sentence(value: Any) -> str:
    words = re.findall(r"[A-Za-z0-9]+", _text(value))
    while words and words[0].casefold() in {"the", "a", "an", "user", "users", "operator", "operators"}:
        words.pop(0)
    return " ".join(word if word.isupper() else word.capitalize() for word in words[:9]) or "Review Planning Requirement"


def _similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left); right_tokens = _tokens(right)
    if not left_tokens or not right_tokens: return 0.0
    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    sequence = SequenceMatcher(None, " ".join(sorted(left_tokens)), " ".join(sorted(right_tokens))).ratio()
    return round(overlap * 0.68 + sequence * 0.32, 4)


def _match_reason(left: str, right: str, confidence: float) -> str:
    overlap = sorted(_tokens(left) & _tokens(right))
    return f"Shared planning terms: {', '.join(overlap[:6])}." if overlap else f"Title structure similarity is {round(confidence * 100)}%."


def _tokens(value: Any) -> set[str]:
    ignored = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with", "implement", "modernize", "create", "add"}
    return {word for word in re.findall(r"[a-z0-9]+", _text(value).casefold()) if len(word) > 2 and word not in ignored}


def _normalize_type(value: Any) -> str:
    text = _text(value).casefold()
    if "epic" in text: return "Epic"
    if "feature" in text: return "Feature"
    if "story" in text or "product backlog" in text or text == "pbi": return "Story"
    if "task" in text: return "Task"
    if "bug" in text or "defect" in text: return "Bug"
    return _text(value).title()


def _strings(value: Any) -> list[str]:
    if isinstance(value, str): return [item.strip() for item in re.split(r"[;\n]", value) if item.strip()]
    if isinstance(value, list): return [_text(item.get("text") if isinstance(item, dict) else item) for item in value if _text(item.get("text") if isinstance(item, dict) else item)]
    return []


def _percent(value: Any) -> int:
    try:
        number = float(value or 0)
        return max(0, min(100, round(number * 100 if 0 < number <= 1 else number)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _digest(value: Any) -> str:
    import json
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
