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
      "title": "Implement Phone OTP login",
      "description": "Build the approved behavior for flows: login, otp_verification."
    },
    {
      "type": "ui_task",
      "title": "Design Phone OTP login",
      "description": "Define the UI behavior, fields, and states for: phone_number, otp."
    },
    {
      "type": "qa_task",
      "title": "Validate Phone OTP login",
      "description": "Prepare and execute the validation and regression checklist for the approved scope."
    }
  ],
  "proposed_work_items": [
    {
      "id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_ui_phone_otp_login_1_4597e64155",
      "draft_id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_ui_phone_otp_login_1_4597e64155",
      "type": "Task",
      "draft_type": "Task",
      "title": "UI Task: Phone OTP login",
      "description": "Design and implement the UI structure for phone otp login, including fields and states.",
      "acceptance_criteria": [
        "UI structure reflects the approved story scope.",
        "Fields are covered: phone_number, otp."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_phone_otp_login_1_cf37513cc4",
      "parent_work_item_id": "106",
      "children": [],
      "child_drafts": [],
      "source_stage": "task_planning",
      "selected": true,
      "status": "draft",
      "azure_work_item_id": null,
      "creation_error": null
    },
    {
      "id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_dev_phone_otp_login_2_10fc857116",
      "draft_id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_dev_phone_otp_login_2_10fc857116",
      "type": "Task",
      "draft_type": "Task",
      "title": "Dev Task: Phone OTP login",
      "description": "Implement the approved behavior for phone otp login with minimal scope.",
      "acceptance_criteria": [
        "Implementation follows the approved execution scope.",
        "Variant behavior is respected: phone_otp."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_phone_otp_login_1_cf37513cc4",
      "parent_work_item_id": "106",
      "children": [],
      "child_drafts": [],
      "source_stage": "task_planning",
      "selected": true,
      "status": "draft",
      "azure_work_item_id": null,
      "creation_error": null
    },
    {
      "id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_qa_phone_otp_login_3_948f8c6ccd",
      "draft_id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_qa_phone_otp_login_3_948f8c6ccd",
      "type": "Task",
      "draft_type": "Task",
      "title": "QA Task: Phone OTP login",
      "description": "Validate the delivered behavior for phone otp login and capture regression coverage.",
      "acceptance_criteria": [
        "Positive, negative, and edge validation is documented.",
        "Regression risks are covered before closure."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_phone_otp_login_1_cf37513cc4",
      "parent_work_item_id": "106",
      "children": [],
      "child_drafts": [],
      "source_stage": "task_planning",
      "selected": true,
      "status": "draft",
      "azure_work_item_id": null,
      "creation_error": null
    },
    {
      "id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_docs_phone_otp_login_4_e2f7c33090",
      "draft_id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_docs_phone_otp_login_4_e2f7c33090",
      "type": "Task",
      "draft_type": "Task",
      "title": "Documentation Task: Phone OTP login",
      "description": "Update supporting release or support documentation for phone otp login.",
      "acceptance_criteria": [
        "Documentation reflects the delivered behavior and rollout notes."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_phone_otp_login_1_cf37513cc4",
      "parent_work_item_id": "106",
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
      "id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_ui_phone_otp_login_1_4597e64155",
      "draft_id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_ui_phone_otp_login_1_4597e64155",
      "type": "Task",
      "draft_type": "Task",
      "title": "UI Task: Phone OTP login",
      "description": "Design and implement the UI structure for phone otp login, including fields and states.",
      "acceptance_criteria": [
        "UI structure reflects the approved story scope.",
        "Fields are covered: phone_number, otp."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_phone_otp_login_1_cf37513cc4",
      "parent_work_item_id": "106",
      "children": [],
      "child_drafts": [],
      "source_stage": "task_planning",
      "selected": true,
      "status": "draft",
      "azure_work_item_id": null,
      "creation_error": null
    },
    {
      "id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_dev_phone_otp_login_2_10fc857116",
      "draft_id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_dev_phone_otp_login_2_10fc857116",
      "type": "Task",
      "draft_type": "Task",
      "title": "Dev Task: Phone OTP login",
      "description": "Implement the approved behavior for phone otp login with minimal scope.",
      "acceptance_criteria": [
        "Implementation follows the approved execution scope.",
        "Variant behavior is respected: phone_otp."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_phone_otp_login_1_cf37513cc4",
      "parent_work_item_id": "106",
      "children": [],
      "child_drafts": [],
      "source_stage": "task_planning",
      "selected": true,
      "status": "draft",
      "azure_work_item_id": null,
      "creation_error": null
    },
    {
      "id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_qa_phone_otp_login_3_948f8c6ccd",
      "draft_id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_qa_phone_otp_login_3_948f8c6ccd",
      "type": "Task",
      "draft_type": "Task",
      "title": "QA Task: Phone OTP login",
      "description": "Validate the delivered behavior for phone otp login and capture regression coverage.",
      "acceptance_criteria": [
        "Positive, negative, and edge validation is documented.",
        "Regression risks are covered before closure."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_phone_otp_login_1_cf37513cc4",
      "parent_work_item_id": "106",
      "children": [],
      "child_drafts": [],
      "source_stage": "task_planning",
      "selected": true,
      "status": "draft",
      "azure_work_item_id": null,
      "creation_error": null
    },
    {
      "id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_docs_phone_otp_login_4_e2f7c33090",
      "draft_id": "draft_task_planning_draft_task_planning_phone_otp_login_1_cf37513cc4_docs_phone_otp_login_4_e2f7c33090",
      "type": "Task",
      "draft_type": "Task",
      "title": "Documentation Task: Phone OTP login",
      "description": "Update supporting release or support documentation for phone otp login.",
      "acceptance_criteria": [
        "Documentation reflects the delivered behavior and rollout notes."
      ],
      "tags": [],
      "area_path": "",
      "iteration_path": "",
      "parent_draft_id": "draft_task_planning_phone_otp_login_1_cf37513cc4",
      "parent_work_item_id": "106",
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
    "Support the required fields: phone_number, otp.",
    "Authenticate the user with phone number entry followed by OTP verification."
  ],
  "flows": [
    "login",
    "otp_verification"
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
