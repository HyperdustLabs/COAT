"""OpenCOAT Runtime storage backends.

Public re-exports are kept minimal so consumers can import the backend they
actually want without dragging in optional dependencies.

* ``opencoat_runtime_storage.memory`` — default in-process backends (M1)
* ``opencoat_runtime_storage.sqlite`` — single-process persistence (M3)
* ``opencoat_runtime_storage.postgres`` — service deployments (M8)
* ``opencoat_runtime_storage.jsonl`` — append-only replay log (M3)
* ``opencoat_runtime_storage.vector`` — optional embedding index (M2+)
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    __version__ = _version("opencoat-runtime")
except PackageNotFoundError:
    __version__ = "0.0.0"
