from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .repository_snapshot import RepositoryFile


DEFAULT_IGNORE_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    "bin",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "obj",
    "target",
}


class RepositoryScanner:
    def scan(self, repository: dict[str, Any] | str, *, max_files: int = 2000, max_file_bytes: int = 80_000) -> dict[str, Any]:
        if isinstance(repository, str):
            repository = {"path": repository, "repositoryId": Path(repository).name}
        repo_path = Path(str(repository.get("path") or repository.get("local_path") or ".")).expanduser()
        repository_id = str(repository.get("repositoryId") or repository.get("repository_id") or repository.get("id") or repo_path.name)
        files: list[RepositoryFile] = []
        warnings: list[str] = []
        if not repo_path.exists():
            return {
                "repositoryId": repository_id,
                "repositoryType": repository.get("type") or "Unknown",
                "files": [],
                "warnings": [f"Repository path not found: {repo_path}"],
                "projects": [],
                "packages": [],
                "sourceFolders": [],
                "documentation": [],
                "configuration": [],
                "buildFiles": [],
            }
        for root, dirs, filenames in os.walk(repo_path):
            dirs[:] = [item for item in dirs if item not in DEFAULT_IGNORE_DIRS and not item.startswith(".")]
            for filename in filenames:
                if len(files) >= max_files:
                    warnings.append(f"Scan stopped at max_files={max_files}.")
                    break
                path = Path(root) / filename
                relative = path.relative_to(repo_path).as_posix()
                try:
                    raw = path.read_bytes()[:max_file_bytes]
                    content = raw.decode("utf-8", errors="ignore")
                except OSError as exc:
                    warnings.append(f"Could not read {relative}: {exc}")
                    continue
                files.append(RepositoryFile(relative, content))
        paths = [item.path for item in files]
        return {
            "repositoryId": repository_id,
            "repositoryType": repository.get("type") or "Local Folder",
            "root": str(repo_path),
            "files": files,
            "warnings": warnings,
            "projects": _matching(paths, (".sln", ".csproj", ".xcodeproj", ".xcworkspace", "pom.xml", "build.gradle", "settings.gradle")),
            "packages": _matching(paths, ("package.json", "pyproject.toml", "requirements.txt", "pubspec.yaml", "Package.swift")),
            "sourceFolders": sorted({path.split("/", 1)[0] for path in paths if "/" in path and _is_source_path(path)}),
            "documentation": [path for path in paths if path.lower().endswith(".md")],
            "configuration": _matching(paths, ("appsettings.json", "Dockerfile", "docker-compose.yml", ".csproj", "package.json", "pyproject.toml")),
            "buildFiles": _matching(paths, ("package.json", ".csproj", ".sln", "pom.xml", "build.gradle", "Makefile", "webpack.config.js")),
        }


def _matching(paths: list[str], suffixes: tuple[str, ...]) -> list[str]:
    return [path for path in paths if path.endswith(suffixes) or Path(path).name in suffixes]


def _is_source_path(path: str) -> bool:
    lowered = path.lower()
    return any(part in lowered.split("/") for part in ["src", "source", "app", "backend", "frontend", "mobile"])
