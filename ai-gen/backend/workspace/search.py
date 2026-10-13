"""Bounded global search projection for the Engineering Command Center."""

from __future__ import annotations

from typing import Any, Callable


def _text(value: Any) -> str:
    return str(value or "").strip()


class WorkspaceSearchService:
    def __init__(self, *, planning=None, execution=None, repositories=None, ado=None, agents=None, memory=None, activity=None) -> None:
        self.planning = planning
        self.execution = execution
        self.repositories = repositories
        self.ado = ado
        self.agents = agents
        self.memory = memory
        self.activity = activity

    def search(self, query: str, project_id: str = "", limit: int = 60) -> dict[str, Any]:
        query = query.strip()
        if not query:
            return {"query": "", "results": [], "count": 0}
        results: list[dict[str, Any]] = []
        self._collect(results, lambda: self._planning(query, project_id))
        self._collect(results, lambda: self._execution(query))
        self._collect(results, lambda: self._repository(query))
        self._collect(results, lambda: self._ado(query, project_id))
        self._collect(results, self._agents)
        self._collect(results, lambda: self._memory(query, project_id))
        self._collect(results, lambda: self._activity(query))
        ranked = []
        for item in results:
            item["score"] = _fuzzy_score(query, f"{item['title']} {item['subtitle']} {item['category']}")
            if item["score"] > 0:
                ranked.append(item)
        ranked.sort(key=lambda item: (-item["score"], item["category"], item["title"].casefold()))
        bounded = ranked[:max(1, min(limit, 100))]
        return {"query": query, "results": bounded, "count": len(bounded), "totalMatches": len(ranked)}

    @staticmethod
    def _collect(target: list[dict[str, Any]], provider: Callable[[], list[dict[str, Any]]]) -> None:
        try:
            target.extend(provider())
        except Exception:
            return

    def _planning(self, query: str, project_id: str) -> list[dict[str, Any]]:
        payload = self.planning.list(project_id=project_id, search="", limit=250) if self.planning else {}
        categories = {"Requirement": "Requirements", "Epic": "Epics", "Feature": "Features", "Story": "Stories", "Task": "Tasks"}
        return [_result(categories.get(_text(item.get("type")), "Planning"), _text(item.get("id")), _text(item.get("title")), _text(item.get("status")), "planning", item.get("sourceItemId")) for item in payload.get("items", [])]

    def _execution(self, query: str) -> list[dict[str, Any]]:
        payload = self.execution.list(search="", limit=250) if self.execution else {}
        return [_result("Execution Packages", _text(item.get("id")), _text(item.get("title")), _text(item.get("status")), "execution", item.get("id")) for item in payload.get("items", [])]

    def _repository(self, query: str) -> list[dict[str, Any]]:
        if not self.repositories:
            return []
        result = []
        file_paths: set[str] = set()
        repositories = self.repositories.list_repositories().get("repositories", [])
        for repository in repositories:
            repository_id = _text(repository.get("repositoryId"))
            result.append(_result("Repository", repository_id, _text(repository.get("name")), _text(repository.get("defaultBranch") or repository.get("status")), "repository", repository_id))
            symbols = self.repositories.list_symbols(repository_id, search="") or {}
            for symbol in symbols.get("symbols", [])[:40]:
                kind = _text(symbol.get("kind") or "Symbol")
                path = _text(symbol.get("path"))
                category = "APIs" if kind in {"API", "Route", "Controller"} else "Services" if kind == "Service" else "Files" if kind == "File" else "Symbols"
                result.append(_result(category, _text(symbol.get("symbolId") or symbol.get("id")), _text(symbol.get("name")), _text(symbol.get("path") or kind), "repository", repository_id))
                if path and path not in file_paths:
                    file_paths.add(path)
                    result.append(_result("Files", path, path.rsplit("/", 1)[-1], path, "repository", repository_id))
        return result

    def _ado(self, query: str, project_id: str) -> list[dict[str, Any]]:
        if not self.ado:
            return []
        work = self.ado.work_items(project_id, search="", limit=250)
        prs = self.ado.pull_requests(project_id, search="", limit=250)
        values = [_result("Azure DevOps Work Items", _text(item.get("workItemId")), _text(item.get("title")), f"{_text(item.get('type'))} · {_text(item.get('state'))}", "azure-devops", item.get("workItemId")) for item in work.get("items", [])]
        values.extend(_result("Pull Requests", _text(item.get("pullRequestId")), _text(item.get("title")), _text(item.get("status")), "azure-devops", item.get("pullRequestId")) for item in prs.get("items", []))
        return values

    def _agents(self) -> list[dict[str, Any]]:
        payload = self.agents.list() if self.agents else {}
        return [_result("Agents", _text(item.get("agentId")), _text(item.get("name")), _text(item.get("status")), "agents", item.get("agentId")) for item in payload.get("agents", [])]

    def _memory(self, query: str, project_id: str) -> list[dict[str, Any]]:
        payload = self.memory.list_memory(project_id=project_id) if self.memory else {}
        return [_result("Memory", _text(item.get("id")), _text(item.get("title")), _text(item.get("category")), "overview", item.get("id")) for item in payload.get("memories", []) if query.casefold() in f"{item.get('title')} {item.get('summary')} {item.get('tags')}".casefold()]

    def _activity(self, query: str) -> list[dict[str, Any]]:
        payload = self.activity.list(search=query, limit=100) if self.activity else {}
        return [_result("Activities", _text(item.get("activityId")), _text(item.get("title")), _text(item.get("category")), "activity", item.get("activityId")) for item in payload.get("activity", [])]


def _result(category: str, result_id: str, title: str, subtitle: str, route: str, entity_id: Any = "") -> dict[str, Any]:
    return {"id": f"{category}:{result_id}", "category": category, "title": title or result_id or category, "subtitle": subtitle, "route": route, "entityId": _text(entity_id), "score": 0}


def _fuzzy_score(query: str, value: str) -> int:
    query, value = query.casefold(), value.casefold()
    if query in value:
        return 1000 - value.index(query) + len(query) * 5
    position = -1
    score = 0
    for character in query:
        position = value.find(character, position + 1)
        if position < 0:
            return 0
        score += 3 if position == 0 or value[position - 1] in " -_/#" else 1
    return score
