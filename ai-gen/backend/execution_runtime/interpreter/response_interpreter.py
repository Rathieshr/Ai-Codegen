"""Provider-independent, evidence-backed engineering response interpretation."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any

from backend.token_intelligence.models import stable_hash

from ..domain import ARTIFACT_TYPES


_FENCE = re.compile(r"```(?P<language>[a-zA-Z0-9_+#.-]*)\s*\n(?P<content>.*?)```", re.DOTALL)
_FILE = re.compile(r"(?<![\w.-])(?P<path>(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:cs|ts|tsx|js|jsx|java|kt|dart|xaml|json|ya?ml|md|sql|py|go|rs|xml|config))(?![\w-])", re.IGNORECASE)
_CLASS = re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)")
_INTERFACE = re.compile(r"\binterface\s+([A-Za-z_][A-Za-z0-9_]*)")
_METHOD = re.compile(r"\b(?:def|function)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(|\b(?:public|private|protected|internal)\s+(?:async\s+)?(?:[A-Za-z_][\w<>,?\[\].]*\s+)+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_API = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[A-Za-z0-9_./{}:-]+)", re.IGNORECASE)

_CATEGORY_FIELDS: dict[str, tuple[str, ...]] = {
    "File": ("files",),
    "Folder": ("folders",),
    "Class": ("classes",),
    "Interface": ("interfaces",),
    "Method": ("methods",),
    "API": ("apis", "routes"),
    "DatabaseChange": ("databaseChanges", "database_changes", "migrations"),
    "ConfigurationChange": ("configurationChanges", "configuration_changes"),
    "DocumentationChange": ("documentationChanges", "documentation_changes"),
    "Todo": ("todos",),
    "Fixme": ("fixmes",),
    "BreakingChange": ("breakingChanges", "breaking_changes"),
    "Warning": ("warnings",),
    "Risk": ("risks",),
    "ArchitectureNote": ("architectureNotes", "architecture_notes"),
    "ImplementationNote": ("implementationNotes", "implementation_notes"),
    "Unknown": ("unknownItems", "unknown_items"),
}

_EXTRACTION_KEYS = {
    "files": "File",
    "folders": "Folder",
    "classes": "Class",
    "interfaces": "Interface",
    "methods": "Method",
    "apis": "API",
    "databaseChanges": "DatabaseChange",
    "configurationChanges": "ConfigurationChange",
    "documentationChanges": "DocumentationChange",
    "testsAdded": "Test",
    "testsModified": "Test",
    "testsRemoved": "Test",
    "todos": "Todo",
    "fixmes": "Fixme",
    "breakingChanges": "BreakingChange",
    "warnings": "Warning",
    "risks": "Risk",
    "architectureNotes": "ArchitectureNote",
    "implementationNotes": "ImplementationNote",
    "unknownItems": "Unknown",
}


class ResponseInterpreter:
    """Transforms provider output without provider calls, repository writes, or downstream work."""

    def interpret(
        self,
        provider_response: Any,
        *,
        session_id: str,
        execution_manifest: dict[str, Any] | None = None,
        repository_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if provider_response is None:
            raise ValueError("providerResponse is required.")
        raw = deepcopy(provider_response)
        content, envelope = _content(provider_response)
        structured, response_type, warnings = _structured(provider_response, content, envelope)
        primary_artifacts = _artifacts(structured, content, session_id)
        engineering_artifacts = [*primary_artifacts]
        engineering_artifacts.extend(_derived_folders(primary_artifacts, session_id, len(engineering_artifacts)))
        engineering_artifacts.extend(_explicit_categories(structured, session_id, len(engineering_artifacts)))
        engineering_artifacts.extend(_text_categories(content, session_id, len(engineering_artifacts)))
        if not content and not engineering_artifacts and isinstance(provider_response, dict) and provider_response:
            opaque = _snippet(json.dumps(provider_response, sort_keys=True, default=str))
            engineering_artifacts.append(_artifact(
                session_id,
                0,
                "Unknown",
                "Unrecognized provider response item",
                content=opaque,
                confidence=0.2,
                evidence=[opaque],
                reason="The provider payload was retained because its shape is unknown; no engineering meaning was inferred.",
            ))
        engineering_artifacts = _dedupe_artifacts(engineering_artifacts)
        engineering_artifacts, repository_warnings, repository_status = _apply_repository_evidence(engineering_artifacts, repository_snapshot)
        warnings.extend(repository_warnings)
        if not content and response_type == "Unknown":
            warnings.append("Provider response shape was not recognized and contained no interpretable engineering content.")
        if not engineering_artifacts:
            warnings.append("No engineering artifacts were detected in the provider response.")
        extraction = _extraction(engineering_artifacts)
        warning_text = _artifact_values(engineering_artifacts, "Warning")
        warnings.extend(warning_text)
        confidence = _confidence(response_type, engineering_artifacts, warnings, repository_status)
        return {
            "interpretationVersion": "5.2",
            "rawResponse": raw,
            "structuredResponse": structured,
            "responseType": response_type,
            "summary": str(structured.get("summary") or _summary(content)),
            # Kept for Milestone 5.1 runtime comparison compatibility. Rich
            # symbol and note extraction is exposed through engineeringArtifacts.
            "artifacts": primary_artifacts,
            "engineeringArtifacts": deepcopy(engineering_artifacts),
            "extraction": extraction,
            "warnings": list(dict.fromkeys(value for value in warnings if value)),
            "risks": _artifact_values(engineering_artifacts, "Risk"),
            "architectureNotes": _artifact_values(engineering_artifacts, "ArchitectureNote"),
            "implementationNotes": _artifact_values(engineering_artifacts, "ImplementationNote"),
            "unknownItems": _artifact_values(engineering_artifacts, "Unknown"),
            "confidence": confidence,
            "repositoryEvidenceStatus": repository_status,
            "lineage": {
                "sessionId": session_id,
                "executionManifestId": str((execution_manifest or {}).get("manifestId") or ""),
                "repositorySnapshotId": str((repository_snapshot or {}).get("snapshotId") or ""),
                "repositorySnapshotVersion": str((repository_snapshot or {}).get("version") or ""),
            },
            "safety": {
                "repositoryWrites": 0,
                "validationInvoked": False,
                "qaInvoked": False,
                "llmCalls": 0,
                "fabricatedEvidence": False,
            },
        }


def _content(value: Any) -> tuple[str, bool]:
    if isinstance(value, str):
        return value.strip(), False
    if not isinstance(value, dict):
        return str(value).strip(), False
    choices = value.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first.get("message"), dict) else {}
        return str(message.get("content") or first.get("text") or "").strip(), True
    if isinstance(value.get("message"), dict):
        return str(value["message"].get("content") or "").strip(), True
    for field in ("response", "content", "text", "output"):
        if isinstance(value.get(field), str):
            return value[field].strip(), True
    return "", False


def _structured(value: Any, content: str, envelope: bool) -> tuple[dict[str, Any], str, list[str]]:
    warnings: list[str] = []
    if isinstance(value, dict) and any(field in value for field in ("artifacts", "files", "changes", *_all_category_fields())):
        return deepcopy(value), "StructuredJson", warnings
    parsed = _parse_json(content)
    if parsed is not None:
        return parsed, "ProviderEnvelope" if envelope else "StructuredJson", warnings
    if "```" in content or re.search(r"^#{1,6}\s", content, re.MULTILINE):
        return {"summary": content}, "Markdown", warnings
    if content:
        warnings.append("Provider response was interpreted as plain text.")
    return {"summary": content} if content else {}, "PlainText" if content else "Unknown", warnings


def _parse_json(content: str) -> dict[str, Any] | None:
    candidate = content.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        value = json.loads(candidate)
        return value if isinstance(value, dict) else {"items": value}
    except (json.JSONDecodeError, TypeError):
        return None


def _artifacts(structured: dict[str, Any], content: str, session_id: str) -> list[dict[str, Any]]:
    raw_items: list[Any] = []
    for field in ("artifacts", "changes"):
        value = structured.get(field)
        if isinstance(value, list):
            raw_items.extend(value)
    artifacts: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items):
        item = raw if isinstance(raw, dict) else {"content": str(raw)}
        path = str(item.get("path") or item.get("file") or item.get("filePath") or "").strip()
        text = str(item.get("content") or item.get("code") or item.get("description") or item.get("name") or "")
        artifact_type = _artifact_type(str(item.get("type") or ""), path, text)
        artifacts.append(_artifact(
            session_id,
            index,
            artifact_type,
            str(item.get("title") or item.get("name") or path or f"{artifact_type} artifact {index + 1}"),
            path=path,
            content=text,
            change_type=_change_type(item.get("changeType") or item.get("operation") or item.get("status")),
            language=str(item.get("language") or _language(path)),
            confidence=_safe_confidence(item.get("confidence"), 0.94 if path else 0.84),
            evidence=_evidence(item.get("evidence"), text or path),
            reason="Explicitly described in the structured provider response.",
        ))
    if not artifacts:
        for index, match in enumerate(_FENCE.finditer(content)):
            text = match.group("content").strip()
            artifacts.append(_artifact(
                session_id,
                index,
                "Code",
                f"Code artifact {index + 1}",
                content=text,
                language=match.group("language"),
                confidence=0.68,
                evidence=[_snippet(match.group(0))],
                reason="Extracted from an explicit fenced code block; no repository path was claimed.",
            ))
    return artifacts


def _explicit_categories(structured: dict[str, Any], session_id: str, offset: int) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    index = offset
    for artifact_type, fields in _CATEGORY_FIELDS.items():
        for field in fields:
            value = structured.get(field)
            for item in _as_items(value):
                path = str(item.get("path") or item.get("file") or "").strip() if isinstance(item, dict) else ""
                text = str(item.get("name") or item.get("title") or item.get("description") or item.get("content") or path) if isinstance(item, dict) else str(item)
                if not text and not path:
                    continue
                artifacts.append(_artifact(
                    session_id,
                    index,
                    artifact_type,
                    text or path,
                    path=path or (text if artifact_type == "File" and _looks_like_path(text) else ""),
                    content=str(item.get("content") or item.get("description") or "") if isinstance(item, dict) else text,
                    change_type=_change_type(item.get("changeType") or item.get("status")) if isinstance(item, dict) else "Proposed",
                    language=_language(path or text),
                    confidence=_safe_confidence(item.get("confidence"), 0.94) if isinstance(item, dict) else 0.9,
                    evidence=_evidence(item.get("evidence"), text) if isinstance(item, dict) else [_snippet(text)],
                    reason=f"Explicitly listed in provider response field '{field}'.",
                ))
                index += 1
    for field, change_type in (("testsAdded", "Added"), ("testsModified", "Modified"), ("testsRemoved", "Deleted")):
        for item in _as_items(structured.get(field)):
            path, text = _path_text(item)
            artifacts.append(_artifact(session_id, index, "Test", text or path or field, path=path, content=text, change_type=change_type, language=_language(path), confidence=0.94, evidence=[_snippet(text or path)], reason=f"Explicitly listed in provider response field '{field}'."))
            index += 1
    return artifacts


def _text_categories(content: str, session_id: str, offset: int) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    index = offset
    for match in _FILE.finditer(content):
        path = match.group("path")
        kind = _artifact_type("", path, "")
        artifacts.append(_artifact(session_id, index, kind if kind in {"Test", "Documentation", "Configuration", "Migration", "API"} else "File", path, path=path, language=_language(path), confidence=0.78, evidence=[_snippet(match.group(0))], reason="An explicit file path appears in the provider response."))
        index += 1
        folder = str(PurePosixPath(path).parent)
        if folder and folder != ".":
            artifacts.append(_artifact(session_id, index, "Folder", folder, path=folder, confidence=0.74, evidence=[path], reason="Derived only from the parent folder of an explicitly named file path."))
            index += 1
    for artifact_type, pattern in (("Class", _CLASS), ("Interface", _INTERFACE), ("Method", _METHOD)):
        for match in pattern.finditer(content):
            name = next((group for group in match.groups() if group), "")
            artifacts.append(_artifact(session_id, index, artifact_type, name, content=name, confidence=0.76, evidence=[_snippet(match.group(0))], reason=f"An explicit {artifact_type.lower()} declaration appears in the provider response."))
            index += 1
    for match in _API.finditer(content):
        value = f"{match.group(1).upper()} {match.group(2)}"
        artifacts.append(_artifact(session_id, index, "API", value, content=value, confidence=0.82, evidence=[value], reason="An explicit HTTP method and route appear in the provider response."))
        index += 1
    for line in content.splitlines():
        stripped = line.strip(" \t-*#")
        lowered = stripped.casefold()
        marker_type = ""
        if "todo" in lowered:
            marker_type = "Todo"
        elif "fixme" in lowered:
            marker_type = "Fixme"
        elif lowered.startswith(("breaking change", "breaking:")):
            marker_type = "BreakingChange"
        elif lowered.startswith(("warning:", "warning ")):
            marker_type = "Warning"
        elif lowered.startswith(("risk:", "risk ")):
            marker_type = "Risk"
        elif lowered.startswith(("architecture:", "architecture note")):
            marker_type = "ArchitectureNote"
        elif lowered.startswith(("implementation:", "implementation note")):
            marker_type = "ImplementationNote"
        if marker_type and stripped:
            artifacts.append(_artifact(session_id, index, marker_type, stripped, content=stripped, confidence=0.78, evidence=[_snippet(line)], reason=f"The provider response explicitly marks this as {marker_type}."))
            index += 1
    return artifacts


def _derived_folders(artifacts: list[dict[str, Any]], session_id: str, offset: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for artifact in artifacts:
        path = str(artifact.get("path") or "")
        folder = str(PurePosixPath(path).parent) if path else ""
        if folder and folder != ".":
            result.append(_artifact(session_id, offset + len(result), "Folder", folder, path=folder, confidence=0.8, evidence=[path], reason="Derived only from the parent folder of an explicitly named artifact path."))
    return result


def _artifact(session_id: str, index: int, artifact_type: str, title: str, *, path: str = "", content: str = "", change_type: str = "Proposed", language: str = "", confidence: float = 0.8, evidence: list[str] | None = None, reason: str = "") -> dict[str, Any]:
    core = {"sessionId": session_id, "type": artifact_type, "title": title, "path": path, "content": content}
    return {
        "artifactId": f"executionartifact_{stable_hash(core)[:12]}",
        "sessionId": session_id,
        "type": artifact_type if artifact_type in ARTIFACT_TYPES else "Unknown",
        "path": path,
        "title": title,
        "changeType": change_type,
        "language": language,
        "content": content,
        "confidence": round(max(0.05, min(1.0, confidence)), 2),
        "evidence": [value for value in (evidence or []) if value],
        "source": "AI Provider Response",
        "reason": reason,
        "repositoryEvidence": "NotEvaluated",
        "sequence": index,
    }


def _apply_repository_evidence(artifacts: list[dict[str, Any]], snapshot: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[str], str]:
    if not isinstance(snapshot, dict) or not snapshot:
        for artifact in artifacts:
            if artifact.get("path"):
                artifact["repositoryEvidence"] = "Unavailable"
                artifact["confidence"] = round(max(0.05, artifact["confidence"] - 0.12), 2)
        return artifacts, ["Repository snapshot is unavailable; paths remain provider claims and were not verified."], "Unavailable"
    metadata = snapshot.get("metadata") if isinstance(snapshot.get("metadata"), dict) else {}
    files = metadata.get("files") if isinstance(metadata.get("files"), list) else []
    known = {_normalize_path(value.get("path") or value.get("file")) for value in files if isinstance(value, dict)}
    known.update(_normalize_path(value) for value in (metadata.get("filesByPath") or {}).keys() if isinstance(metadata.get("filesByPath"), dict))
    known.discard("")
    warnings: list[str] = []
    snapshot_id = str(snapshot.get("snapshotId") or snapshot.get("version") or "supplied snapshot")
    for artifact in artifacts:
        path = _normalize_path(artifact.get("path"))
        if not path or artifact.get("type") == "Folder":
            continue
        if path in known:
            artifact["repositoryEvidence"] = "Matched"
            artifact["source"] = "AI Provider Response + Repository Snapshot"
            artifact["evidence"] = list(dict.fromkeys([*artifact["evidence"], f"Repository snapshot {snapshot_id} contains {path}."]))
            artifact["confidence"] = round(min(0.99, artifact["confidence"] + 0.04), 2)
        else:
            artifact["repositoryEvidence"] = "Unverified"
            artifact["confidence"] = round(max(0.05, artifact["confidence"] - 0.1), 2)
            warnings.append(f"Path was not present in supplied repository snapshot metadata: {path}")
    return artifacts, warnings, "Available"


def _extraction(artifacts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result = {key: [] for key in _EXTRACTION_KEYS}
    for artifact in artifacts:
        if artifact.get("path") and artifact["type"] not in {"Folder"}:
            result["files"].append(deepcopy(artifact))
        target = next((key for key, artifact_type in _EXTRACTION_KEYS.items() if artifact_type == artifact["type"]), "")
        if artifact["type"] == "Test":
            target = {"Added": "testsAdded", "Modified": "testsModified", "Deleted": "testsRemoved"}.get(artifact["changeType"], "testsModified")
        elif artifact["type"] == "Documentation":
            target = "documentationChanges"
        elif artifact["type"] == "Configuration":
            target = "configurationChanges"
        elif artifact["type"] == "Migration":
            target = "databaseChanges"
        if target and not (target == "files" and artifact.get("path")):
            result[target].append(deepcopy(artifact))
    return result


def _artifact_type(explicit: str, path: str, content: str) -> str:
    normalized = explicit.strip().replace(" ", "").casefold()
    aliases = {value.casefold(): value for value in ARTIFACT_TYPES}
    aliases.update({"docs": "Documentation", "config": "Configuration", "refactor": "Refactoring", "bugfix": "BugFix", "database": "DatabaseChange"})
    if normalized in aliases:
        return aliases[normalized]
    lower = path.casefold()
    if any(marker in lower for marker in ("test", "spec")):
        return "Test"
    if lower.endswith((".md", ".rst", ".txt")):
        return "Documentation"
    if lower.endswith((".json", ".yaml", ".yml", ".toml", ".ini", ".config", ".xml")):
        return "Configuration"
    if "migration" in lower or lower.endswith(".sql"):
        return "Migration"
    if "controller" in lower or "api" in lower:
        return "API"
    if path or content.strip().startswith(("class ", "interface ", "function ", "def ")):
        return "Code"
    return "Unknown"


def _change_type(value: Any) -> str:
    normalized = str(value or "Proposed").strip().casefold()
    return {"add": "Added", "added": "Added", "create": "Added", "modify": "Modified", "modified": "Modified", "update": "Modified", "delete": "Deleted", "deleted": "Deleted", "remove": "Deleted"}.get(normalized, "Proposed")


def _language(path: str) -> str:
    suffix = path.rsplit(".", 1)[-1].casefold() if "." in path else ""
    return {"cs": "C#", "ts": "TypeScript", "tsx": "TypeScript", "js": "JavaScript", "jsx": "JavaScript", "java": "Java", "kt": "Kotlin", "dart": "Dart", "xaml": "XAML", "py": "Python", "sql": "SQL", "md": "Markdown", "json": "JSON", "yaml": "YAML", "yml": "YAML"}.get(suffix, suffix.upper())


def _confidence(response_type: str, artifacts: list[dict[str, Any]], warnings: list[str], repository_status: str) -> float:
    base = {"StructuredJson": 0.94, "ProviderEnvelope": 0.9, "Markdown": 0.76, "PlainText": 0.62, "Unknown": 0.25}.get(response_type, 0.4)
    if artifacts:
        artifact_average = sum(float(item["confidence"]) for item in artifacts) / len(artifacts)
        base = (base + artifact_average) / 2
    if repository_status == "Unavailable":
        base -= 0.08
    return round(max(0.05, min(0.99, base - min(0.18, len(warnings) * 0.015))), 2)


def _as_items(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _path_text(value: Any) -> tuple[str, str]:
    if isinstance(value, dict):
        path = str(value.get("path") or value.get("file") or "").strip()
        text = str(value.get("name") or value.get("title") or value.get("description") or value.get("content") or path).strip()
        return path, text
    text = str(value).strip()
    return (text, text) if _looks_like_path(text) else ("", text)


def _evidence(value: Any, fallback: str) -> list[str]:
    items = value if isinstance(value, list) else ([value] if value else [])
    result = [_snippet(str(item)) for item in items if str(item).strip()]
    return result or ([_snippet(fallback)] if fallback else [])


def _safe_confidence(value: Any, fallback: float) -> float:
    try:
        return max(0.05, min(1.0, float(value))) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback


def _dedupe_artifacts(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for artifact in artifacts:
        key = (artifact["type"].casefold(), _normalize_path(artifact.get("path")), artifact["title"].strip().casefold())
        if key not in seen:
            seen.add(key)
            artifact["sequence"] = len(result)
            result.append(artifact)
    return result


def _artifact_values(artifacts: list[dict[str, Any]], artifact_type: str) -> list[str]:
    return list(dict.fromkeys(str(item.get("content") or item.get("title") or "") for item in artifacts if item["type"] == artifact_type and str(item.get("content") or item.get("title") or "")))


def _all_category_fields() -> tuple[str, ...]:
    return tuple(field for fields in _CATEGORY_FIELDS.values() for field in fields) + ("testsAdded", "testsModified", "testsRemoved")


def _normalize_path(value: Any) -> str:
    return str(value or "").strip().replace("\\", "/").removeprefix("./")


def _looks_like_path(value: str) -> bool:
    return bool(_FILE.fullmatch(value.strip()))


def _summary(content: str) -> str:
    return " ".join(content.strip().split())[:500]


def _snippet(value: str) -> str:
    return " ".join(value.strip().split())[:500]
