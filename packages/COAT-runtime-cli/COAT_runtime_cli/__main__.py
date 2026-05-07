"""Allow ``python -m COAT_runtime_cli``."""

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
