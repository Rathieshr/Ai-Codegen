# UI_PLAN Handoff
Status: draft

## Summary
Design Workflow Screen with primary components, submit, loading, error, success, and validation and error handling.

## Stage Output
```json
{
  "assistant": "ui_plan",
  "screen_name": "Workflow Screen",
  "screen_type": "form",
  "platform": "unknown",
  "user_goal": "Design Workflow Screen with primary components, submit, loading, error, success, and validation and error handling.",
  "summary": "Design Workflow Screen with primary components, submit, loading, error, success, and validation and error handling.",
  "layout": [
    "title and helper text",
    "primary action row",
    "inline validation and error area"
  ],
  "fields": [],
  "actions": [
    "submit"
  ],
  "states": [
    "default",
    "loading",
    "error",
    "success"
  ],
  "ux_notes": [
    "Keep the first interaction path short and obvious."
  ],
  "accessibility_notes": [
    "Provide clear labels and error text for every interactive element."
  ],
  "unknowns": [],
  "skippable": false,
  "skip_reason": "",
  "react": {
    "reason": {
      "known": [
        "workflow"
      ],
      "missing": [],
      "goal": "Turn the approved requirement into screen structure, fields, actions, and states."
    },
    "act": {
      "screen_name": "Workflow Screen",
      "screen_type": "form",
      "field_count": 0,
      "action_count": 1
    },
    "observe": {
      "surface": "unknown",
      "variant": null,
      "skippable": false
    },
    "decision": "ready_for_approval"
  }
}
```
