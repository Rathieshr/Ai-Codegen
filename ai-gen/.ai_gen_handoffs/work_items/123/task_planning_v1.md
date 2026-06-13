# TASK_PLANNING Handoff
Status: draft

## Summary
Generated proposed child work items from the approved story scope.

## Stage Output
```json
{
  "assistant": "task_planning",
  "summary": "Generated proposed child work items from the approved story scope.",
  "proposed_child_tasks": [
    {
      "type": "task",
      "title": "Implement Ai Gen Extension Test",
      "description": "Build the approved behavior for flows: otp_verification, login."
    },
    {
      "type": "ui_task",
      "title": "Design Ai Gen Extension Test",
      "description": "Define the UI behavior, fields, and states for: phone_number, otp."
    },
    {
      "type": "qa_task",
      "title": "Validate Ai Gen Extension Test",
      "description": "Prepare and execute the validation and regression checklist for the approved scope."
    }
  ],
  "proposed_work_items": [
    {
      "id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__ui_ai_gen_extension_test_focus_first_on_phone_nu_1_11ca7431db",
      "draft_id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__ui_ai_gen_extension_test_focus_first_on_phone_nu_1_11ca7431db",
      "type": "Task",
      "draft_type": "Task",
      "title": "UI Task: Ai Gen Extension Test. Focus first on phone number input, otp verification step Review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required",
      "description": "Design and implement the UI structure for ai gen extension test. focus first on phone number input, otp verification step review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required, including fields and states.",
      "acceptance_criteria": [
        "UI structure reflects the approved story scope.",
        "Fields are covered: phone_number, otp."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_ai_gen_extension_test_focus_first_on_phone_numbe_1_87c3e33c66",
      "parent_work_item_id": "123",
      "children": [],
      "child_drafts": [],
      "source_stage": "task_planning",
      "selected": true,
      "status": "draft",
      "azure_work_item_id": null,
      "creation_error": null
    },
    {
      "id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__dev_ai_gen_extension_test_focus_first_on_phone_n_2_88583ec61c",
      "draft_id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__dev_ai_gen_extension_test_focus_first_on_phone_n_2_88583ec61c",
      "type": "Task",
      "draft_type": "Task",
      "title": "Dev Task: Ai Gen Extension Test. Focus first on phone number input, otp verification step Review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required",
      "description": "Implement the approved behavior for ai gen extension test. focus first on phone number input, otp verification step review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required with minimal scope.",
      "acceptance_criteria": [
        "Implementation follows the approved execution scope.",
        "Variant behavior is respected: phone_otp."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_ai_gen_extension_test_focus_first_on_phone_numbe_1_87c3e33c66",
      "parent_work_item_id": "123",
      "children": [],
      "child_drafts": [],
      "source_stage": "task_planning",
      "selected": true,
      "status": "draft",
      "azure_work_item_id": null,
      "creation_error": null
    },
    {
      "id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__qa_ai_gen_extension_test_focus_first_on_phone_nu_3_9d3edc89f9",
      "draft_id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__qa_ai_gen_extension_test_focus_first_on_phone_nu_3_9d3edc89f9",
      "type": "Task",
      "draft_type": "Task",
      "title": "QA Task: Ai Gen Extension Test. Focus first on phone number input, otp verification step Review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required",
      "description": "Validate the delivered behavior for ai gen extension test. focus first on phone number input, otp verification step review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required and capture regression coverage.",
      "acceptance_criteria": [
        "Positive, negative, and edge validation is documented.",
        "Regression risks are covered before closure."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_ai_gen_extension_test_focus_first_on_phone_numbe_1_87c3e33c66",
      "parent_work_item_id": "123",
      "children": [],
      "child_drafts": [],
      "source_stage": "task_planning",
      "selected": true,
      "status": "draft",
      "azure_work_item_id": null,
      "creation_error": null
    },
    {
      "id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__docs_ai_gen_extension_test_focus_first_on_phone__4_1c9201c074",
      "draft_id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__docs_ai_gen_extension_test_focus_first_on_phone__4_1c9201c074",
      "type": "Task",
      "draft_type": "Task",
      "title": "Documentation Task: Ai Gen Extension Test. Focus first on phone number input, otp verification step Review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required",
      "description": "Update supporting release or support documentation for ai gen extension test. focus first on phone number input, otp verification step review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required.",
      "acceptance_criteria": [
        "Documentation reflects the delivered behavior and rollout notes."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_ai_gen_extension_test_focus_first_on_phone_numbe_1_87c3e33c66",
      "parent_work_item_id": "123",
      "children": [],
      "child_drafts": [],
      "source_stage": "task_planning",
      "selected": true,
      "status": "draft",
      "azure_work_item_id": null,
      "creation_error": null
    }
  ],
  "generated_work_items": [
    {
      "id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__ui_ai_gen_extension_test_focus_first_on_phone_nu_1_11ca7431db",
      "draft_id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__ui_ai_gen_extension_test_focus_first_on_phone_nu_1_11ca7431db",
      "type": "Task",
      "draft_type": "Task",
      "title": "UI Task: Ai Gen Extension Test. Focus first on phone number input, otp verification step Review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required",
      "description": "Design and implement the UI structure for ai gen extension test. focus first on phone number input, otp verification step review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required, including fields and states.",
      "acceptance_criteria": [
        "UI structure reflects the approved story scope.",
        "Fields are covered: phone_number, otp."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_ai_gen_extension_test_focus_first_on_phone_numbe_1_87c3e33c66",
      "parent_work_item_id": "123",
      "children": [],
      "child_drafts": [],
      "source_stage": "task_planning",
      "selected": true,
      "status": "draft",
      "azure_work_item_id": null,
      "creation_error": null
    },
    {
      "id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__dev_ai_gen_extension_test_focus_first_on_phone_n_2_88583ec61c",
      "draft_id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__dev_ai_gen_extension_test_focus_first_on_phone_n_2_88583ec61c",
      "type": "Task",
      "draft_type": "Task",
      "title": "Dev Task: Ai Gen Extension Test. Focus first on phone number input, otp verification step Review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required",
      "description": "Implement the approved behavior for ai gen extension test. focus first on phone number input, otp verification step review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required with minimal scope.",
      "acceptance_criteria": [
        "Implementation follows the approved execution scope.",
        "Variant behavior is respected: phone_otp."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_ai_gen_extension_test_focus_first_on_phone_numbe_1_87c3e33c66",
      "parent_work_item_id": "123",
      "children": [],
      "child_drafts": [],
      "source_stage": "task_planning",
      "selected": true,
      "status": "draft",
      "azure_work_item_id": null,
      "creation_error": null
    },
    {
      "id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__qa_ai_gen_extension_test_focus_first_on_phone_nu_3_9d3edc89f9",
      "draft_id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__qa_ai_gen_extension_test_focus_first_on_phone_nu_3_9d3edc89f9",
      "type": "Task",
      "draft_type": "Task",
      "title": "QA Task: Ai Gen Extension Test. Focus first on phone number input, otp verification step Review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required",
      "description": "Validate the delivered behavior for ai gen extension test. focus first on phone number input, otp verification step review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required and capture regression coverage.",
      "acceptance_criteria": [
        "Positive, negative, and edge validation is documented.",
        "Regression risks are covered before closure."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_ai_gen_extension_test_focus_first_on_phone_numbe_1_87c3e33c66",
      "parent_work_item_id": "123",
      "children": [],
      "child_drafts": [],
      "source_stage": "task_planning",
      "selected": true,
      "status": "draft",
      "azure_work_item_id": null,
      "creation_error": null
    },
    {
      "id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__docs_ai_gen_extension_test_focus_first_on_phone__4_1c9201c074",
      "draft_id": "draft_task_planning_draft_task_planning_ai_gen_extension_test_focus__docs_ai_gen_extension_test_focus_first_on_phone__4_1c9201c074",
      "type": "Task",
      "draft_type": "Task",
      "title": "Documentation Task: Ai Gen Extension Test. Focus first on phone number input, otp verification step Review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required",
      "description": "Update supporting release or support documentation for ai gen extension test. focus first on phone number input, otp verification step review clarifications: retry policy of 3 times and expiry policy of 60 seconds; second factor screen required.",
      "acceptance_criteria": [
        "Documentation reflects the delivered behavior and rollout notes."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_ai_gen_extension_test_focus_first_on_phone_numbe_1_87c3e33c66",
      "parent_work_item_id": "123",
      "children": [],
      "child_drafts": [],
      "source_stage": "task_planning",
      "selected": true,
      "status": "draft",
      "azure_work_item_id": null,
      "creation_error": null
    }
  ],
  "acceptance_criteria": [
    "Phone number input is required."
  ],
  "flows": [
    "otp_verification",
    "login"
  ],
  "unknowns": []
}
```

## Next Actions
- Review the proposed child tasks.
- Approve before copying tasks into downstream systems.

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
