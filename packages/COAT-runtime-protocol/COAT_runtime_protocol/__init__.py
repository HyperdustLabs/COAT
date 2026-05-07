"""COAT Runtime Protocol — JSON Schemas and pydantic envelopes.

This package is the source of truth for every cross-process / cross-language
data contract used by the COAT Runtime. JSON Schemas live under
``COAT_runtime_protocol/schemas`` and the matching pydantic models are exposed
from :mod:`COAT_runtime_protocol.envelopes`.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from . import envelopes
from .envelopes import (
    COPR,
    Advice,
    AdviceType,
    Concern,
    ConcernInjection,
    ConcernKind,
    ConcernRelationType,
    ConcernVector,
    Injection,
    JoinpointEvent,
    JoinpointSelector,
    LifecycleState,
    MetaConcern,
    Pointcut,
    WeavingLevel,
    WeavingOp,
    WeavingOperation,
    WeavingPolicy,
)
from .schema_loader import SCHEMA_FILES, load_schema, schema_dir, schemas

try:
    __version__ = _version("COAT-runtime-protocol")
except PackageNotFoundError:  # editable install before metadata exists
    __version__ = "0.0.0"

SCHEMA_VERSION = "0.1.0"

__all__ = [
    "COPR",
    "SCHEMA_FILES",
    "SCHEMA_VERSION",
    "Advice",
    "AdviceType",
    "Concern",
    "ConcernInjection",
    "ConcernKind",
    "ConcernRelationType",
    "ConcernVector",
    "Injection",
    "JoinpointEvent",
    "JoinpointSelector",
    "LifecycleState",
    "MetaConcern",
    "Pointcut",
    "WeavingLevel",
    "WeavingOp",
    "WeavingOperation",
    "WeavingPolicy",
    "envelopes",
    "load_schema",
    "schema_dir",
    "schemas",
]
