#!/usr/bin/env bash
# Dev environment bootstrap.
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required (https://docs.astral.sh/uv/)" >&2
  exit 1
fi

uv sync --all-extras --dev
echo
echo "OK — try:  uv run pytest -q"
echo "          uv run python tools/schema_check.py"
