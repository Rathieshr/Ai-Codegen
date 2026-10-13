"""Command line entry point for ai-gen."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


DEFAULT_BACKEND_URL = "http://127.0.0.1:8000/context"


def fetch_optimized_prompt(query: str, backend_url: str, max_tokens: int) -> dict:
    """Call the local backend with only standard-library dependencies."""

    payload = json.dumps({"query": query, "max_tokens": max_tokens}).encode("utf-8")
    request = urllib.request.Request(
        backend_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("Backend returned invalid JSON.") from exc
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Backend returned HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not reach ai-gen backend at {backend_url}. "
            "Start it with: python -m uvicorn backend.app:app --app-dir ai-gen --reload"
        ) from exc

    required_keys = {"optimized_prompt", "matched_logic", "token_estimate"}
    missing_keys = required_keys.difference(data)
    if missing_keys:
        missing = ", ".join(sorted(missing_keys))
        raise RuntimeError(f"Backend response is missing required field(s): {missing}")

    if not isinstance(data["optimized_prompt"], str) or not data["optimized_prompt"].strip():
        raise RuntimeError("Backend returned an empty optimized prompt.")

    return data


def run_codex(prompt: str, codex_bin: str) -> int:
    """Forward the enriched prompt to the Codex CLI."""

    try:
        completed = subprocess.run([codex_bin, prompt], check=False)
    except FileNotFoundError:
        print(
            f"Codex executable not found: {codex_bin}. "
            "Set AI_GEN_CODEX_BIN or pass --codex-bin.",
            file=sys.stderr,
        )
        return 127
    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    """Create the command parser."""

    parser = argparse.ArgumentParser(
        prog="ai-gen",
        description="Inject compact business logic context before running Codex.",
    )
    parser.add_argument("query", help="Natural language task, for example: 'Add OTP login'")
    parser.add_argument(
        "--backend-url",
        default=os.getenv("AI_GEN_BACKEND_URL", DEFAULT_BACKEND_URL),
        help=f"Context backend URL. Defaults to {DEFAULT_BACKEND_URL}.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=int(os.getenv("AI_GEN_MAX_TOKENS", "900")),
        help="Approximate token budget for generated context.",
    )
    parser.add_argument(
        "--codex-bin",
        default=os.getenv("AI_GEN_CODEX_BIN", "codex"),
        help="Codex executable to run after context generation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the optimized prompt without invoking Codex.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI coordinator: query backend, then hand the prompt to Codex."""

    args = build_parser().parse_args(argv)
    try:
        response = fetch_optimized_prompt(args.query, args.backend_url, args.max_tokens)
    except RuntimeError as exc:
        print(f"[ai-gen] {exc}", file=sys.stderr)
        return 1

    optimized_prompt = response["optimized_prompt"]

    if args.dry_run:
        print(optimized_prompt)
        print(
            f"\n[ai-gen] matched={','.join(response['matched_logic']) or 'none'} "
            f"tokens~={response['token_estimate']}",
            file=sys.stderr,
        )
        return 0

    print("[ai-gen] Context optimized. Forwarding enriched prompt to Codex...", file=sys.stderr)
    return run_codex(optimized_prompt, args.codex_bin)


if __name__ == "__main__":
    raise SystemExit(main())
