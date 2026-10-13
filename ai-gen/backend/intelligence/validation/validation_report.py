from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

ValidationStatus = Literal["Approved", "NeedsReview", "Rejected"]
IssueSeverity = Literal["Info", "Warning", "Error"]


@dataclass(frozen=True)
class ValidationIssue:
    severity: IssueSeverity
    category: str
    message: str
    recommendation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True)
class ValidationReport:
    validation_status: ValidationStatus
    overall_score: int
    business_alignment: int
    capability_alignment: int
    repository_alignment: int
    engineering_readiness: int
    sprint_readiness: int
    execution_readiness: int
    duplicate_risk: int
    confidence: float
    issues: list[ValidationIssue] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    validated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "validationStatus": self.validation_status,
            "overallScore": int(self.overall_score),
            "businessAlignment": int(self.business_alignment),
            "capabilityAlignment": int(self.capability_alignment),
            "repositoryAlignment": int(self.repository_alignment),
            "engineeringReadiness": int(self.engineering_readiness),
            "sprintReadiness": int(self.sprint_readiness),
            "executionReadiness": int(self.execution_readiness),
            "duplicateRisk": int(self.duplicate_risk),
            "confidence": round(float(self.confidence), 2),
            "issues": [issue.to_dict() for issue in self.issues],
            "recommendations": list(self.recommendations),
            "validatedAt": self.validated_at,
            "diagnostics": dict(self.diagnostics),
        }

