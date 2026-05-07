"""Pointcut compiler — turn a :class:`Pointcut` into an executable matcher.

Compilation is opportunistic: the keyword strategy precompiles its set,
the regex strategy compiles ``re.Pattern`` once, etc. The result is a
:class:`CompiledPointcut` that can be reused across joinpoints.
"""

from __future__ import annotations

from dataclasses import dataclass

from COAT_runtime_protocol import Pointcut


@dataclass(frozen=True)
class CompiledPointcut:
    """Cached / pre-validated form of a :class:`Pointcut`."""

    source: Pointcut
    # Concrete fields are filled in by M1; for now only ``source`` is required.


class PointcutCompiler:
    def compile(self, pointcut: Pointcut) -> CompiledPointcut:
        raise NotImplementedError
