#!/usr/bin/env bash
# Tear down dev artefacts (no daemon at M0 — placeholder).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -d ".venv" ]; then
  echo "Removing .venv/"
  rm -rf .venv
fi
