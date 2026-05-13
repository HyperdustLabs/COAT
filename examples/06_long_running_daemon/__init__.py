"""End-to-end M4 daemon example (PR-23).

Run with::

    uv run python -m examples.06_long_running_daemon.main

This package boots a real :class:`opencoat_runtime_daemon.Daemon` in-process
over HTTP JSON-RPC and drives it from the same
:class:`opencoat_runtime_cli.transport.HttpRpcClient` that ``opencoat concern``
and ``opencoat dcn`` use on the wire — so it doubles as a black-box test
that PR-17 through PR-22 actually compose.
"""
