"""M0 smoke tests for the host SDK skeleton."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "modname",
    [
        "opencoat_runtime_host_sdk",
        "opencoat_runtime_host_sdk.client",
        "opencoat_runtime_host_sdk.decorators",
        "opencoat_runtime_host_sdk.injection_consumer",
        "opencoat_runtime_host_sdk.joinpoint_emitter",
        "opencoat_runtime_host_sdk.transport",
        "opencoat_runtime_host_sdk.transport.inproc",
        "opencoat_runtime_host_sdk.transport.socket",
        "opencoat_runtime_host_sdk.transport.http",
    ],
)
def test_module_imports(modname: str) -> None:
    importlib.import_module(modname)


def test_joinpoint_decorator_is_passthrough_for_now() -> None:
    from opencoat_runtime_host_sdk import joinpoint

    @joinpoint("before_response", client=None, level=1)  # type: ignore[arg-type]
    def gen(ctx: dict) -> str:
        return ctx["text"]

    assert gen({"text": "hi"}) == "hi"
    assert gen.__COATr_joinpoint__ == {"name": "before_response", "level": 1}
