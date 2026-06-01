# DEV_PACKET Handoff
Status: draft

## Summary
Implement resend cooldown.

## Stage Output
```json
{
  "assistant": "dev_packet",
  "task_summary": "Implement resend cooldown.",
  "flow": "workflow",
  "variant": null,
  "surface": null,
  "flows": [
    "workflow"
  ],
  "variants": [],
  "surfaces": [],
  "scope": [
    "Capture the approved behavior in implementation-ready acceptance criteria."
  ],
  "constraints": [
    "Preserve the approved workflow and safety rules."
  ],
  "likely_breakpoints": [],
  "selected_files": [],
  "execution_packet": "# Task\n\nImplement resend cooldown.\n\n# Scope\nFlow:\n- workflow\nFirst-pass scope:\n- Capture the approved behavior in implementation-ready acceptance criteria.\n\n# Focus\n- Prefer the smallest safe change.\n\n# Constraints\n- Preserve the approved workflow and safety rules.\n\n# Execution Rules\n\n- Do not repeat broad repo analysis unless necessary.\n- Use the provided scope, constraints, and likely breakpoints first.\n- Do not widen scope unless the listed path fails to explain the task.\n- Avoid re-planning from scratch.\n- Apply the smallest safe change.",
  "react": {
    "reason": {
      "known": [
        "Implement resend cooldown.",
        "workflow"
      ],
      "missing": [],
      "goal": "Turn the approved requirement into a small, safe implementation packet."
    },
    "act": {
      "scope": [
        "Capture the approved behavior in implementation-ready acceptance criteria."
      ],
      "selected_files_count": 0,
      "constraint_count": 1
    },
    "observe": {
      "repo_context_available": false,
      "breakpoints_found": 0,
      "ui_context_used": false
    },
    "decision": "ready_for_approval"
  }
}
```

## Constraints
- Preserve the approved workflow and safety rules.

## Next Actions
- Review the execution packet.
- Approve before handing work to implementation.
