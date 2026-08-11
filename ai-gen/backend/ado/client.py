"""Azure DevOps REST API client for ai-gen backend.

Supported operations
--------------------
Work items
    - patch_work_item()        Update fields on an existing work item
    - add_work_item_comment()  Post a comment on a work item
    - get_work_item()          Fetch a work item by ID

Git / Pull Requests
    - create_pull_request()    Open a PR from a source branch to a target branch
    - get_pull_request()       Get PR state by ID
    - add_pr_comment()         Post a thread comment on a PR

Pipelines / Builds
    - trigger_pipeline()       Queue a build pipeline run
    - get_pipeline_run()       Check the status of a queued run

Authentication
--------------
Uses ``ADO_PAT`` (Personal Access Token) via Basic Auth.
Required PAT scopes:
  - Work Items (Read & Write)
  - Code (Read & Write)
  - Build (Read & Execute)

All methods raise ``AdoClientError`` on HTTP errors so callers can
catch a single well-defined exception.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("ai_gen.ado")

_DEFAULT_API_VERSION = "7.1"


class AdoClientError(Exception):
    """Raised when the ADO REST API returns a non-2xx response."""

    def __init__(self, message: str, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass
class AdoConfig:
    """ADO connection configuration, read from environment variables."""

    org_url: str = field(default_factory=lambda: os.getenv("ADO_ORG_URL", ""))
    project: str = field(default_factory=lambda: os.getenv("ADO_PROJECT", ""))
    pat: str = field(default_factory=lambda: os.getenv("ADO_PAT", ""))
    default_repo_id: str = field(default_factory=lambda: os.getenv("ADO_DEFAULT_REPO_ID", ""))
    api_version: str = field(default_factory=lambda: os.getenv("ADO_API_VERSION", _DEFAULT_API_VERSION))

    @property
    def is_configured(self) -> bool:
        return bool(self.org_url and self.project and self.pat)

    @property
    def platform_configured(self) -> bool:
        return bool(self.org_url and self.pat)

    def _base64_pat(self) -> str:
        token = base64.b64encode(f":{self.pat}".encode()).decode()
        return f"Basic {token}"

    @property
    def base_url(self) -> str:
        return self._organization_url(self.org_url)

    @property
    def project_url(self) -> str:
        return f"{self.base_url}/{urllib.parse.quote(self.project, safe='')}"

    def project_url_for(self, project: str | None = None) -> str:
        selected = project or self.project
        return f"{self.base_url}/{urllib.parse.quote(selected, safe='')}"

    @staticmethod
    def _organization_url(raw_url: str) -> str:
        """Return the Azure DevOps organization URL even if a project URL was supplied."""
        url = (raw_url or "").strip().rstrip("/")
        if not url:
            return ""
        parsed = urllib.parse.urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return url
        path_parts = [part for part in parsed.path.split("/") if part]
        if parsed.netloc.lower() == "dev.azure.com" and path_parts:
            path = f"/{path_parts[0]}"
        else:
            path = ""
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


class AdoClient:
    """Thin synchronous ADO REST client.

    Uses stdlib ``urllib`` only — no additional dependencies required.
    All public methods return parsed JSON dicts or raise ``AdoClientError``.
    """

    def __init__(self, config: AdoConfig | None = None) -> None:
        self._cfg = config or AdoConfig()
        if not self._cfg.platform_configured:
            logger.warning(
                "ai-gen ADO: ADO_ORG_URL or ADO_PAT is not set. "
                "Project-specific connector endpoints and legacy ADO automation are disabled."
            )
        elif not self._cfg.project:
            logger.info(
                "ai-gen ADO: no default ADO_PROJECT configured. "
                "Project Intelligence connector endpoints will use per-profile project mappings."
            )

    @property
    def is_configured(self) -> bool:
        return self._cfg.is_configured

    @property
    def is_platform_configured(self) -> bool:
        return self._cfg.platform_configured

    # ── Project / Repository Discovery ───────────────────────────────────────

    def list_projects(self) -> list[dict[str, Any]]:
        """List Azure DevOps projects visible to the configured PAT."""
        self._require_platform_config()
        url = f"{self._cfg.base_url}/_apis/projects?api-version={self._cfg.api_version}"
        payload = self._get(url)
        return [
            {
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "description": item.get("description", ""),
                "state": item.get("state", ""),
                "visibility": item.get("visibility", ""),
            }
            for item in payload.get("value", [])
            if item.get("id") and item.get("name")
        ]

    def list_repositories(self, project: str) -> list[dict[str, Any]]:
        """List Git repositories for a selected Azure DevOps project."""
        self._require_platform_config()
        if not project:
            raise AdoClientError("ADO project is required to list repositories.")
        url = f"{self._cfg.project_url_for(project)}/_apis/git/repositories?api-version={self._cfg.api_version}"
        payload = self._get(url)
        return [
            {
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "defaultBranch": item.get("defaultBranch", ""),
                "remoteUrl": item.get("remoteUrl", ""),
                "webUrl": item.get("webUrl", ""),
            }
            for item in payload.get("value", [])
            if item.get("id") and item.get("name")
        ]

    def list_branches(self, project: str, repo_id: str) -> list[str]:
        """List branch names for a selected Azure DevOps repository."""
        self._require_platform_config()
        if not project or not repo_id:
            raise AdoClientError("ADO project and repository_id are required to list branches.")
        url = (
            f"{self._cfg.project_url_for(project)}/_apis/git/repositories/"
            f"{urllib.parse.quote(repo_id, safe='')}/refs?filter=heads/&api-version={self._cfg.api_version}"
        )
        payload = self._get(url)
        branches: list[str] = []
        for item in payload.get("value", []):
            name = str(item.get("name", ""))
            if name.startswith("refs/heads/"):
                name = name[len("refs/heads/") :]
            if name:
                branches.append(name)
        return branches

    def get_file_content(self, project: str, repo_id: str, path: str, branch: str = "main") -> str:
        """Load a text file from an Azure DevOps Git repository."""
        self._require_platform_config()
        if not project or not repo_id:
            raise AdoClientError("ADO project and repository_id are required to load repository files.")
        normalized_path = path if path.startswith("/") else f"/{path}"
        query = urllib.parse.urlencode(
            {
                "path": normalized_path,
                "includeContent": "true",
                "resolveLfs": "true",
                "versionDescriptor.version": branch or "main",
                "versionDescriptor.versionType": "branch",
                "api-version": self._cfg.api_version,
            }
        )
        url = (
            f"{self._cfg.project_url_for(project)}/_apis/git/repositories/"
            f"{urllib.parse.quote(repo_id, safe='')}/items?{query}"
        )
        payload = self._get(url)
        return str(payload.get("content") or "")

    def list_repository_items(self, project: str, repo_id: str, branch: str = "main") -> list[dict[str, Any]]:
        """List repository folders and files recursively without downloading content."""
        self._require_platform_config()
        if not project or not repo_id:
            raise AdoClientError("ADO project and repository_id are required to list repository items.")
        discovered = {
            str(item.get("path")): item
            for item in self._list_repository_scope(project, repo_id, branch, "/")
            if item.get("path")
        }

        # Some ADO Server/proxy combinations return only the immediate children even
        # when Full recursion is requested. Expand any tree that has no returned
        # descendants so Repository Intelligence never silently becomes root-only.
        visited: set[str] = {"/"}
        while len(visited) <= 500:
            trees = sorted(
                path for path, item in discovered.items()
                if path not in visited
                and (bool(item.get("isFolder")) or str(item.get("gitObjectType") or "").casefold() == "tree")
                and not any(other != path and other.startswith(f"{path.rstrip('/')}/") for other in discovered)
            )
            if not trees:
                break
            for scope_path in trees:
                visited.add(scope_path)
                for item in self._list_repository_scope(project, repo_id, branch, scope_path):
                    path = str(item.get("path") or "")
                    if path:
                        discovered[path] = item
        return [discovered[path] for path in sorted(discovered)]

    def _list_repository_scope(
        self,
        project: str,
        repo_id: str,
        branch: str,
        scope_path: str,
    ) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode(
            {
                "scopePath": scope_path or "/",
                "recursionLevel": "Full",
                "includeContentMetadata": "true",
                "versionDescriptor.version": branch or "main",
                "versionDescriptor.versionType": "branch",
                "api-version": self._cfg.api_version,
            }
        )
        url = (
            f"{self._cfg.project_url_for(project)}/_apis/git/repositories/"
            f"{urllib.parse.quote(repo_id, safe='')}/items?{query}"
        )
        payload = self._get(url)
        return [item for item in payload.get("value", []) if isinstance(item, dict) and item.get("path")]

    # ── Work Items ────────────────────────────────────────────────────────────

    def get_work_item(self, work_item_id: int | str) -> dict[str, Any]:
        """Fetch a work item by ID."""
        url = (
            f"{self._cfg.project_url}/_apis/wit/workItems/{work_item_id}"
            f"?api-version={self._cfg.api_version}&$expand=all"
        )
        return self._get(url)

    def patch_work_item(
        self,
        work_item_id: int | str,
        fields: dict[str, str | None],
    ) -> dict[str, Any]:
        """Update one or more fields on a work item using JSON Patch.

        Example fields::

            {
                "System.State": "Active",
                "System.AssignedTo": "dev@example.com",
                "Microsoft.VSTS.Common.AcceptanceCriteria": "<html>…</html>",
            }
        """
        url = (
            f"{self._cfg.project_url}/_apis/wit/workItems/{work_item_id}"
            f"?api-version={self._cfg.api_version}"
        )
        ops = [
            {"op": "replace", "path": f"/fields/{field_name}", "value": value}
            for field_name, value in fields.items()
        ]
        return self._patch(url, ops, content_type="application/json-patch+json")

    def add_work_item_comment(
        self,
        work_item_id: int | str,
        text: str,
    ) -> dict[str, Any]:
        """Post a comment on a work item."""
        url = (
            f"{self._cfg.project_url}/_apis/wit/workItems/{work_item_id}/comments"
            f"?api-version={self._cfg.api_version}-preview.4"
        )
        return self._post(url, {"text": text})

    # ── Pull Requests ─────────────────────────────────────────────────────────

    def create_pull_request(
        self,
        repo_id: str,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str = "",
        work_item_ids: list[int] | None = None,
        auto_complete: bool = False,
        draft: bool = False,
    ) -> dict[str, Any]:
        """Open a pull request.

        Returns the PR resource dict (includes ``pullRequestId``).
        """
        if not source_branch.startswith("refs/"):
            source_branch = f"refs/heads/{source_branch}"
        if not target_branch.startswith("refs/"):
            target_branch = f"refs/heads/{target_branch}"

        url = (
            f"{self._cfg.project_url}/_apis/git/repositories/"
            f"{urllib.parse.quote(repo_id, safe='')}/"
            f"pullRequests?api-version={self._cfg.api_version}"
        )
        body: dict[str, Any] = {
            "sourceRefName": source_branch,
            "targetRefName": target_branch,
            "title": title,
            "description": description,
            "isDraft": draft,
        }
        if work_item_ids:
            body["workItemRefs"] = [{"id": str(wid)} for wid in work_item_ids]
        if auto_complete:
            body["completionOptions"] = {"mergeStrategy": "squash", "deleteSourceBranch": True}

        return self._post(url, body)

    def get_pull_request(self, repo_id: str, pr_id: int) -> dict[str, Any]:
        """Fetch PR state."""
        url = (
            f"{self._cfg.project_url}/_apis/git/repositories/"
            f"{urllib.parse.quote(repo_id, safe='')}/pullRequests/{pr_id}"
            f"?api-version={self._cfg.api_version}"
        )
        return self._get(url)

    def add_pr_comment(
        self,
        repo_id: str,
        pr_id: int,
        comment: str,
        status: str = "active",
    ) -> dict[str, Any]:
        """Post a thread comment on a PR."""
        url = (
            f"{self._cfg.project_url}/_apis/git/repositories/"
            f"{urllib.parse.quote(repo_id, safe='')}/pullRequests/{pr_id}/threads"
            f"?api-version={self._cfg.api_version}"
        )
        return self._post(url, {
            "comments": [{"parentCommentId": 0, "content": comment, "commentType": 1}],
            "status": status,
        })

    # ── Pipelines / Builds ────────────────────────────────────────────────────

    def trigger_pipeline(
        self,
        definition_id: int,
        branch: str = "main",
        variables: dict[str, str] | None = None,
        source_branch: str | None = None,
    ) -> dict[str, Any]:
        """Queue a build pipeline run.

        Returns the Build resource dict (includes ``id`` and ``status``).
        """
        url = (
            f"{self._cfg.project_url}/_apis/build/builds"
            f"?api-version={self._cfg.api_version}"
        )
        ref_name = source_branch or branch
        if not ref_name.startswith("refs/"):
            ref_name = f"refs/heads/{ref_name}"
        body: dict[str, Any] = {
            "definition": {"id": definition_id},
            "sourceBranch": ref_name,
        }
        if variables:
            body["templateParameters"] = variables
        return self._post(url, body)

    def get_pipeline_run(self, build_id: int) -> dict[str, Any]:
        """Get the status of a queued build run."""
        url = (
            f"{self._cfg.project_url}/_apis/build/builds/{build_id}"
            f"?api-version={self._cfg.api_version}"
        )
        return self._get(url)

    # ── Internal HTTP helpers ─────────────────────────────────────────────────

    def _headers(self, content_type: str = "application/json") -> dict[str, str]:
        return {
            "Authorization": self._cfg._base64_pat(),
            "Content-Type": content_type,
            "Accept": "application/json",
        }

    def _require_platform_config(self) -> None:
        if not self._cfg.platform_configured:
            raise AdoClientError("ADO_ORG_URL and ADO_PAT must be configured.")

    def _get(self, url: str) -> dict[str, Any]:
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        return self._send(req)

    def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        return self._send(req)

    def _patch(
        self,
        url: str,
        body: list[dict[str, Any]],
        content_type: str = "application/json",
    ) -> dict[str, Any]:
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            url, data=data, headers=self._headers(content_type), method="PATCH"
        )
        return self._send(req)

    def _send(self, req: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                pass
            logger.error("ADO HTTP %s — %s — body: %.400s", exc.code, req.full_url, body)
            raise AdoClientError(
                f"ADO returned HTTP {exc.code} for {req.full_url}",
                status=exc.code,
                body=body,
            ) from exc
        except urllib.error.URLError as exc:
            logger.error("ADO connection error — %s — %s", req.full_url, exc.reason)
            raise AdoClientError(
                f"Cannot reach ADO: {exc.reason}",
                status=None,
            ) from exc
