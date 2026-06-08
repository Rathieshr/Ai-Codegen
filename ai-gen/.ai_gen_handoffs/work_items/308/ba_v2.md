# BA Handoff
Status: draft

## Summary
Phone OTP login. Focus first on phone number input, otp verification step Review clarifications: OTP expires in 120 seconds. Retry allowed 3 times. Second factor screen required..

## Stage Output
```json
{
  "assistant": "ba",
  "refined_requirement": "Phone OTP login. Focus first on phone number input, otp verification step Review clarifications: OTP expires in 120 seconds. Retry allowed 3 times. Second factor screen required..",
  "actors": [
    "end_user"
  ],
  "flows": [
    "login",
    "otp_verification"
  ],
  "variant": "phone_otp",
  "variants": [
    "phone_otp"
  ],
  "business_rules": [
    "Preserve validation rules for auth_required, required.",
    "Preserve the existing authentication order and failure safety rules.",
    "Reuse the existing session or token lifecycle."
  ],
  "acceptance_criteria": [
    "Support the required fields: phone_number, otp.",
    "Enforce the expected validations: auth_required, required.",
    "Authenticate the user with phone number entry followed by OTP verification."
  ],
  "unknowns": [],
  "react": {
    "reason": {
      "known": [
        "Phone OTP login",
        "flow:login",
        "variant:phone_otp"
      ],
      "missing": [],
      "goal": "Clarify the requirement, actors, flows, and business rules before UI or development work starts."
    },
    "act": {
      "requirement": "Phone OTP login. Focus first on phone number input, otp verification step Review clarifications: OTP expires in 120 seconds. Retry allowed 3 times. Second factor screen required..",
      "actors": [
        "end_user"
      ],
      "flows": [
        "login",
        "otp_verification"
      ],
      "acceptance_criteria_count": 3
    },
    "observe": {
      "used_refinement": true,
      "tags": [],
      "surface": "ui_screen"
    },
    "decision": "ready_for_approval"
  }
}
```

## Constraints
- Preserve validation rules for auth_required, required.
- Preserve the existing authentication order and failure safety rules.
- Reuse the existing session or token lifecycle.

## Next Actions
- Review the clarified requirement.
- Approve BA output before UI or dev work.

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
  "surfaces": [
    "ui_screen"
  ],
  "validations": [
    "auth_required",
    "required"
  ],
  "variants": [
    "phone_otp"
  ],
  "scope_hints": [
    "phone number input",
    "otp verification step"
  ],
  "states": [],
  "first_pass_scope": [
    "phone number input",
    "otp verification step"
  ],
  "actors": [
    "end_user"
  ],
  "unknowns": [
    "Clarify OTP retry and expiry policy."
  ],
  "base_flow": "login",
  "variant": "phone_otp",
  "surface": "ui_screen",
  "confidence": "medium"
}
```
