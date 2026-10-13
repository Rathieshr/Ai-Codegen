"""Filesystem-backed repo context storage for ai-gen."""

from backend.repo_context.manager import (
    RepoContextManager,
    load_repo_registry,
    make_repo_id,
    merge_effective_context,
    normalize_git_remote,
    register_repo_identity,
    resolve_repo_id_from_registry,
    save_repo_registry,
)
from backend.repo_context.models import BranchMeta, RepoMeta, SessionContext

__all__ = [
    "BranchMeta",
    "RepoContextManager",
    "RepoMeta",
    "SessionContext",
    "make_repo_id",
    "merge_effective_context",
    "normalize_git_remote",
    "load_repo_registry",
    "register_repo_identity",
    "resolve_repo_id_from_registry",
    "save_repo_registry",
]
