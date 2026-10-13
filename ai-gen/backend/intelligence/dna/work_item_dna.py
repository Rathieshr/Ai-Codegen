from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


IMMUTABLE_FIELDS = {"businessGoals", "businessOutcome", "capability", "planningBoundary"}
MERGE_EXTEND_FIELDS = {"responsibilities", "dependencies", "constraints", "assumptions", "risks", "engineeringStandards", "acceptanceThemes"}
DNA_STORE: dict[str, list[dict[str, Any]]] = {}


@dataclass
class WorkItemDNA:
    dnaId: str
    workItemId: int | str | None
    workItemType: str
    version: int
    parentDNA: str | None = None
    businessProblem: list[str] = field(default_factory=list)
    businessGoals: list[str] = field(default_factory=list)
    businessOutcome: str = ""
    capability: str = ""
    responsibilities: list[str] = field(default_factory=list)
    planningBoundary: dict[str, list[str]] = field(default_factory=lambda: {"inScope": [], "outOfScope": []})
    repositoryEvidence: dict[str, list[str]] = field(default_factory=lambda: {"modules": [], "flows": [], "applications": [], "services": [], "files": []})
    dependencies: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    engineeringStandards: list[str] = field(default_factory=list)
    acceptanceThemes: list[str] = field(default_factory=list)
    validationSummary: dict[str, Any] = field(default_factory=lambda: {"score": 0, "issues": []})
    confidence: float = 0.0
    approved: bool = False
    approvedBy: str | None = None
    approvedAt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dnaId": self.dnaId,
            "workItemId": self.workItemId,
            "workItemType": self.workItemType,
            "version": self.version,
            "parentDNA": self.parentDNA,
            "businessProblem": list(self.businessProblem),
            "businessGoals": list(self.businessGoals),
            "businessOutcome": self.businessOutcome,
            "capability": self.capability,
            "responsibilities": list(self.responsibilities),
            "planningBoundary": {
                "inScope": list(self.planningBoundary.get("inScope", [])),
                "outOfScope": list(self.planningBoundary.get("outOfScope", [])),
            },
            "repositoryEvidence": {key: list(value) for key, value in self.repositoryEvidence.items()},
            "dependencies": list(self.dependencies),
            "constraints": list(self.constraints),
            "assumptions": list(self.assumptions),
            "risks": list(self.risks),
            "engineeringStandards": list(self.engineeringStandards),
            "acceptanceThemes": list(self.acceptanceThemes),
            "validationSummary": {
                "score": int(self.validationSummary.get("score") or 0),
                "issues": list(self.validationSummary.get("issues") or []),
            },
            "confidence": round(float(self.confidence), 3),
            "approved": bool(self.approved),
            "approvedBy": self.approvedBy,
            "approvedAt": self.approvedAt,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkItemDNA":
        return cls(
            dnaId=str(payload.get("dnaId") or payload.get("dna_id") or ""),
            workItemId=payload.get("workItemId") or payload.get("work_item_id"),
            workItemType=str(payload.get("workItemType") or payload.get("work_item_type") or ""),
            version=int(payload.get("version") or 1),
            parentDNA=payload.get("parentDNA") or payload.get("parent_dna"),
            businessProblem=_string_list(payload.get("businessProblem") or payload.get("business_problem")),
            businessGoals=_string_list(payload.get("businessGoals") or payload.get("business_goals")),
            businessOutcome=_clean_text(payload.get("businessOutcome") or payload.get("business_outcome")),
            capability=_clean_text(payload.get("capability")),
            responsibilities=_string_list(payload.get("responsibilities")),
            planningBoundary=_boundary(payload.get("planningBoundary") or payload.get("planning_boundary")),
            repositoryEvidence=_repository_evidence(payload.get("repositoryEvidence") or payload.get("repository_evidence")),
            dependencies=_string_list(payload.get("dependencies")),
            constraints=_string_list(payload.get("constraints")),
            assumptions=_string_list(payload.get("assumptions")),
            risks=_string_list(payload.get("risks")),
            engineeringStandards=_string_list(payload.get("engineeringStandards") or payload.get("engineering_standards")),
            acceptanceThemes=_string_list(payload.get("acceptanceThemes") or payload.get("acceptance_themes")),
            validationSummary=dict(payload.get("validationSummary") or payload.get("validation_summary") or {"score": 0, "issues": []}),
            confidence=float(payload.get("confidence") or 0),
            approved=bool(payload.get("approved")),
            approvedBy=payload.get("approvedBy") or payload.get("approved_by"),
            approvedAt=payload.get("approvedAt") or payload.get("approved_at"),
        )


