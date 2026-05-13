"""One-shot pyproject.toml bumper for the 0.1.0 PyPI release.

Applied uniformly to every package under ``packages/opencoat-runtime-*``:

* ``version`` → ``0.1.0``
* ``license`` migrates from the deprecated table form
  (``license = { text = "Apache-2.0" }``) to PEP 639 SPDX
  (``license = "Apache-2.0"``).
* ``requires-python`` left as-is (already ``>=3.11``).
* ``dependencies`` — every ``opencoat-runtime-*`` row gets a
  ``>=0.1.0,<0.2.0`` constraint (the workspace siblings stay
  resolvable via ``tool.uv.sources`` for local dev; the constraint
  only matters once the wheels are on PyPI).
* ``classifiers`` and ``keywords`` added for PyPI listing.
* ``[project.urls]`` block added (Homepage / Repository / Issues /
  Documentation / Changelog).
* ``[build-system]`` ``requires`` bumped to ``hatchling>=1.27`` —
  earliest version with native SPDX-string support per PEP 639.

Run from the repo root: ``uv run --with tomlkit python scripts/_bump_to_010.py``.

Idempotent: re-running on already-bumped files is a no-op.
This script is meant to be deleted after the 0.1.0 cut lands.
"""

from __future__ import annotations

import sys
from pathlib import Path

import tomlkit
from tomlkit.items import Array

PACKAGES_DIR = Path(__file__).resolve().parents[1] / "packages"

NEW_VERSION = "0.1.0"
PIN_RANGE = ">=0.1.0,<0.2.0"
HATCHLING_REQ = "hatchling>=1.27"

KEYWORDS = [
    "opencoat",
    "agent-runtime",
    "concerns",
    "aop",
    "joinpoint",
    "pointcut",
    "weaving",
    "dcn",
]

CLASSIFIERS = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Typing :: Typed",
]

URLS = {
    "Homepage": "https://github.com/HyperdustLabs/OpenCOAT",
    "Repository": "https://github.com/HyperdustLabs/OpenCOAT",
    "Issues": "https://github.com/HyperdustLabs/OpenCOAT/issues",
    "Documentation": "https://github.com/HyperdustLabs/OpenCOAT/tree/main/docs",
    "Changelog": "https://github.com/HyperdustLabs/OpenCOAT/releases",
}


def _multiline_array(values: list[str]) -> Array:
    arr = tomlkit.array()
    arr.multiline(True)
    for v in values:
        arr.append(v)
    return arr


def bump(path: Path) -> bool:
    text = path.read_text()
    doc = tomlkit.parse(text)

    project = doc["project"]

    # 1. version
    project["version"] = NEW_VERSION

    # 2. license → SPDX string
    project["license"] = "Apache-2.0"

    # 3. dependencies — pin opencoat-runtime-* siblings
    deps = project.get("dependencies")
    if deps is not None:
        new_deps: list[str] = []
        for dep in deps:
            s = str(dep).strip()
            if (
                s.startswith("opencoat-runtime-")
                and "==" not in s
                and ">=" not in s
                and "<" not in s
            ):
                new_deps.append(f"{s}{PIN_RANGE}")
            else:
                new_deps.append(s)
        project["dependencies"] = _multiline_array(new_deps)

    # 4. classifiers + keywords (idempotent: overwrite if present)
    project["keywords"] = _multiline_array(KEYWORDS)
    project["classifiers"] = _multiline_array(CLASSIFIERS)

    # 5. [project.urls]
    urls_tbl = tomlkit.table()
    for k, v in URLS.items():
        urls_tbl[k] = v
    project["urls"] = urls_tbl

    # 6. build-system requires hatchling>=1.27
    bs = doc.get("build-system")
    if bs is not None and "requires" in bs:
        new_reqs: list[str] = []
        for r in bs["requires"]:
            s = str(r).strip()
            if s.startswith("hatchling"):
                new_reqs.append(HATCHLING_REQ)
            else:
                new_reqs.append(s)
        bs["requires"] = _multiline_array(new_reqs)

    new_text = tomlkit.dumps(doc)
    if new_text == text:
        return False
    path.write_text(new_text)
    return True


def main() -> int:
    pyprojects = sorted(PACKAGES_DIR.glob("*/pyproject.toml"))
    if not pyprojects:
        print("no packages found under", PACKAGES_DIR, file=sys.stderr)
        return 1
    changed = 0
    for p in pyprojects:
        if bump(p):
            print(f"bumped: {p.relative_to(PACKAGES_DIR.parent)}")
            changed += 1
        else:
            print(f"unchanged: {p.relative_to(PACKAGES_DIR.parent)}")
    print(f"\n{changed}/{len(pyprojects)} files updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
