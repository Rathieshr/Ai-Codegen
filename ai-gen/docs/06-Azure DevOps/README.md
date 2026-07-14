# Azure DevOps Integration

Azure DevOps is an HEI experience surface and enterprise system connector.

## Responsibilities

- Load current work-item context and hierarchy.
- Route Epic, Feature, Story, Task, Bug, and Test Case workflows.
- Preview and create approved child work items with parent links.
- Select repositories and branches under Code read permission.
- Map Azure DevOps groups to HEI roles.
- Synchronize comments, approval state, and artifact references.
- Open Execution Packages in VS Code.

The extension must not implement planning, context retrieval, or package assembly independently. It calls HEI APIs and renders canonical lifecycle state.