def generateDNA(
    work_item: dict[str, Any],
    work_item_type: str,
    *,
    profile: dict[str, Any] | None = None,
    epic_analysis: dict[str, Any] | None = None,
    capability_review: dict[str, Any] | None = None,
    validation_report: dict[str, Any] | None = None,
    parent_dna: dict[str, Any] | None = None,
    approved: bool = False,
    approved_by: str | None = None,
) -> dict[str, Any]:
    profile = profile or {}
    epic_analysis = epic_analysis or {}
    capability_review = capability_review or {}
    parent = WorkItemDNA.from_dict(parent_dna) if parent_dna else None
    work_item_id = _item_id(work_item)
    capability = _clean_text(capability_review.get("capabilityName") or work_item.get("capability") or work_item.get("capability_category") or (parent.capability if parent else ""))
    dna = WorkItemDNA(
        dnaId=_dna_id(work_item_id, work_item_type, capability, parent.dnaId if parent else ""),
        workItemId=work_item_id,
        workItemType=work_item_type,
        version=1,
        parentDNA=parent.dnaId if parent else None,
        businessProblem=_inherit_or(epic_analysis.get("businessProblems"), parent.businessProblem if parent else [], work_item.get("user_problem")),
        businessGoals=_inherit_or(epic_analysis.get("businessGoals"), parent.businessGoals if parent else [], work_item.get("business_goal")),
        businessOutcome=_clean_text(work_item.get("business_outcome") or work_item.get("business_value") or (parent.businessOutcome if parent else "") or _first(epic_analysis.get("desiredOutcomes"))),
        capability=capability,
        responsibilities=_unique([*(parent.responsibilities if parent and work_item_type != "Feature" else []), *_string_list(capability_review.get("responsibilities")), *_string_list(work_item.get("responsibilities"))]),
        planningBoundary=_merge_boundary(parent.planningBoundary if parent else {}, capability_review.get("inScope"), capability_review.get("outOfScope"), epic_analysis.get("planningBoundary")),
        repositoryEvidence=_merge_repository_evidence(parent.repositoryEvidence if parent else {}, profile, work_item, capability_review),
        dependencies=_unique([*(parent.dependencies if parent else []), *_string_list(capability_review.get("dependencies")), *_string_list(work_item.get("dependencies"))]),
        constraints=_unique([*(parent.constraints if parent else []), *_string_list(work_item.get("constraints")), *_standards(profile, "security_requirements")]),
        assumptions=_unique([*(parent.assumptions if parent else []), *_string_list(work_item.get("assumptions"))]),
        risks=_unique([*(parent.risks if parent else []), *_string_list(work_item.get("risks"))]),
        engineeringStandards=_unique([*(parent.engineeringStandards if parent else []), *_all_standards(profile)]),
        acceptanceThemes=_unique([*(parent.acceptanceThemes if parent and work_item_type != "Feature" else []), *_acceptance_themes(work_item), *_string_list(capability_review.get("inScope"))]),
        validationSummary=_validation_summary(validation_report),
        confidence=round(float(work_item.get("confidence") or capability_review.get("confidence") or (parent.confidence if parent else 0.72)), 3),
        approved=approved,
        approvedBy=approved_by,
        approvedAt=_now_iso() if approved else None,
    )
    payload = dna.to_dict()
    _record_history(payload)
    return payload


def inheritDNA(parent_dna: dict[str, Any], child_updates: dict[str, Any], child_type: str) -> dict[str, Any]:
    parent = WorkItemDNA.from_dict(parent_dna).to_dict()
    merged = deepcopy(parent)
    merged["workItemType"] = child_type
    merged["workItemId"] = child_updates.get("workItemId") or child_updates.get("work_item_id") or child_updates.get("id") or parent.get("workItemId")
    merged["parentDNA"] = parent["dnaId"]
    merged["version"] = int(parent.get("version") or 1) + 1
    merged["dnaId"] = _dna_id(merged["workItemId"], child_type, parent.get("capability"), parent["dnaId"])
    for field in MERGE_EXTEND_FIELDS:
        merged[field] = _unique([*(_string_list(parent.get(field))), *_string_list(child_updates.get(field))])
    merged["repositoryEvidence"] = _merge_evidence_dict(parent.get("repositoryEvidence"), child_updates.get("repositoryEvidence"))
    merged["validationSummary"] = validateDNA(parent, merged)["summary"]
    _record_history(merged)
    return merged


