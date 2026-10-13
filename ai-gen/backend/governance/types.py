"""Shared models and normalization helpers for Engineering Governance."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean(value: Any) -> str:
    return str(value or "").strip()


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def default_policy_config() -> dict[str, Any]:
    return {
        "planning": {
            "story_requires_approval_before_execution": True,
            "task_required_for_high_risk_work": True,
            "direct_story_execution_allowed": True,
        },
        "execution": {
            "execution_package_required": True,
            "prompt_requires_approved_artifact": True,
            "repository_confidence_threshold": 70,
        },
        "qa": {
            "acceptance_coverage_threshold": 80,
            "allowed_regression_risk": "Medium",
            "required_tests_present": True,
        },
        "release": {
            "qa_ready_required": True,
            "validation_passed_required": True,
            "pr_review_completed_required": True,
        },
    }


def normalize_policy(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": clean(policy.get("id")) or f"policy_{uuid4().hex[:12]}",
        "name": clean(policy.get("name")) or "Engineering Policy",
        "area": clean(policy.get("area")) or "Planning",
        "description": clean(policy.get("description")) or "Enterprise engineering policy.",
        "enabled": bool(policy.get("enabled", True)),
        "severity": clean(policy.get("severity")) or "High",
        "rules": policy.get("rules") if isinstance(policy.get("rules"), dict) else {},
        "createdAt": clean(policy.get("createdAt")) or now_iso(),
        "updatedAt": clean(policy.get("updatedAt")) or now_iso(),
    }


def normalize_approval(approval: dict[str, Any]) -> dict[str, Any]:
    status = clean(approval.get("status")) or "Pending"
    return {
        "id": clean(approval.get("id")) or f"approval_{uuid4().hex[:12]}",
        "artifactType": clean(approval.get("artifactType")) or "Artifact",
        "artifactId": clean(approval.get("artifactId")) or clean(approval.get("artifact_id")),
        "artifactTitle": clean(approval.get("artifactTitle")) or clean(approval.get("title")) or "Engineering Artifact",
        "status": status if status in {"Pending", "Approved", "Rejected", "Expired"} else "Pending",
        "requestedBy": clean(approval.get("requestedBy")) or "system",
        "approvedBy": clean(approval.get("approvedBy")),
        "reason": clean(approval.get("reason")),
        "expiresAt": clean(approval.get("expiresAt")),
        "createdAt": clean(approval.get("createdAt")) or now_iso(),
        "updatedAt": clean(approval.get("updatedAt")) or now_iso(),
    }


def normalize_feedback(feedback: dict[str, Any]) -> dict[str, Any]:
    rating = clean(feedback.get("rating")) or "neutral"
    return {
        "id": clean(feedback.get("id")) or f"feedback_{uuid4().hex[:12]}",
        "artifactType": clean(feedback.get("artifactType")) or "Artifact",
        "artifactId": clean(feedback.get("artifactId")),
        "category": clean(feedback.get("category")) or "General",
        "rating": rating if rating in {"thumbs_up", "thumbs_down", "neutral"} else "neutral",
        "comment": clean(feedback.get("comment")),
        "reason": clean(feedback.get("reason")),
        "createdBy": clean(feedback.get("createdBy")) or "user",
        "createdAt": clean(feedback.get("createdAt")) or now_iso(),
    }


def normalize_observation(observation: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": clean(observation.get("id")) or f"obs_{uuid4().hex[:12]}",
        "engine": clean(observation.get("engine")) or "Unknown Engine",
        "operation": clean(observation.get("operation")) or "unknown_operation",
        "status": clean(observation.get("status")) or "success",
        "durationMs": int(number(observation.get("durationMs") or observation.get("latencyMs"), 0)),
        "provider": clean(observation.get("provider")),
        "model": clean(observation.get("model")),
        "tokenUsage": observation.get("tokenUsage") if isinstance(observation.get("tokenUsage"), dict) else {},
        "failure": clean(observation.get("failure")),
        "retries": int(number(observation.get("retries"), 0)),
        "fallbacks": int(number(observation.get("fallbacks"), 0)),
        "memoryRetrieval": observation.get("memoryRetrieval") if isinstance(observation.get("memoryRetrieval"), dict) else {},
        "repositoryRetrieval": observation.get("repositoryRetrieval") if isinstance(observation.get("repositoryRetrieval"), dict) else {},
        "graphRetrieval": observation.get("graphRetrieval") if isinstance(observation.get("graphRetrieval"), dict) else {},
        "createdAt": clean(observation.get("createdAt")) or now_iso(),
    }


def normalize_audit_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": clean(event.get("id")) or f"audit_{uuid4().hex[:12]}",
        "who": clean(event.get("who")) or clean(event.get("actor")) or "system",
        "what": clean(event.get("what")) or "Governance event",
        "when": clean(event.get("when")) or now_iso(),
        "why": clean(event.get("why")) or clean(event.get("reason")),
        "artifactType": clean(event.get("artifactType")),
        "artifactId": clean(event.get("artifactId")),
        "eventType": clean(event.get("eventType")) or "Audit",
        "metadata": event.get("metadata") if isinstance(event.get("metadata"), dict) else {},
    }
