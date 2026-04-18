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
