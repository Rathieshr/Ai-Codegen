# ai-gen

`ai-gen` is a small CLI + FastAPI backend that enriches a Codex prompt with compact business logic context before execution.

## Install

```bash
cd ai-gen
python3 -m pip install -r requirements.txt
python3 -m pip install --no-use-pep517 -e .
```

## Run Backend

```bash
cd ai-gen
python3 -m uvicorn backend.app:app --reload
```

## Optional Phi Refiner

ai-gen can optionally use Azure AI Foundry Phi as a backend-only refinement advisor. This is disabled by default. The backend still owns final prompt building, constraints, routing, and validation.

Local env example:

```bash
export AI_GEN_REFINER_ENABLED=1
export AI_GEN_REFINER_PROVIDER=azure_phi
export AI_GEN_REFINER_ENDPOINT="https://<your-foundry-endpoint>"
export AI_GEN_REFINER_API_KEY="<your-key>"
export AI_GEN_REFINER_MODEL="Phi-4-mini-instruct"
export AI_GEN_REFINER_API_VERSION="2024-05-01-preview"
export AI_GEN_REFINER_TIMEOUT_SECONDS=20
```

Railway setup:

- add the same `AI_GEN_REFINER_*` variables in Railway service settings
- keep the API key only in Railway/backend environment config
- do not expose the key in the VS Code extension, Azure DevOps extension, or any frontend client

## Use CLI

```bash
ai-gen "Add OTP login"
```

For a local smoke test that does not invoke Codex:

```bash
ai-gen "Add OTP login" --dry-run
```

## Test

```bash
python3 -m unittest discover -s tests -v
```

## API

```bash
curl -X POST http://127.0.0.1:8000/context \
  -H "Content-Type: application/json" \
  -d '{"query":"Add OTP login"}'
```

## What It Includes

- Mock logic extraction for login/signup/OTP work.
- Three-level context compression:
  - Level 1: business logic flow.
  - Level 2: services, dependencies, and likely files.
  - Level 3: minimal code snippets.
- Token optimization through line deduplication and a configurable word-budget approximation.
- MVP execution routing metadata:
  - `local` and `cloud` are routing-ready only.
  - `codex` is the only active execution path today.
  - `preview_only` means the prompt should be reviewed or copied without execution.
