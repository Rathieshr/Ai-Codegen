"""JSON storage helpers for repo context."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def read_json(path: str | Path, default: Any = None) -> Any:
    """Read UTF-8 JSON, returning default when the file is absent."""

    json_path = Path(path)
    if not json_path.exists():
        return default
    with json_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, data: Any) -> None:
    """Write pretty UTF-8 JSON and create parent directories."""

    json_path = Path(path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(_to_jsonable(data), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        if hasattr(value, "to_dict"):
            return value.to_dict()
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value
