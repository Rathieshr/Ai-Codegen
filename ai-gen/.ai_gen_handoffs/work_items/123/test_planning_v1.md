# TEST_PLANNING Handoff
Status: draft

## Summary
4 test items prepared.

## Stage Output
```json
{
  "assistant": "test_planning",
  "test_cases": [
    {
      "title": "Otp_Verification happy path works",
      "type": "positive",
      "steps": [
        "Prepare the otp_verification entry point with valid data.",
        "Submit the primary action.",
        "Verify the expected success outcome."
      ],
      "expected": "The user completes the intended flow successfully.",
      "linked_acceptance_criteria": [
        "Phone number input is required."
      ]
    },
    {
      "title": "Otp_Verification rejects invalid input",
      "type": "negative",
      "steps": [
        "Use invalid or incomplete input.",
        "Submit the primary action.",
        "Verify the validation or failure message."
      ],
      "expected": "The change blocks invalid input without breaking the existing safety rules.",
      "linked_acceptance_criteria": [
        "Phone number input is required."
      ]
    },
    {
      "title": "Otp_Verification handles boundary values for otp",
      "type": "edge",
      "steps": [
        "Prepare otp with a boundary value or maximum allowed length.",
        "Submit the action.",
        "Verify the boundary behavior stays within the expected rules."
      ],
      "expected": "Boundary values are handled without unexpected errors or unsafe bypasses.",
      "linked_acceptance_criteria": [
        "Phone number input is required."
      ]
    },
    {
      "title": "Otp_Verification meets approved acceptance criteria",
      "type": "acceptance",
      "steps": [
        "Walk through the approved user path.",
        "Check each acceptance criterion against the observed behavior."
      ],
      "expected": "The approved behavior matches the acceptance criteria.",
      "linked_acceptance_criteria": [
        "Phone number input is required."
      ]
    }
  ],
  "coverage_notes": [
    "Review both successful and failure paths before sign-off.",
    "Include validation coverage for: phone_number, otp.",
    "Include OTP retry, expiry, and invalid-code coverage."
  ],
  "unknowns": [],
  "react": {
    "reason": {
      "known": [
        "otp_verification",
        "Phone number input is required.",
        "phone_number",
        "otp"
      ],
      "missing": [],
      "goal": "Cover the approved scope with positive, negative, edge, and acceptance tests."
    },
    "act": {
      "test_case_count": 4,
      "coverage": [
        "positive",
        "negative",
        "edge",
        "acceptance"
      ]
    },
    "observe": {
      "ui_context_used": true,
      "field_count": 2
    },
    "decision": "ready_for_approval"
  }
}
```

## Next Actions
- Review the planned validation coverage.
- Approve before downstream QA or validation work.

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
