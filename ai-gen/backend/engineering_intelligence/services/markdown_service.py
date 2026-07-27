"""Reusable Markdown indexing over supplied documents.

This service never scans a repository. Callers provide documents already read by
Repository Intelligence or an ingestion provider.
"""

from __future__ import annotations

import re
from typing import Any


class MarkdownService:
    def __init__(self) -> None:
        self._documents: list[dict[str, Any]] = []

    def index_markdown(self, documents: dict[str, str]) -> dict[str, Any]:
        indexed = []
        for path, content in documents.items():
            if not str(path).casefold().endswith((".md", ".markdown")):
                continue
            headings = [
                match.group(1).strip()
                for match in re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*$", str(content))
            ]
            indexed.append({
                "path": str(path),
                "title": headings[0] if headings else str(path).rsplit("/", 1)[-1],
                "headings": headings,
                "summary": _compact(str(content), 900),
                "content": str(content),
            })
        self._documents = indexed
        return {"documentsIndexed": len(indexed), "documents": self._public(indexed)}

    def search_documentation(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        terms = {item for item in re.findall(r"[a-z0-9]+", query.casefold()) if len(item) > 2}
        ranked = []
        for document in self._documents:
            searchable = " ".join([
                document["path"], document["title"], *document["headings"], document["content"],
            ]).casefold()
            score = sum(searchable.count(term) for term in terms)
            if score:
                ranked.append((score, document))
        ranked.sort(key=lambda item: (-item[0], item[1]["path"]))
        return self._public([item[1] for item in ranked[: max(0, limit)]])

    def get_architecture_summary(self) -> str:
        candidates = [
            item for item in self._documents
            if any(
                term in (item["path"] + " " + " ".join(item["headings"])).casefold()
                for term in ("architecture", "adr", "design")
            )
        ]
        return "\n\n".join(item["summary"] for item in candidates[:5])

    @staticmethod
    def _public(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{key: value for key, value in item.items() if key != "content"} for item in documents]

    indexMarkdown = index_markdown
    searchDocumentation = search_documentation
    getArchitectureSummary = get_architecture_summary


def _compact(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]
