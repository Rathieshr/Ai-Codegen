"""Workflow-specific state machines for template-driven UX."""

from __future__ import annotations

from .base_state_machine import BaseWorkflowStateMachine, WorkflowSnapshot
from .bug_state_machine import BugStateMachine
from .epic_state_machine import EpicStateMachine
from .feature_state_machine import FeatureStateMachine
from .qa_task_state_machine import QaTaskStateMachine
from .spike_state_machine import SpikeStateMachine
from .story_state_machine import StoryStateMachine
from .task_state_machine import TaskStateMachine
from .ui_task_state_machine import UiTaskStateMachine


STATE_MACHINES = {
    "epic_planning": EpicStateMachine,
    "feature_planning": FeatureStateMachine,
    "story_delivery": StoryStateMachine,
    "task_execution": TaskStateMachine,
    "bug_fix": BugStateMachine,
    "qa_task": QaTaskStateMachine,
    "ui_task": UiTaskStateMachine,
    "spike": SpikeStateMachine,
}


def get_state_machine(workflow_template: str, snapshot: WorkflowSnapshot) -> BaseWorkflowStateMachine:
    machine_type = STATE_MACHINES.get(workflow_template, BaseWorkflowStateMachine)
    return machine_type(snapshot)
