#!/usr/bin/env bash
# Local mirror of .github/workflows/ci.yml.
# Run this before opening a PR — if it fails, CI will fail the same way.

set -euo pipefail
cd "$(dirname "$0")/.."

bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
red()   { printf "\033[31m%s\033[0m\n" "$*"; }

step() {
  bold ""
  bold "──▶  $1"
}

if ! command -v uv >/dev/null 2>&1; then
  red "uv is not installed. See https://docs.astral.sh/uv/ for install instructions."
  exit 1
fi

step "1/5 uv sync --all-extras --dev"
uv sync --all-extras --dev

step "2/5 ruff check ."
uv run ruff check .

step "3/5 ruff format --check ."
uv run ruff format --check .

step "4/5 schema validation"
uv run python tools/schema_check.py

step "5/5 pytest"
uv run pytest -q

bold ""
green "✓ verify.sh passed — safe to push and open a PR"
