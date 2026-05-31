# DEV Handoff
Status: approved

## Summary
Ai Gen Extension Test.

## Stage Output
```json
{
  "assistant": "dev",
  "constraints": [
    "Preserve validation rules for auth_required.",
    "Reuse the existing session or token lifecycle.",
    "Do not bypass credential validation.",
    "Reuse the existing token or session generation path."
  ],
  "execution_packet": "# Task\n\nAi Gen Extension Test.\n\n# Scope\nFlow:\n- login\nVariant:\n- phone_otp\nSurface:\n- ui_screen\nFields:\n- phone_number\n- otp\nValidations:\n- auth_required\nFirst-pass scope:\n- Login Unknown\n- submit\n- update field state\n\n# Focus\n- Prefer the smallest safe change.\n- Start with the UI or input handling path before widening to deeper services.\n- Preserve the existing auth and session safety rules.\n\n# Constraints\n- Preserve validation rules for auth_required.\n- Reuse the existing session or token lifecycle.\n- Do not bypass credential validation.\n- Reuse the existing token or session generation path.\n\n# Execution Rules\n\n- Do not repeat broad repo analysis unless necessary.\n- Use the provided scope, constraints, and likely breakpoints first.\n- Do not widen scope unless the listed path fails to explain the task.\n- Avoid re-planning from scratch.\n- Apply the smallest safe change.",
  "flow": "login",
  "flows": [
    "login",
    "otp_verification"
  ],
  "likely_breakpoints": [],
  "react": {
    "act": {
      "constraint_count": 4,
      "scope": [
        "Login Unknown",
        "submit",
        "update field state"
      ],
      "selected_files_count": 0
    },
    "decision": "ready_for_approval",
    "observe": {
      "breakpoints_found": 0,
      "repo_context_available": false,
      "ui_context_used": true
    },
    "reason": {
      "goal": "Turn the approved requirement into a small, safe implementation packet.",
      "known": [
        "Ai Gen Extension Test.",
        "login",
        "ui_screen"
      ],
      "missing": []
    }
  },
  "scope": [
    "Login Unknown",
    "submit",
    "update field state"
  ],
  "selected_files": [],
  "surface": "ui_screen",
  "surfaces": [
    "ui_screen"
  ],
  "task_summary": "Ai Gen Extension Test.",
  "variant": "phone_otp",
  "variants": [
    "phone_otp"
  ]
}
```

## Constraints
- Preserve validation rules for auth_required.
- Reuse the existing session or token lifecycle.
- Do not bypass credential validation.
- Reuse the existing token or session generation path.

## Next Actions
- Review the execution packet and selected scope.
- Approve before test planning.

## Refinement
```json
{
  "base_flows": [
    "login",
    "otp_verification"
  ],
  "fields": [
    "phone_number",
    "otp"
  ],
  "refinement_unknowns": [
    "Clarify OTP retry and expiry policy."
  ],
  "surfaces": [
    "ui_screen"
  ],
  "validations": [
    "auth_required"
  ],
  "variants": [
    "phone_otp"
  ]
}
```
