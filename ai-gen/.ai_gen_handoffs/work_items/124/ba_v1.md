# BA Handoff
Status: draft

## Summary
Phone OTP login.

## Stage Output
```json
{
  "assistant": "ba",
  "refined_requirement": "Phone OTP login.",
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
    "Preserve validation rules for auth_required.",
    "Preserve the existing authentication order and failure safety rules.",
    "Reuse the existing session or token lifecycle."
  ],
  "acceptance_criteria": [
    "Support the required fields: phone_number, otp.",
    "Enforce the expected validations: auth_required.",
    "Authenticate the user with phone number entry followed by OTP verification."
  ],
  "unknowns": [
    "Is OTP or a second-factor step required after the primary input succeeds?",
    "Clarify OTP retry and expiry policy."
  ],
  "react": {
    "reason": {
      "known": [
        "Phone OTP login",
        "flow:login",
        "variant:phone_otp"
      ],
      "missing": [
        "Is OTP or a second-factor step required after the primary input succeeds?",
        "Clarify OTP retry and expiry policy."
      ],
      "goal": "Clarify the requirement, actors, flows, and business rules before UI or development work starts."
    },
    "act": {
      "requirement": "Phone OTP login.",
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
      "surface": null
    },
    "decision": "ready_for_approval"
  }
}
```

## Constraints
- Preserve validation rules for auth_required.
- Preserve the existing authentication order and failure safety rules.
- Reuse the existing session or token lifecycle.

## Open Questions
- Is OTP or a second-factor step required after the primary input succeeds?
- Clarify OTP retry and expiry policy.

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
    "auth_required"
  ],
  "variants": [
    "phone_otp"
  ]
}
```
