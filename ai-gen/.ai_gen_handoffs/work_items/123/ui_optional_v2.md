# UI_OPTIONAL Handoff
Status: approved

## Summary
Design Otp_Verification Form with phone number, otp, submit, update field state, loading, error, success, and validation and error handling.

## Stage Output
```json
{
  "accessibility_notes": [
    "Provide clear labels and error text for every interactive element.",
    "Ensure field validation can be understood without relying on color alone."
  ],
  "actions": [
    "submit",
    "update field state"
  ],
  "assistant": "ui_optional",
  "fields": [
    {
      "name": "phone_number",
      "type": "text_input",
      "validation": [
        "auth_required",
        "required"
      ]
    },
    {
      "name": "otp",
      "type": "text_input",
      "validation": [
        "auth_required",
        "required"
      ]
    }
  ],
  "layout": [
    "title and helper text",
    "grouped input fields",
    "primary action row",
    "inline validation and error area"
  ],
  "platform": "unknown",
  "react": {
    "act": {
      "action_count": 2,
      "field_count": 2,
      "screen_name": "Otp_Verification Form",
      "screen_type": "form"
    },
    "decision": "ready_for_approval",
    "observe": {
      "skippable": false,
      "surface": "ui_screen",
      "variant": "phone_otp"
    },
    "reason": {
      "goal": "Turn the approved requirement into screen structure, fields, actions, and states.",
      "known": [
        "otp_verification",
        "login"
      ],
      "missing": []
    }
  },
  "screen_name": "Otp_Verification Form",
  "screen_type": "form",
  "skip_reason": "",
  "skippable": false,
  "states": [
    "default",
    "loading",
    "error",
    "success"
  ],
  "summary": "Design Otp_Verification Form with phone number, otp, submit, update field state, loading, error, success, and validation and error handling.",
  "unknowns": [],
  "user_goal": "Design Otp_Verification Form with phone number, otp, submit, update field state, loading, error, success, and validation and error handling.",
  "ux_notes": [
    "Keep the first interaction path short and obvious.",
    "Keep validation messages clear without exposing sensitive auth details.",
    "Make the phone input and verification step easy to understand before submission."
  ]
}
```

## Next Actions
- Review the optional UI planning output.
- Approve or skip the UI stage before task planning.

## Refinement
```json
{
  "actors": [],
  "base_flow": "otp_verification",
  "base_flows": [
    "otp_verification",
    "login"
  ],
  "confidence": "medium",
  "fields": [
    "phone_number",
    "otp"
  ],
  "first_pass_scope": [
    "phone number input",
    "otp verification step"
  ],
  "refinement_unknowns": [
    "Clarify OTP retry and expiry policy."
  ],
  "scope_hints": [
    "phone number input",
    "otp verification step"
  ],
  "states": [],
  "surface": "ui_screen",
  "surfaces": [
    "ui_screen"
  ],
  "unknowns": [
    "Clarify OTP retry and expiry policy."
  ],
  "validations": [
    "auth_required",
    "required"
  ],
  "variant": "phone_otp",
  "variants": [
    "phone_otp"
  ]
}
```
