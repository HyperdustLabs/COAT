"""Tests for :class:`OpenClawInjector` and :class:`OpenClawSpanExtractor` (M5 #29)."""

from __future__ import annotations

import copy

import pytest
from COAT_runtime_host_openclaw import (
    OpenClawAdapterConfig,
    OpenClawInjector,
    OpenClawSpanExtractor,
)
from COAT_runtime_protocol import ConcernInjection, Injection, WeavingOperation


@pytest.fixture
def injector() -> OpenClawInjector:
    return OpenClawInjector()


class TestOpenClawInjector:
    def test_insert_appends_with_newline(self, injector: OpenClawInjector) -> None:
        inj = ConcernInjection(
            turn_id="t",
            injections=[
                Injection(
                    concern_id="c-a",
                    target="runtime_prompt.output_format",
                    mode=WeavingOperation.INSERT,
                    content="Second line.",
                )
            ],
        )
        out = injector.apply(inj, {"runtime_prompt": {"output_format": "First line."}})
        assert out["runtime_prompt"]["output_format"] == "First line.\nSecond line."

    def test_insert_creates_missing_path(self, injector: OpenClawInjector) -> None:
        inj = ConcernInjection(
            turn_id="t",
            injections=[
                Injection(
                    concern_id="c-b",
                    target="runtime_prompt.verification_rules",
                    mode=WeavingOperation.INSERT,
                    content="Must pass regex.",
                )
            ],
        )
        out = injector.apply(inj, {})
        assert out["runtime_prompt"]["verification_rules"] == "Must pass regex."

    def test_replace_overwrites(self, injector: OpenClawInjector) -> None:
        inj = ConcernInjection(
            turn_id="t",
            injections=[
                Injection(
                    concern_id="c-c",
                    target="response.text",
                    mode=WeavingOperation.REPLACE,
                    content="Replacement body.",
                )
            ],
        )
        out = injector.apply(inj, {"response": {"text": "old"}})
        assert out["response"]["text"] == "Replacement body."

    def test_block_sets_content(self, injector: OpenClawInjector) -> None:
        inj = ConcernInjection(
            turn_id="t",
            injections=[
                Injection(
                    concern_id="c-d",
                    target="response.text",
                    mode=WeavingOperation.BLOCK,
                    content="[BLOCKED]",
                )
            ],
        )
        out = injector.apply(inj, {"response": {"text": "leak"}})
        assert out["response"]["text"] == "[BLOCKED]"

    def test_skips_runtime_prompt_when_config_disabled(self) -> None:
        inj = ConcernInjection(
            turn_id="t",
            injections=[
                Injection(
                    concern_id="c-e",
                    target="runtime_prompt.output_format",
                    mode=WeavingOperation.INSERT,
                    content="ignored",
                )
            ],
        )
        injector = OpenClawInjector(OpenClawAdapterConfig(inject_into_runtime_prompt=False))
        out = injector.apply(inj, {"runtime_prompt": {"output_format": "keep"}})
        assert out["runtime_prompt"]["output_format"] == "keep"

    def test_deepcopy_does_not_mutate_input(self, injector: OpenClawInjector) -> None:
        nested = {"runtime_prompt": {"output_format": "x"}}
        original = copy.deepcopy(nested)
        inj = ConcernInjection(
            turn_id="t",
            injections=[
                Injection(
                    concern_id="c-f",
                    target="runtime_prompt.output_format",
                    mode=WeavingOperation.INSERT,
                    content="y",
                )
            ],
        )
        injector.apply(inj, nested)
        assert nested == original

    def test_wire_mode_string_insert(self, injector: OpenClawInjector) -> None:
        """JSON round-trip leaves ``mode`` as plain strings — accept both."""
        inj = ConcernInjection.model_validate(
            {
                "turn_id": "t",
                "injections": [
                    {
                        "concern_id": "c-g",
                        "target": "runtime_prompt.output_format",
                        "mode": "insert",
                        "content": "appended",
                    }
                ],
            }
        )
        out = injector.apply(inj, {"runtime_prompt": {"output_format": "base"}})
        assert out["runtime_prompt"]["output_format"] == "base\nappended"


class TestOpenClawSpanExtractor:
    def test_extract_prefers_text_then_raw_then_content(self) -> None:
        ext = OpenClawSpanExtractor()
        spans = ext.extract({"id": "m-1", "text": "hello", "raw_text": "ignored"})
        assert len(spans) == 1
        assert spans[0].id == "m-1"
        assert spans[0].text == "hello"
        assert spans[0].semantic_type == "openclaw.message"

    def test_extract_uses_role_as_semantic_type(self) -> None:
        ext = OpenClawSpanExtractor()
        spans = ext.extract({"text": "hi", "role": "user"})
        assert spans[0].semantic_type == "user"

    def test_extract_returns_empty_when_no_text(self) -> None:
        ext = OpenClawSpanExtractor()
        assert ext.extract({"role": "user"}) == []

    def test_extract_generates_id_when_missing(self) -> None:
        ext = OpenClawSpanExtractor()
        spans = ext.extract({"text": "only body"})
        assert len(spans) == 1
        assert len(spans[0].id) == 36  # uuid4 hex + dashes
