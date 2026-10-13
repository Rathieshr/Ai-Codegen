# VS Code Engineering Assistant

The HEI VS Code extension continues the engineering lifecycle inside the repository workspace.

## Primary flow

`HEI work item -> Execution Package -> Execution Manifest -> VS Code workspace -> implementation -> validation`

The main developer artifact is the Execution Manifest. Detailed Execution Package JSON, repository evidence, engineering rules, and diagnostics remain available under advanced details.

The extension may locate workspace files and collect runtime evidence, but it must not rebuild project context or invent repository paths.
