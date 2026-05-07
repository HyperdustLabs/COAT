"""``python -m COAT_runtime_daemon`` entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="COAT-runtime-daemon")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a daemon YAML config (defaults to config/default.yaml)",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate config and exit (M0 — only this branch is implemented).",
    )
    args = parser.parse_args(argv)

    if args.check_config:
        from .config.loader import load_config

        cfg = load_config(args.config)
        sys.stdout.write(f"config OK: schema_version={cfg.runtime.schema_version}\n")
        return 0

    raise NotImplementedError("Full daemon startup arrives at M4.")


if __name__ == "__main__":
    raise SystemExit(main())
