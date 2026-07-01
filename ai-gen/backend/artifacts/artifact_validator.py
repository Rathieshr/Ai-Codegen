"""Shared validator for the generic artifact engine."""

from __future__ import annotations

from typing import Any


REQUIRED_COMMON_FIELDS = ["id", "type", "title", "status", "version"]


class ArtifactValidator:
    def validate_common(self, artifact: dict[str, Any]) -> dict[str, Any]:
        issues = []
        for field in REQUIRED_COMMON_FIELDS:
            if artifact.get(field) in (None, "", []):
                issues.append({"severity": "critical", "field": field, "message": f"{field} is required."})
        confidence = float(artifact.get("confidence") or 0)
        if confidence < 0.5:
            issues.append({"severity": "warning", "field": "confidence", "message": "Artifact confidence is low."})
        status = "Approved" if not any(issue["severity"] == "critical" for issue in issues) else "Rejected"
        if any(issue["severity"] == "warning" for issue in issues) and status == "Approved":
            status = "NeedsReview"
        return {
            "validationStatus": status,
            "issues": issues,
            "score": max(0, 100 - (35 * len([item for item in issues if item["severity"] == "critical"])) - (10 * len([item for item in issues if item["severity"] == "warning"]))),
        }

    def validate_with_definition(self, artifact: dict[str, Any], definition_report: dict[str, Any]) -> dict[str, Any]:
        common = self.validate_common(artifact)
        extra_issues = definition_report.get("issues") if isinstance(definition_report.get("issues"), list) else []
        issues = [*common["issues"], *extra_issues]
        status = definition_report.get("validationStatus") or common["validationStatus"]
        if any(issue.get("severity") == "critical" for issue in issues):
            status = "Rejected"
        elif any(issue.get("severity") in {"warning", "major"} for issue in issues) and status == "Approved":
            status = "NeedsReview"
        return {
            **common,
            **definition_report,
            "validationStatus": status,
            "issues": issues,
            "score": min(int(common.get("score") or 0), int(definition_report.get("score") or common.get("score") or 0)),
        }

