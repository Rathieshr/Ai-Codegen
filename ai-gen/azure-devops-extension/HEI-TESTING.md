# HEI Azure DevOps Extension

HEI is packaged as a separate Azure DevOps extension so it can be installed and tested beside the legacy AI Gen extensions.

## Identity

- Display name: `HEI`
- Extension ID: `hei-engineering-platform`
- Contribution ID: `hei.project-intelligence-tab`
- Publisher: `AiIntelliCodegen`
- Current version: `0.2.9`

The legacy manifests remain unchanged. Azure DevOps therefore treats HEI as a new installation with independent enablement and extension data.

## Package

```bash
npm run package:hei
```

This creates `AiIntelliCodegen.hei-engineering-platform-0.2.9.vsix` in the extension directory.

Upload that VSIX as a private extension and share it only with the test Azure DevOps organization. Azure DevOps project navigation displays one `HEI` entry. The existing work-item page and `Open in HEI` action remain available.

## Versioning

Increment the version in `azure-devops-extension.hei.json` before packaging an update. Keep the extension and contribution IDs unchanged so HEI test installations upgrade in place.
