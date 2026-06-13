# BA Handoff
Status: draft

## Summary
Phone OTP login. Focus first on phone number input, otp verification step Review clarifications: OTP is required after phone entry.
Retry max is 3..

## Stage Output
```json
{
  "assistant": "ba",
  "refined_requirement": "Phone OTP login. Focus first on phone number input, otp verification step Review clarifications: OTP is required after phone entry.\nRetry max is 3..",
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
    "Preserve validation rules for required, auth_required.",
    "Preserve the existing authentication order and failure safety rules.",
    "Reuse the existing session or token lifecycle."
  ],
  "acceptance_criteria": [
    "Support the required fields: phone_number, otp.",
    "Enforce the expected validations: required, auth_required.",
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
      "requirement": "Phone OTP login. Focus first on phone number input, otp verification step Review clarifications: OTP is required after phone entry.\nRetry max is 3..",
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
      "surface": "authentication"
    },
    "decision": "ready_for_approval"
  }
}
```

## Constraints
- Preserve validation rules for required, auth_required.
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
  "variants": [
    "phone_otp"
  ],
  "surfaces": [
    "authentication"
  ],
  "first_pass_scope": [
    "phone number input",
    "otp verification step"
  ],
  "states": [],
  "fields": [
    "phone_number",
    "otp"
  ],
  "unknowns": [
    "Clarify OTP retry and expiry policy."
  ],
  "validations": [
    "required",
    "auth_required"
  ],
  "actors": [],
  "scope_hints": [
    "phone number input",
    "otp verification step"
  ],
  "base_flow": "login",
  "variant": "phone_otp",
  "surface": "authentication",
  "confidence": "medium"
}
```
