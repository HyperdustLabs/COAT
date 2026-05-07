"""Intercept ``tool_call.arguments`` and apply tool_guard advice — M5."""

from __future__ import annotations


class OpenClawToolGuard:
    def guard(self, tool_call: dict, host_context: dict) -> dict:
        raise NotImplementedError
