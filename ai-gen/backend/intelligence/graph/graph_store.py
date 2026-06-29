from __future__ import annotations

import json
import os
from pathlib import Path

from .engineering_graph import EngineeringGraph


class GraphStore:
    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            data_dir = Path(os.getenv("AI_GEN_DATA_DIR", str(Path(__file__).parents[3] / "data")))
            path = data_dir / "project_intelligence" / "engineering_graph.json"
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> EngineeringGraph:
        if not self.path.exists():
            return EngineeringGraph()
        return EngineeringGraph.from_dict(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self, graph: EngineeringGraph) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(graph.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return {
            "path": str(self.path),
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
        }
