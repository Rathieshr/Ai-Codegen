# BA Handoff
Status: approved

## Summary
Phone OTP login.

## Stage Output
```json
{
  "acceptance_criteria": [
    "Support the required fields: phone_number, otp.",
    "Authenticate the user with phone number entry followed by OTP verification."
  ],
  "actors": [
    "end_user"
  ],
  "assistant": "ba",
  "business_rules": [
    "Preserve the existing authentication order and failure safety rules.",
    "Reuse the existing session or token lifecycle."
  ],
  "flows": [
    "login",
    "otp_verification"
  ],
  "react": {
    "act": {
      "acceptance_criteria_count": 2,
      "actors": [
        "end_user"
      ],
      "flows": [
        "login",
        "otp_verification"
      ],
      "requirement": "Phone OTP login."
    },
    "decision": "ready_for_approval",
    "observe": {
      "surface": null,
      "tags": [],
      "used_refinement": true
    },
    "reason": {
      "goal": "Clarify the requirement, actors, flows, and business rules before UI or development work starts.",
      "known": [
        "Phone OTP login",
        "flow:login",
        "variant:phone_otp"
      ],
      "missing": [
        "Is OTP or a second-factor step required after the primary input succeeds?",
        "Clarify OTP retry and expiry policy."
      ]
    }
  },
  "refined_requirement": "Phone OTP login.",
  "unknowns": [
    "Is OTP or a second-factor step required after the primary input succeeds?",
    "Clarify OTP retry and expiry policy."
  ],
  "variant": "phone_otp",
  "variants": [
    "phone_otp"
  ]
}
```

## Constraints
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
  "variants": [
    "phone_otp"
  ]
}
```
