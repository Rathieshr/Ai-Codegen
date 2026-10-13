from __future__ import annotations


def resolve_generation_role(work_item_type: str, parent_type: str | None = None, objective: str | None = None) -> tuple[str, str]:
    normalized = (work_item_type or "").replace("User Story", "Story")
    if normalized == "Epic":
        return "ProductOwner", "Refine the Epic into controlled business outcomes without broad project context leakage."
    if normalized == "Feature":
        return "ProductManager", "Prepare feature-generation input from the parent Epic, intent, selected capabilities, and relevant knowledge only."
    if normalized == "Story":
        return "ScrumMaster", "Prepare story-generation input from the selected Feature capability, acceptance areas, personas, flows, and modules only."
    if normalized == "Task":
        if parent_type == "Task" or (objective or "").lower() == "execution":
            return "TechLead", "Prepare execution prompt context from the Task, parent Story acceptance criteria, selected modules, flows, and repository-ranked files only."
        return "SeniorDeveloper", "Prepare task-generation input from Story description, acceptance criteria, selected modules, selected flows, repository artifacts, and engineering standards only."
    return "ProductOwner", "Prepare controlled planning context."
