from __future__ import annotations

import json
from typing import Any


def estimate_tokens(payload: dict[str, Any]) -> int:
    text = json.dumps(payload, default=str, sort_keys=True)
    return max(1, int(len(text) / 4) + 1)
