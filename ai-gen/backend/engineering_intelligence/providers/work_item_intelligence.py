"""Stable adapter over the existing Azure DevOps Work Item Intelligence service."""

from __future__ import annotations

from typing import Any


class WorkItemIntelligenceProvider:
    """Exposes item-level intelligence without duplicating its reasoning rules."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def get_work_item(self, work_item_id: str, project_id: str = "") -> dict[str, Any]:
        cached = self._service.ado_sdk.find_cached(
            "workItems", str(work_item_id), str(project_id or ""),
        )
        if not cached:
            return {}
        resolved_project, item = cached
        return _normalize_work_item(dict(item), resolved_project)

    def analyze_work_item(
        self,
        work_item_id: str,
        *,
        project_id: str = "",
        repository_id: str = "",
        correlation_id: str = "",
        token_budget: int = 1200,
    ) -> dict[str, Any]:
        return dict(self._service.analyze(
            str(work_item_id),
            {
                "projectId": project_id,
                "repositoryId": repository_id,
                "tokenBudget": token_budget,
            },
            correlation_id=correlation_id,
        ))

    def refine_work_item(self, work_item_id: str, **options: Any) -> dict[str, Any]:
        return self.analyze_work_item(work_item_id, **options)

    def find_related_items(self, work_item_id: str, project_id: str = "") -> list[dict[str, Any]]:
        current = self.get_work_item(work_item_id, project_id)
        if not current:
            return []
        ids = {
            str(item.get("id") or item.get("workItemId") or "")
            for key in ("parents", "children", "relations", "linkedWorkItems")
            for item in current.get(key) or []
            if isinstance(item, dict)
        }
        return [
            item for item in (
                self.get_work_item(item_id, current.get("projectId") or project_id)
                for item_id in ids
            ) if item
        ]

    def find_similar_items(self, work_item_id: str) -> list[dict[str, Any]]:
        analysis = self._service.repository.latest_analysis(str(work_item_id)) or {}
        return list(analysis.get("duplicateOrSimilarWork") or [])

    def get_hierarchy_context(self, work_item_id: str, project_id: str = "") -> dict[str, Any]:
        item = self.get_work_item(work_item_id, project_id)
        return {
            "workItemId": str(work_item_id),
            "parents": list(item.get("parents") or []),
            "children": list(item.get("children") or []),
            "relatedItems": self.find_related_items(work_item_id, project_id),
        }

    def analyze_acceptance_criteria(self, work_item_id: str) -> dict[str, Any]:
        analysis = self._service.repository.latest_analysis(str(work_item_id)) or {}
        return dict(analysis.get("acceptanceCriteriaQuality") or {})

    def build_work_item_context(
        self,
        work_item_id: str,
        project_id: str = "",
        *,
        analyze: bool = False,
        repository_id: str = "",
        correlation_id: str = "",
    ) -> dict[str, Any]:
        item = self.get_work_item(work_item_id, project_id)
        if not item:
            return {"available": False, "workItemId": str(work_item_id)}
        analysis = (
            self.analyze_work_item(
                work_item_id,
                project_id=item.get("projectId") or project_id,
                repository_id=repository_id,
                correlation_id=correlation_id,
            )
            if analyze
            else self._service.repository.latest_analysis(str(work_item_id)) or {}
        )
        return {
            "available": True,
            "workItem": item,
            "analysis": analysis,
            "hierarchy": self.get_hierarchy_context(work_item_id, item.get("projectId") or project_id),
            "similarItems": list(analysis.get("duplicateOrSimilarWork") or []),
            "acceptanceCriteria": list(item.get("acceptanceCriteria") or []),
            "acceptanceCriteriaAnalysis": dict(analysis.get("acceptanceCriteriaQuality") or {}),
            "repositoryImpact": dict(analysis.get("context") or {}),
            "recommendations": list(analysis.get("recommendations") or []),
            "source": "ADO Work Item Intelligence",
        }


def _normalize_work_item(item: dict[str, Any], project_id: str) -> dict[str, Any]:
    return {
        **item,
        "id": str(item.get("workItemId") or item.get("id") or ""),
        "workItemId": str(item.get("workItemId") or item.get("id") or ""),
        "workItemType": str(item.get("workItemType") or item.get("type") or "Work Item"),
        "title": str(item.get("title") or ""),
        "description": str(item.get("description") or ""),
        "acceptanceCriteria": _criteria(item.get("acceptanceCriteria")),
        "revision": int(item.get("revision") or item.get("rev") or 0),
        "projectId": str(item.get("projectId") or project_id or ""),
    }


def _criteria(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [line.strip(" -\t") for line in text.splitlines() if line.strip(" -\t")]
