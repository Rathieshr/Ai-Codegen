"""Deterministic execution validation and scope drift checks."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExecutionContext:
    """Scope and safety context captured before execution."""

    selected_files: list[str] = field(default_factory=list)
    allowed_flows: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    likely_breakpoints: list[str] = field(default_factory=list)
    baseline_hashes: dict[str, str] = field(default_factory=dict)


@dataclass
class ExecutionValidationResult:
    """Validation result returned after execution."""

    drift_detected: bool
    drift_score: float
    out_of_scope_files: list[str]
    constraint_violations: list[str]
    risky_changes: list[str]
    summary: str


def snapshot_selected_files(repo_root: str, selected_files: list[str]) -> dict[str, str]:
    """Capture baseline hashes for selected files before execution."""

    root = Path(repo_root)
    snapshots: dict[str, str] = {}
    for file_path in selected_files:
        normalized = _norm_path(file_path)
        full_path = root / normalized
        if not full_path.is_file():
            continue
        snapshots[normalized] = _hash_file(full_path)
    return snapshots


def get_changed_files_after_execution(repo_root: str, baseline_hashes: dict[str, str] | None = None) -> list[str]:
    """Return changed files using git diff, with hash comparison fallback."""

    git_changed = _git_changed_files(repo_root)
    if git_changed:
        return git_changed

    changed: list[str] = []
    root = Path(repo_root)
    for file_path, old_hash in (baseline_hashes or {}).items():
        full_path = root / file_path
        new_hash = _hash_file(full_path) if full_path.is_file() else ""
        if new_hash != old_hash:
            changed.append(_norm_path(file_path))
    return changed


def detect_scope_drift(selected_files: list[str], changed_files: list[str]) -> dict[str, Any]:
    """Detect whether changed files escaped the selected execution scope."""

    selected = {_norm_path(path) for path in selected_files}
    changed = [_norm_path(path) for path in changed_files]
    in_scope = [path for path in changed if path in selected]
    out_of_scope = [path for path in changed if path not in selected]
    drift_score = len(out_of_scope) / max(len(changed), 1)
    return {
        "out_of_scope_files": out_of_scope,
        "in_scope_files": in_scope,
        "drift_score": round(drift_score, 2),
    }


def validate_constraints(constraints: list[str], changed_files: list[str], repo_root: str) -> list[str]:
    """Validate simple safety constraints using keyword checks on changed content."""

    violations: list[str] = []
    changed_text = "\n".join(_changed_content(repo_root, path) for path in changed_files).lower()
    if not changed_text:
        return violations

    for constraint in constraints:
        normalized = constraint.lower()
        if _is_user_existence_constraint(normalized) and any(
            phrase in changed_text
            for phrase in ("email exists", "username exists", "user exists", "account exists", "no user found")
        ):
            _append_once(violations, "Possible user-existence leak in authentication error handling.")
        if _is_session_reuse_constraint(normalized) and any(
            phrase in changed_text
            for phrase in ("jwt.encode", "create_token(", "generate_token(", "new session", "session(")
        ):
            _append_once(violations, "Possible new token/session generation path instead of reuse.")
        if _is_validation_constraint(normalized) and any(
            phrase in changed_text
            for phrase in ("skip validation", "bypass validation", "validate=false", "verify=false")
        ):
            _append_once(violations, "Possible validation bypass.")
        if _is_payment_constraint(normalized) and any(
            phrase in changed_text
            for phrase in ("payment.status = 'success'", "mark_success", "successful = true")
        ):
            _append_once(violations, "Possible payment success before verification.")
    return violations


def detect_risky_changes(changed_files: list[str]) -> list[str]:
    """Flag risky paths and broad module changes."""

    risks: list[str] = []
    normalized_files = [_norm_path(path) for path in changed_files]
    for path in normalized_files:
        lowered = path.lower()
        if any(keyword in lowered for keyword in ("auth", "login", "password")):
            _append_once(risks, f"Auth-sensitive file changed: {path}")
        if any(keyword in lowered for keyword in ("payment", "billing", "transaction", "checkout")):
            _append_once(risks, f"Payment-sensitive file changed: {path}")
        if any(keyword in lowered for keyword in ("session", "token", "jwt")):
            _append_once(risks, f"Session/token-sensitive file changed: {path}")

    modules = {Path(path).parts[0] for path in normalized_files if Path(path).parts}
    if len(modules) > 1:
        _append_once(risks, f"Changes touch multiple modules: {', '.join(sorted(modules))}")
    if len(normalized_files) > 5:
        _append_once(risks, "Large change set detected.")
    return risks


def validate_execution(
    context: ExecutionContext,
    repo_root: str,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    """Validate post-execution changes against the selected scope and constraints."""

    changed = changed_files if changed_files is not None else get_changed_files_after_execution(repo_root, context.baseline_hashes)
    drift = detect_scope_drift(context.selected_files, changed)
    violations = validate_constraints(context.constraints, changed, repo_root)
    risky = detect_risky_changes(changed)
    result = ExecutionValidationResult(
        drift_detected=bool(drift["out_of_scope_files"]),
        drift_score=drift["drift_score"],
        out_of_scope_files=drift["out_of_scope_files"],
        constraint_violations=violations,
        risky_changes=risky,
        summary=_summary(drift["out_of_scope_files"], violations, risky),
    )
    return asdict(result)


def _git_changed_files(repo_root: str) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    return [_norm_path(path) for path in completed.stdout.splitlines() if path.strip()]


def _changed_content(repo_root: str, file_path: str) -> str:
    diff = _git_added_lines(repo_root, file_path)
    if diff:
        return diff
    path = Path(repo_root) / _norm_path(file_path)
    try:
        if path.is_file() and path.stat().st_size <= 300 * 1024:
            return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return ""


def _git_added_lines(repo_root: str, file_path: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "diff", "--", _norm_path(file_path)],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    lines = []
    for line in completed.stdout.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
    return "\n".join(lines)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _is_user_existence_constraint(value: str) -> bool:
    return "reveal whether" in value or "user existence" in value or "failed authentication" in value or "generic" in value


def _is_session_reuse_constraint(value: str) -> bool:
    return "reuse" in value and ("session" in value or "token" in value)


def _is_validation_constraint(value: str) -> bool:
    return "validation" in value or "validate" in value or "verify" in value


def _is_payment_constraint(value: str) -> bool:
    return "payment" in value or "transaction" in value or "gateway" in value


def _summary(out_of_scope: list[str], violations: list[str], risky: list[str]) -> str:
    if not out_of_scope and not violations and not risky:
        return "Execution stayed within scope with no detected constraint or risk issues."
    parts: list[str] = []
    if out_of_scope:
        parts.append(f"{len(out_of_scope)} out-of-scope file(s) changed")
    if violations:
        parts.append(f"{len(violations)} possible constraint violation(s)")
    if risky:
        parts.append(f"{len(risky)} risky change signal(s)")
    return "; ".join(parts) + "."


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _norm_path(path: str) -> str:
    return path.replace("\\", "/").strip()
