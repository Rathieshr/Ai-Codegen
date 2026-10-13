"""Version and fingerprint management for reusable HEI artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class ArtifactVersionManager:
    def fingerprint(self, artifact: dict[str, Any]) -> str:
        payload = {
            key: artifact.get(key)
            for key in [
                "type",
                "parentId",
                "title",
                "description",
                "businessGoal",
                "businessValue",
                "dependencies",
                "responsibilities",
                "acceptanceThemes",
                "dna",
            ]
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def next_version(self, artifact: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
        previous_version = int((previous or {}).get("version") or artifact.get("version") or 0)
        fingerprint = self.fingerprint(artifact)
        previous_fingerprint = (previous or {}).get("fingerprint")
        changed = fingerprint != previous_fingerprint
        return {
            **artifact,
            "version": previous_version + 1 if changed else max(previous_version, 1),
            "fingerprint": fingerprint,
            "versionedAt": datetime.now(timezone.utc).isoformat(),
            "changed": changed,
        }

