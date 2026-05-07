#!/usr/bin/env python
"""Codegen entrypoint — JSON Schema → pydantic.

M0 only documents the intent. The actual generator (using
``datamodel-code-generator`` or a small custom emitter) lands at M1
once the schemas are stable.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("codegen not implemented yet — see milestone M1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
