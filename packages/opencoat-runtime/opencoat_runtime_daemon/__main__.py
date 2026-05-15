"""``python -m opencoat_runtime_daemon`` entrypoint (M0 skeleton + M4 PR-20 run)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opencoat-daemon")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a daemon YAML config (defaults to config/default.yaml)",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate config and exit.",
    )
    parser.add_argument(
        "--pid-file",
        type=Path,
        default=None,
        help="Path to a PID file; refuses to start if a live daemon already owns it.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level (default: INFO).",
    )
    args = parser.parse_args(argv)

    from .config.loader import load_config, merge_user_llm_env_file, resolve_daemon_config_path

    # So detached ``runtime up`` picks up ``opencoat configure llm`` keys
    # without requiring a manual ``source ~/.opencoat/opencoat.env``.
    merge_user_llm_env_file()

    cfg = load_config(resolve_daemon_config_path(args.config))

    if args.check_config:
        sys.stdout.write(f"config OK: schema_version={cfg.runtime.schema_version}\n")
        return 0

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    from .daemon import Daemon

    daemon = Daemon(cfg, pid_file=args.pid_file)
    daemon.run_until_signal()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
