"""Tests for dependency-aware flow composition."""

import unittest

from context_builder.flow_composer import compose_flow


class FlowComposerTests(unittest.TestCase):
    def test_injects_dependency_steps_after_token_step(self) -> None:
        composed = compose_flow(
            main_flow=[
                "Validate credentials",
                "Return session token",
                "Show success response",
            ],
            dependent_flows=[
                {
                    "id": "TokenGeneration",
                    "steps": ["Generate session token"],
                }
            ],
        )

        self.assertEqual(
            composed,
            [
                "Validate credentials",
                "Return session token",
                "Generate session token",
                "Show success response",
            ],
        )

    def test_appends_dependencies_when_no_injection_point_exists(self) -> None:
        composed = compose_flow(
            main_flow=["Validate credentials", "Show success response"],
            dependent_flows=[{"id": "Audit", "steps": ["Record analytics event"]}],
        )

        self.assertEqual(
            composed,
            ["Validate credentials", "Show success response", "Record analytics event"],
        )

    def test_deduplicates_steps(self) -> None:
        composed = compose_flow(
            main_flow=["Return session token"],
            dependent_flows=[
                {
                    "id": "TokenGeneration",
                    "steps": ["Return session token", "Generate session token"],
                }
            ],
        )

        self.assertEqual(
            composed,
            ["Return session token", "Generate session token"],
        )

    def test_limits_nested_dependency_depth(self) -> None:
        composed = compose_flow(
            main_flow=["Return session token"],
            dependent_flows=[
                {
                    "id": "Level1",
                    "steps": ["Generate level one token"],
                    "dependent_flows": [
                        {
                            "id": "Level2",
                            "steps": ["Generate level two token"],
                            "dependent_flows": [
                                {
                                    "id": "Level3",
                                    "steps": ["Generate level three token"],
                                }
                            ],
                        }
                    ],
                }
            ],
        )

        self.assertIn("Generate level one token", composed)
        self.assertIn("Generate level two token", composed)
        self.assertNotIn("Generate level three token", composed)

    def test_prevents_circular_dependency_loops(self) -> None:
        first = {"id": "First", "steps": ["Generate first token"]}
        second = {"id": "Second", "steps": ["Generate second token"]}
        first["dependent_flows"] = [second]
        second["dependent_flows"] = [first]

        composed = compose_flow(
            main_flow=["Return session token"],
            dependent_flows=[first],
        )

        self.assertEqual(composed.count("Generate first token"), 1)
        self.assertEqual(composed.count("Generate second token"), 1)


if __name__ == "__main__":
    unittest.main()