def validateDNA(parent_dna: dict[str, Any] | None, child_dna: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    if parent_dna:
        parent = WorkItemDNA.from_dict(parent_dna).to_dict()
        child = WorkItemDNA.from_dict(child_dna).to_dict()
        if child.get("capability") and parent.get("capability") and child.get("capability") != parent.get("capability"):
            issues.append("Child DNA cannot change parent capability.")
        parent_scope = set(_string_list(parent.get("planningBoundary", {}).get("inScope")))
        child_scope = set(_string_list(child.get("planningBoundary", {}).get("inScope")))
        extra_scope = child_scope - parent_scope
        if parent_scope and extra_scope:
            issues.append(f"Child DNA cannot expand planning boundary: {', '.join(sorted(extra_scope))}.")
        parent_dependencies = set(_string_list(parent.get("dependencies")))
        child_dependencies = set(_string_list(child.get("dependencies")))
        missing = parent_dependencies - child_dependencies
        if missing:
            issues.append(f"Child DNA cannot remove required dependencies: {', '.join(sorted(missing))}.")
        parent_modules = set(_string_list(parent.get("repositoryEvidence", {}).get("modules")))
        child_modules = set(_string_list(child.get("repositoryEvidence", {}).get("modules")))
        unrelated = child_modules - parent_modules
        if parent_modules and unrelated:
            issues.append(f"Child DNA introduced unrelated modules: {', '.join(sorted(unrelated))}.")
    score = max(0, 100 - len(issues) * 25)
    return {
        "valid": not issues,
        "status": "Approved" if not issues else "Rejected",
        "issues": issues,
        "summary": {"score": score, "issues": issues},
    }


def mergeDNA(base_dna: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = WorkItemDNA.from_dict(base_dna).to_dict()
    for field, value in updates.items():
        if field in IMMUTABLE_FIELDS:
            continue
        if field in MERGE_EXTEND_FIELDS:
            merged[field] = _unique([*_string_list(merged.get(field)), *_string_list(value)])
        elif field == "repositoryEvidence":
            merged[field] = _merge_evidence_dict(merged.get(field), value)
        else:
            merged[field] = value
    merged["version"] = int(merged.get("version") or 1) + 1
    _record_history(merged)
    return merged


def compareDNA(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    left_clean = WorkItemDNA.from_dict(left).to_dict()
    right_clean = WorkItemDNA.from_dict(right).to_dict()
    for key in sorted(set(left_clean) | set(right_clean)):
        if left_clean.get(key) != right_clean.get(key):
            changes[key] = {"from": left_clean.get(key), "to": right_clean.get(key)}
    return {"changed": bool(changes), "changes": changes}


def getDNA(dna_id: str) -> dict[str, Any] | None:
    history = DNA_STORE.get(str(dna_id), [])
    return deepcopy(history[-1]) if history else None


def getDNAHistory(dna_id: str) -> list[dict[str, Any]]:
    return deepcopy(DNA_STORE.get(str(dna_id), []))


def dnaToGraph(dna: dict[str, Any]) -> dict[str, Any]:
    payload = WorkItemDNA.from_dict(dna).to_dict()
    dna_id = payload["dnaId"]
    work_node = f"{payload['workItemType']}:{payload['workItemId']}"
    nodes = [
        {"id": dna_id, "type": "WorkItemDNA", "name": f"{payload['workItemType']} DNA v{payload['version']}", "source": "planning", "metadata": payload, "confidence": payload["confidence"]},
        {"id": work_node, "type": payload["workItemType"], "name": str(payload["workItemId"] or payload["workItemType"]), "source": "planning"},
    ]
    edges = [{"from": dna_id, "to": work_node, "type": "generated_from", "source": "dna", "reason": "DNA identifies the source work item."}]
    if payload.get("parentDNA"):
        edges.append({"from": dna_id, "to": payload["parentDNA"], "type": "inherits", "source": "dna", "reason": "Child DNA inherits parent engineering identity."})
    for module in payload["repositoryEvidence"].get("modules", []):
        node_id = f"Module:{module}"
        nodes.append({"id": node_id, "type": "Module", "name": module, "source": "knowledge_registry"})
        edges.append({"from": dna_id, "to": node_id, "type": "uses", "source": "dna"})
    for flow in payload["repositoryEvidence"].get("flows", []):
        node_id = f"Flow:{flow}"
        nodes.append({"id": node_id, "type": "Flow", "name": flow, "source": "knowledge_registry"})
        edges.append({"from": dna_id, "to": node_id, "type": "uses", "source": "dna"})
    return {"nodes": nodes, "edges": edges}


def _record_history(dna: dict[str, Any]) -> None:
    DNA_STORE.setdefault(str(dna["dnaId"]), []).append(deepcopy(dna))


def _dna_id(work_item_id: Any, work_item_type: str, capability: Any, parent_dna: Any = "") -> str:
    raw = f"{work_item_type}|{work_item_id}|{capability}|{parent_dna}"
    return f"dna_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def _item_id(item: dict[str, Any]) -> int | str | None:
    return item.get("id") or item.get("workItemId") or item.get("work_item_id") or item.get("title")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _inherit_or(primary: Any, inherited: list[str], fallback: Any = None) -> list[str]:
    values = _string_list(primary)
    if values:
        return values
    return _unique([*inherited, *_string_list(fallback)])


def _first(value: Any) -> str:
    values = _string_list(value)
    return values[0] if values else ""


def _boundary(value: Any) -> dict[str, list[str]]:
    value = value if isinstance(value, dict) else {}
    return {
        "inScope": _string_list(value.get("inScope") or value.get("in_scope")),
        "outOfScope": _string_list(value.get("outOfScope") or value.get("out_of_scope")),
    }


def _merge_boundary(parent: dict[str, Any], in_scope: Any, out_of_scope: Any, epic_boundary: Any) -> dict[str, list[str]]:
    epic = _boundary(epic_boundary)
    parent = _boundary(parent)
    return {
        "inScope": _unique([*parent["inScope"], *epic["inScope"], *_string_list(in_scope)]),
        "outOfScope": _unique([*parent["outOfScope"], *epic["outOfScope"], *_string_list(out_of_scope)]),
    }


def _repository_evidence(value: Any) -> dict[str, list[str]]:
    value = value if isinstance(value, dict) else {}
    return {
        "modules": _string_list(value.get("modules")),
        "flows": _string_list(value.get("flows")),
        "applications": _string_list(value.get("applications")),
        "services": _string_list(value.get("services")),
        "files": _string_list(value.get("files")),
    }


def _merge_repository_evidence(parent: dict[str, Any], profile: dict[str, Any], work_item: dict[str, Any], review: dict[str, Any]) -> dict[str, list[str]]:
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    current = {
        "modules": _string_list(review.get("relatedModules") or work_item.get("impacted_modules") or work_item.get("affected_modules")),
        "flows": _string_list(review.get("relatedFlows") or work_item.get("impacted_flows") or work_item.get("affected_flows")),
        "applications": _string_list(review.get("relatedApplications") or work_item.get("impacted_applications") or work_item.get("affected_applications")),
        "services": _string_list(work_item.get("services")),
        "files": _string_list(work_item.get("files") or registry.get("source_files")),
    }
    return _merge_evidence_dict(parent, current)


def _merge_evidence_dict(left: Any, right: Any) -> dict[str, list[str]]:
    left = _repository_evidence(left)
    right = _repository_evidence(right)
    return {key: _unique([*left.get(key, []), *right.get(key, [])]) for key in ["modules", "flows", "applications", "services", "files"]}


def _validation_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    report = report if isinstance(report, dict) else {}
    issues = report.get("issues") if isinstance(report.get("issues"), list) else []
    score = int(report.get("score") or report.get("qualityScore") or report.get("validationScore") or max(0, 100 - len(issues) * 10))
    return {"score": score, "issues": [_clean_text(issue.get("message") or issue.get("reason") or issue) for issue in issues]}


def _acceptance_themes(work_item: dict[str, Any]) -> list[str]:
    criteria = _string_list(work_item.get("acceptance_criteria") or work_item.get("acceptanceCriteria"))
    themes = []
    for item in criteria:
        words = [word.strip(".,:;").title() for word in item.split() if len(word.strip(".,:;")) > 4]
        if words:
            themes.append(" ".join(words[:3]))
    return themes[:8]


def _standards(profile: dict[str, Any], key: str) -> list[str]:
    standards = profile.get("development_standards") if isinstance(profile.get("development_standards"), dict) else {}
    return _string_list(standards.get(key))


def _all_standards(profile: dict[str, Any]) -> list[str]:
    standards = profile.get("development_standards") if isinstance(profile.get("development_standards"), dict) else {}
    values: list[str] = []
    for item in standards.values():
        values.extend(_string_list(item))
    registry = profile.get("knowledge_registry") if isinstance(profile.get("knowledge_registry"), dict) else {}
    values.extend(_string_list(registry.get("standards")))
    return _unique(values)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_clean_text(item) for item in value if _clean_text(item)]
    if isinstance(value, tuple) or isinstance(value, set):
        return [_clean_text(item) for item in value if _clean_text(item)]
    text = _clean_text(value)
    if not text:
        return []
    if "\n" in text:
        return [_clean_text(item.strip("-* ")) for item in text.splitlines() if _clean_text(item.strip("-* "))]
    return [text]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean_text(value)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result
