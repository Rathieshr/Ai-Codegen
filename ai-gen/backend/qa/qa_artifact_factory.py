"""Factory helpers for QA Intelligence artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import hashlib
import json


class QAArtifactFactory:
    def build(self, payload: dict[str, Any]) -> dict[str, Any]:
        artifact_id = "qa_" + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
        return {
            "artifactId": artifact_id,
            "artifactType": "QA Intelligence",
            "version": 1,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
