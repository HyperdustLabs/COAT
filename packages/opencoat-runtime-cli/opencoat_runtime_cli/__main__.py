"""Allow ``python -m opencoat_runtime_cli``."""

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
