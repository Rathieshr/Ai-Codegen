"""Repository parser foundation for supported languages."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from backend.platform.shared import JsonListStore, generated_id

from ..domain import (
    IRepositoryParserService,
    Repository,
    RepositoryLanguage,
    RepositoryParsedSymbol,
    RepositorySnapshot,
    RepositorySymbolKind,
)


class FileBackedRepositoryParserService(IRepositoryParserService):
    def __init__(
        self,
        storage_path: Path,
        remote_content_provider: Callable[[Repository, str], str] | None = None,
        *,
        max_remote_files: int = 500,
        max_remote_file_size: int = 1_000_000,
    ) -> None:
        self._store = JsonListStore(storage_path)
        self._remote_content_provider = remote_content_provider
        self._max_remote_files = max_remote_files
        self._max_remote_file_size = max_remote_file_size

    def parse_snapshot(self, repository: Repository, snapshot: RepositorySnapshot) -> list[RepositoryParsedSymbol]:
        root_path = str(repository.metadata.get("localPath") or "").strip()
        root = Path(root_path).expanduser().resolve() if root_path else None
        files = list((snapshot.metadata or {}).get("files") or [])
        if (not root or not root.exists()) and self._remote_content_provider:
            return self._parse_remote(repository, snapshot, files)
        if not root or not root.exists():
            return []
        if snapshot.scan_mode == "Incremental":
            return self._parse_incremental(repository, snapshot, root, files)
        return self._parse_full(repository, snapshot, root, files)

    def _parse_remote(
        self,
        repository: Repository,
        snapshot: RepositorySnapshot,
        files: list[dict[str, object]],
    ) -> list[RepositoryParsedSymbol]:
        candidates = files
        carry_forward: list[RepositoryParsedSymbol] = []
        if snapshot.scan_mode == "Incremental":
            previous_symbols = self.list_symbols(repository.repository_id)
            diff = dict((snapshot.metadata or {}).get("diff") or {})
            changed_paths = set(diff.get("added") or []) | set(diff.get("changed") or [])
            changed_paths |= {pair[1] for pair in list(diff.get("renamed") or []) if len(pair) == 2}
            removed_paths = set(diff.get("deleted") or [])
            removed_paths |= {pair[0] for pair in list(diff.get("renamed") or []) if len(pair) == 2}
            if previous_symbols:
                carry_forward = [
                    RepositoryParsedSymbol.from_dict({**item.to_dict(), "snapshotId": snapshot.snapshot_id})
                    for item in previous_symbols
                    if item.path not in changed_paths and item.path not in removed_paths
                ]
                candidates = [item for item in files if str(item.get("path") or "") in changed_paths]

        parsed: list[RepositoryParsedSymbol] = []
        fetched = 0
        for file_record in candidates:
            if fetched >= self._max_remote_files:
                break
            relative_path = str(file_record.get("path") or "")
            language = _language_for_record(file_record)
            size = int(file_record.get("size") or 0)
            if not relative_path or language == RepositoryLanguage.UNKNOWN or size > self._max_remote_file_size:
                continue
            try:
                content = self._remote_content_provider(repository, relative_path) if self._remote_content_provider else ""
            except Exception:
                continue
            fetched += 1
            parsed.extend(self._symbols_from_content(repository, snapshot, relative_path, content, language))
        return _dedupe_symbols([*carry_forward, *parsed])

    def save_symbols(
        self,
        repository_id: str,
        snapshot_id: str,
        symbols: list[RepositoryParsedSymbol],
    ) -> list[RepositoryParsedSymbol]:
        items = [RepositoryParsedSymbol.from_dict(item) for item in self._store.read()]
        filtered = [
            item for item in items if not (item.repository_id == repository_id and item.snapshot_id == snapshot_id)
        ]
        filtered.extend(symbols)
        self._store.write([item.to_dict() for item in filtered])
        return symbols

    def list_symbols(
        self,
        repository_id: str,
        *,
        snapshot_id: str = "",
        language: str = "",
        kind: str = "",
        path: str = "",
        search: str = "",
    ) -> list[RepositoryParsedSymbol]:
        symbols = [
            RepositoryParsedSymbol.from_dict(item)
            for item in self._store.read()
            if str(item.get("repositoryId") or item.get("repository_id")) == repository_id
        ]
        if snapshot_id:
            symbols = [item for item in symbols if item.snapshot_id == snapshot_id]
        normalized_language = language.strip().lower()
        if normalized_language:
            symbols = [item for item in symbols if item.language.value.lower() == normalized_language]
        normalized_kind = kind.strip().lower()
        if normalized_kind:
            symbols = [item for item in symbols if item.kind.value.lower() == normalized_kind]
        normalized_path = path.strip().lower()
        if normalized_path:
            symbols = [item for item in symbols if normalized_path in item.path.lower()]
        normalized_search = search.strip().lower()
        if normalized_search:
            symbols = [
                item
                for item in symbols
                if normalized_search in item.name.lower()
                or normalized_search in item.namespace.lower()
                or normalized_search in item.container.lower()
                or normalized_search in item.path.lower()
            ]
        return symbols

    def _parse_full(
        self,
        repository: Repository,
        snapshot: RepositorySnapshot,
        root: Path,
        files: list[dict[str, object]],
    ) -> list[RepositoryParsedSymbol]:
        symbols: list[RepositoryParsedSymbol] = []
        for file_record in files:
            symbols.extend(self._parse_file(repository, snapshot, root, file_record))
        return symbols

    def _parse_incremental(
        self,
        repository: Repository,
        snapshot: RepositorySnapshot,
        root: Path,
        files: list[dict[str, object]],
    ) -> list[RepositoryParsedSymbol]:
        diff = dict((snapshot.metadata or {}).get("diff") or {})
        previous_symbols = self.list_symbols(repository.repository_id)
        changed_paths = set(diff.get("added") or []) | set(diff.get("changed") or [])
        changed_paths |= {pair[1] for pair in list(diff.get("renamed") or []) if len(pair) == 2}
        removed_paths = set(diff.get("deleted") or [])
        removed_paths |= {pair[0] for pair in list(diff.get("renamed") or []) if len(pair) == 2}
        carry_forward = [
            RepositoryParsedSymbol.from_dict(
                {
                    **item.to_dict(),
                    "snapshotId": snapshot.snapshot_id,
                }
            )
            for item in previous_symbols
            if item.path not in changed_paths and item.path not in removed_paths
        ]
        current_files = {str(item.get("path") or ""): item for item in files}
        reparsed: list[RepositoryParsedSymbol] = []
        for path in sorted(changed_paths):
            file_record = current_files.get(path)
            if file_record:
                reparsed.extend(self._parse_file(repository, snapshot, root, file_record))
        return carry_forward + reparsed

    def _parse_file(
        self,
        repository: Repository,
        snapshot: RepositorySnapshot,
        root: Path,
        file_record: dict[str, object],
    ) -> list[RepositoryParsedSymbol]:
        relative_path = str(file_record.get("path") or "")
        if not relative_path:
            return []
        full_path = (root / relative_path).resolve()
        if not full_path.exists() or not full_path.is_file():
            return []
        content = full_path.read_text(encoding="utf-8", errors="ignore")
        language = _language_for_record(file_record)
        return self._symbols_from_content(repository, snapshot, relative_path, content, language)

    def _symbols_from_content(
        self,
        repository: Repository,
        snapshot: RepositorySnapshot,
        relative_path: str,
        content: str,
        language: RepositoryLanguage,
    ) -> list[RepositoryParsedSymbol]:
        parsed = _extract_symbols_for_content(relative_path, content, language)
        output: list[RepositoryParsedSymbol] = []
        for item in parsed:
            output.append(
                RepositoryParsedSymbol(
                    symbol_id=generated_id("parsed_symbol"),
                    repository_id=repository.repository_id,
                    snapshot_id=snapshot.snapshot_id,
                    path=relative_path,
                    language=language,
                    kind=item["kind"],
                    name=item["name"],
                    namespace=item.get("namespace", ""),
                    container=item.get("container", ""),
                    signature=item.get("signature", ""),
                    metadata=item.get("metadata", {}),
                )
            )
        return _dedupe_symbols(output)


def _extract_symbols_for_content(
    path: str,
    content: str,
    language: RepositoryLanguage,
) -> list[dict[str, object]]:
    namespace = _extract_namespace(content, language)
    containers = _container_positions(content)
    items: list[dict[str, object]] = []
    items.extend(_namespace_symbols(namespace))
    items.extend(_import_symbols(content, language, namespace))
    items.extend(_type_symbols(content, namespace))
    items.extend(_method_symbols(content, language, namespace, containers))
    items.extend(_attribute_symbols(content, language, namespace))
    items.extend(_route_symbols(content, language, namespace))
    items.extend(_role_symbols(path, content, namespace))
    if language in {RepositoryLanguage.JSON, RepositoryLanguage.YAML, RepositoryLanguage.XAML, RepositoryLanguage.XML}:
        items.extend(_structured_symbols(content, language, namespace))
    return items


def _extract_namespace(content: str, language: RepositoryLanguage) -> str:
    patterns = []
    if language == RepositoryLanguage.CSHARP:
        patterns.append(r"\bnamespace\s+([A-Za-z0-9_.]+)")
    if language in {RepositoryLanguage.JAVA, RepositoryLanguage.KOTLIN, RepositoryLanguage.DART}:
        patterns.append(r"\bpackage\s+([A-Za-z0-9_.]+)")
    if language in {RepositoryLanguage.XAML, RepositoryLanguage.XML}:
        patterns.append(r'x:Class="([^"]+)"')
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()
    return ""


def _namespace_symbols(namespace: str) -> list[dict[str, object]]:
    if not namespace:
        return []
    return [{"kind": RepositorySymbolKind.NAMESPACE, "name": namespace, "namespace": namespace}]


def _import_symbols(content: str, language: RepositoryLanguage, namespace: str) -> list[dict[str, object]]:
    imports: list[str] = []
    for pattern in [
        r"^\s*using\s+([A-Za-z0-9_.]+)\s*;",
        r"^\s*import\s+.*?from\s+['\"]([^'\"]+)['\"]",
        r"^\s*import\s+['\"]([^'\"]+)['\"]",
        r"require\(\s*['\"]([^'\"]+)['\"]\s*\)",
    ]:
        imports.extend(re.findall(pattern, content, flags=re.MULTILINE))
    if language in {RepositoryLanguage.JAVA, RepositoryLanguage.KOTLIN, RepositoryLanguage.DART}:
        imports.extend(re.findall(r"^\s*import\s+([A-Za-z0-9_.*]+)\s*;?", content, flags=re.MULTILINE))
    if language in {RepositoryLanguage.XAML, RepositoryLanguage.XML}:
        imports.extend(re.findall(r'xmlns(?::\w+)?="([^"]+)"', content))
    return [
        {
            "kind": RepositorySymbolKind.IMPORT,
            "name": item,
            "namespace": namespace,
            "metadata": {"import": item},
        }
        for item in _dedupe_strings(imports)
    ]


def _type_symbols(content: str, namespace: str) -> list[dict[str, object]]:
    symbols: list[dict[str, object]] = []
    for kind_name, symbol_kind in {
        "class": RepositorySymbolKind.CLASS,
        "interface": RepositorySymbolKind.INTERFACE,
        "enum": RepositorySymbolKind.ENUM,
    }.items():
        pattern = rf"\b{kind_name}\s+([A-Za-z_][A-Za-z0-9_]*)"
        for match in re.finditer(pattern, content):
            symbols.append(
                {
                    "kind": symbol_kind,
                    "name": match.group(1),
                    "namespace": namespace,
                    "signature": match.group(0).strip(),
                }
            )
    return symbols


def _method_symbols(
    content: str,
    language: RepositoryLanguage,
    namespace: str,
    containers: list[tuple[int, str]],
) -> list[dict[str, object]]:
    patterns = [
        r"\bfun\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\([^)]*\)\s*=>",
        r"\b(?:public|private|protected|internal|static|async|override|virtual|abstract|final|suspend|\s)+[A-Za-z0-9_<>\[\]?.,]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        r"^\s*(?:async\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*\{",
    ]
    methods: list[dict[str, object]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, content):
            name = match.group(1)
            if name in {"if", "for", "while", "switch", "catch", "return", "new", "constructor"}:
                continue
            methods.append(
                {
                    "kind": RepositorySymbolKind.METHOD,
                    "name": name,
                    "namespace": namespace,
                    "container": _nearest_container(match.start(), containers),
                    "signature": match.group(0).strip(),
                }
            )
    return methods


def _attribute_symbols(content: str, language: RepositoryLanguage, namespace: str) -> list[dict[str, object]]:
    matches = re.findall(r"\[([A-Za-z_][A-Za-z0-9_]*(?:\([^\]]*\))?)\]", content)
    matches.extend(re.findall(r"^\s*@([A-Za-z_][A-Za-z0-9_]*)", content, flags=re.MULTILINE))
    if language in {RepositoryLanguage.XAML, RepositoryLanguage.XML}:
        matches.extend(re.findall(r"\s([A-Za-z_:][A-Za-z0-9_:.-]*)=\"[^\"]*\"", content))
    return [
        {
            "kind": RepositorySymbolKind.ATTRIBUTE,
            "name": item,
            "namespace": namespace,
            "metadata": {"attribute": item},
        }
        for item in _dedupe_strings(matches)
    ]


def _route_symbols(content: str, language: RepositoryLanguage, namespace: str) -> list[dict[str, object]]:
    routes = re.findall(r"\[(?:Route|HttpGet|HttpPost|HttpPut|HttpDelete|HttpPatch)\(\"([^\"]+)\"\)\]", content)
    routes.extend(re.findall(r"\b(?:app|router)\.(?:get|post|put|delete|patch)\(\s*['\"]([^'\"]+)['\"]", content))
    if language in {RepositoryLanguage.JSON, RepositoryLanguage.YAML}:
        routes.extend(re.findall(r'["\'](?:route|path)["\']\s*[:=]\s*["\']([^"\']+)["\']', content))
        routes.extend(re.findall(r"^\s*path:\s*([^\s#]+)", content, flags=re.MULTILINE))
    return [
        {
            "kind": RepositorySymbolKind.ROUTE,
            "name": item,
            "namespace": namespace,
            "metadata": {"route": item},
        }
        for item in _dedupe_strings(routes)
    ]


def _role_symbols(path: str, content: str, namespace: str) -> list[dict[str, object]]:
    symbols: list[dict[str, object]] = []
    names = re.findall(r"\b(class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)", content)
    names.extend([("file", Path(path).stem)])
    for _kind, name in names:
        lowered = name.lower()
        if lowered.endswith("controller"):
            symbols.append({"kind": RepositorySymbolKind.CONTROLLER, "name": name, "namespace": namespace})
        if lowered.endswith("repository"):
            symbols.append({"kind": RepositorySymbolKind.REPOSITORY, "name": name, "namespace": namespace})
        if lowered.endswith("service"):
            symbols.append({"kind": RepositorySymbolKind.SERVICE, "name": name, "namespace": namespace})
        if lowered.endswith("test") or lowered.endswith("tests") or lowered.endswith("spec"):
            symbols.append({"kind": RepositorySymbolKind.TEST, "name": name, "namespace": namespace})
    if "/test" in path.lower() or path.lower().endswith((".spec.ts", ".test.ts", "_test.dart", "test.java", "test.kt")):
        symbols.append({"kind": RepositorySymbolKind.TEST, "name": Path(path).stem, "namespace": namespace})
    return symbols


def _structured_symbols(content: str, language: RepositoryLanguage, namespace: str) -> list[dict[str, object]]:
    symbols: list[dict[str, object]] = []
    if language == RepositoryLanguage.JSON:
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                for key in parsed.keys():
                    symbols.append(
                        {
                            "kind": RepositorySymbolKind.ATTRIBUTE,
                            "name": str(key),
                            "namespace": namespace,
                            "metadata": {"key": str(key)},
                        }
                    )
        except json.JSONDecodeError:
            pass
        return symbols
    if language == RepositoryLanguage.YAML:
        keys = re.findall(r"^\s*([A-Za-z0-9_.-]+):", content, flags=re.MULTILINE)
        return [
            {
                "kind": RepositorySymbolKind.ATTRIBUTE,
                "name": key,
                "namespace": namespace,
                "metadata": {"key": key},
            }
            for key in _dedupe_strings(keys)
        ]
    if language in {RepositoryLanguage.XAML, RepositoryLanguage.XML}:
        classes = re.findall(r'x:Class="([^"]+)"', content)
        for class_name in classes:
            symbols.append(
                {
                    "kind": RepositorySymbolKind.CLASS,
                    "name": class_name.split(".")[-1],
                    "namespace": class_name,
                    "signature": class_name,
                }
            )
        tags = re.findall(r"<([A-Za-z_:][A-Za-z0-9_:.-]*)", content)
        for tag in _dedupe_strings(tags):
            symbols.append(
                {
                    "kind": RepositorySymbolKind.CLASS,
                    "name": tag,
                    "namespace": namespace,
                    "metadata": {"tag": tag},
                }
            )
        return symbols
    return symbols


def _container_positions(content: str) -> list[tuple[int, str]]:
    containers: list[tuple[int, str]] = []
    for match in re.finditer(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", content):
        containers.append((match.start(), match.group(1)))
    return containers


def _nearest_container(position: int, containers: list[tuple[int, str]]) -> str:
    current = ""
    for offset, name in containers:
        if offset > position:
            break
        current = name
    return current


def _language_for_record(file_record: dict[str, object]) -> RepositoryLanguage:
    value = str(file_record.get("language") or "")
    for language in RepositoryLanguage:
        if language.value == value:
            return language
    extension = str(file_record.get("extension") or "").lower()
    return {
        "cs": RepositoryLanguage.CSHARP,
        "ts": RepositoryLanguage.TYPESCRIPT,
        "tsx": RepositoryLanguage.TYPESCRIPT,
        "js": RepositoryLanguage.JAVASCRIPT,
        "jsx": RepositoryLanguage.JAVASCRIPT,
        "kt": RepositoryLanguage.KOTLIN,
        "java": RepositoryLanguage.JAVA,
        "dart": RepositoryLanguage.DART,
        "xaml": RepositoryLanguage.XAML,
        "xml": RepositoryLanguage.XML,
        "json": RepositoryLanguage.JSON,
        "yaml": RepositoryLanguage.YAML,
        "yml": RepositoryLanguage.YAML,
    }.get(extension, RepositoryLanguage.UNKNOWN)


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _dedupe_symbols(symbols: list[RepositoryParsedSymbol]) -> list[RepositoryParsedSymbol]:
    result: list[RepositoryParsedSymbol] = []
    seen: set[tuple[str, str, str, str]] = set()
    for symbol in symbols:
        key = (symbol.path, symbol.kind.value, symbol.name, symbol.signature)
        if key in seen:
            continue
        seen.add(key)
        result.append(symbol)
    return result
