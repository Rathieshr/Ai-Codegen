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
    "login"
  ],
  "variant": "phone_otp",
  "variants": [
    "phone_otp"
  ],
  "business_rules": [
    "Preserve the existing authentication order and failure safety rules.",
    "Reuse the existing session or token lifecycle."
  ],
  "acceptance_criteria": [
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
      "requirement": "Phone OTP login.",
      "actors": [
        "end_user"
      ],
      "flows": [
        "login"
      ],
      "acceptance_criteria_count": 1
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
- Preserve the existing authentication order and failure safety rules.
- Reuse the existing session or token lifecycle.

## Next Actions
- Review the clarified requirement.
- Approve BA output before UI or dev work.

## Refinement
```json
{
  "base_flows": [
    "login"
  ],
  "variants": [
    "phone_otp"
  ]
}
```
