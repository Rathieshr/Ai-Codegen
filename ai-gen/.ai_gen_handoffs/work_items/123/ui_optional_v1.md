# UI_OPTIONAL Handoff
Status: draft

## Summary
Design login UI with phone number entry, OTP request, OTP verification state, validation and error handling.

## Stage Output
```json
{
  "assistant": "ui_optional",
  "screen_name": "Login Unknown",
  "screen_type": "unknown",
  "platform": "unknown",
  "user_goal": "Design login UI with phone number entry, OTP request, OTP verification state, validation and error handling.",
  "summary": "Design login UI with phone number entry, OTP request, OTP verification state, validation and error handling.",
  "layout": [
    "primary content",
    "supporting actions"
  ],
  "fields": [
    {
      "name": "phone_number",
      "type": "text_input",
      "validation": [
        "auth_required"
      ]
    },
    {
      "name": "otp",
      "type": "text_input",
      "validation": [
        "auth_required"
      ]
    }
  ],
  "actions": [
    "submit",
    "update field state",
    "show validation errors"
  ],
  "states": [
    "default",
    "loading",
    "error",
    "success"
  ],
  "ux_notes": [
    "Keep the first interaction path short and obvious.",
    "Keep validation messages clear without exposing sensitive auth details.",
    "Make the phone input and verification step easy to understand before submission."
  ],
  "accessibility_notes": [
    "Provide clear labels and error text for every interactive element.",
    "Ensure field validation can be understood without relying on color alone."
  ],
  "unknowns": [],
  "skippable": false,
  "skip_reason": "",
  "react": {
    "reason": {
      "known": [
        "login",
        "otp_verification"
      ],
      "missing": [],
      "goal": "Turn the approved requirement into screen structure, fields, actions, and states."
    },
    "act": {
      "screen_name": "Login Unknown",
      "screen_type": "unknown",
      "field_count": 2,
      "action_count": 3
    },
    "observe": {
      "surface": "ui_screen",
      "variant": "phone_otp",
      "skippable": false
    },
    "decision": "ready_for_approval"
  }
}
```

## Next Actions
- Review the optional UI planning output.
- Approve or skip the UI stage before task planning.

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
