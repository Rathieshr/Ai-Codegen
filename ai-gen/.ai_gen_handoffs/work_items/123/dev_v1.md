# DEV Handoff
Status: draft

## Summary
Ai Gen Extension Test.

## Stage Output
```json
{
  "assistant": "dev",
  "task_summary": "Ai Gen Extension Test.",
  "flow": "login",
  "variant": "phone_otp",
  "surface": "ui_screen",
  "flows": [
    "login",
    "otp_verification"
  ],
  "variants": [
    "phone_otp"
  ],
  "surfaces": [
    "ui_screen"
  ],
  "scope": [
    "Login Unknown",
    "submit",
    "update field state"
  ],
  "constraints": [
    "Preserve validation rules for auth_required.",
    "Reuse the existing session or token lifecycle.",
    "Do not bypass credential validation.",
    "Reuse the existing token or session generation path."
  ],
  "likely_breakpoints": [],
  "selected_files": [],
  "execution_packet": "# Task\n\nAi Gen Extension Test.\n\n# Scope\nFlow:\n- login\nVariant:\n- phone_otp\nSurface:\n- ui_screen\nFields:\n- phone_number\n- otp\nValidations:\n- auth_required\nFirst-pass scope:\n- Login Unknown\n- submit\n- update field state\n\n# Focus\n- Prefer the smallest safe change.\n- Start with the UI or input handling path before widening to deeper services.\n- Preserve the existing auth and session safety rules.\n\n# Constraints\n- Preserve validation rules for auth_required.\n- Reuse the existing session or token lifecycle.\n- Do not bypass credential validation.\n- Reuse the existing token or session generation path.\n\n# Execution Rules\n\n- Do not repeat broad repo analysis unless necessary.\n- Use the provided scope, constraints, and likely breakpoints first.\n- Do not widen scope unless the listed path fails to explain the task.\n- Avoid re-planning from scratch.\n- Apply the smallest safe change.",
  "react": {
    "reason": {
      "known": [
        "Ai Gen Extension Test.",
        "login",
        "ui_screen"
      ],
      "missing": [],
      "goal": "Turn the approved requirement into a small, safe implementation packet."
    },
    "act": {
      "scope": [
        "Login Unknown",
        "submit",
        "update field state"
      ],
      "selected_files_count": 0,
      "constraint_count": 4
    },
    "observe": {
      "repo_context_available": false,
      "breakpoints_found": 0,
      "ui_context_used": true
    },
    "decision": "ready_for_approval"
  }
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
