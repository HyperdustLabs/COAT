"""Tests for :class:`StubLLMClient`."""

from __future__ import annotations

from COAT_runtime_core.llm import StubLLMClient
from COAT_runtime_core.ports import LLMClient


class TestStubLLMClientProtocol:
    def test_satisfies_LLMClient_runtime_protocol(self) -> None:
        # Runtime ``isinstance`` against a ``runtime_checkable`` Protocol
        # only inspects method names — but that is exactly the contract
        # we care about here: hosts wire the stub via the same port as
        # the real adapters.
        assert isinstance(StubLLMClient(), LLMClient)


class TestStubLLMClientReplies:
    def test_default_completion_used_when_no_prefix_matches(self) -> None:
        client = StubLLMClient(default_completion="hello-world")
        assert client.complete("anything") == "hello-world"

    def test_first_matching_prefix_wins(self) -> None:
        client = StubLLMClient(
            replies={
                "foo": "FOO",
                "foobar": "FOOBAR",  # never reached: 'foo' matches first
            },
            default_completion="default",
        )
        assert client.complete("foobar baz") == "FOO"
        assert client.complete("xyz") == "default"

    def test_chat_returns_default_chat(self) -> None:
        client = StubLLMClient(default_chat="hi")
        assert client.chat([{"role": "user", "content": "x"}]) == "hi"

    def test_structured_returns_copy_of_default(self) -> None:
        default = {"k": 1}
        client = StubLLMClient(default_structured=default)
        out = client.structured([{"role": "user", "content": "x"}], schema={"k": "int"})
        assert out == {"k": 1}
        out["mutated"] = True
        # Mutating the returned dict must not affect the seed.
        assert client.structured([{"role": "user", "content": "x"}], schema={"k": "int"}) == {
            "k": 1
        }

    def test_score_returns_default_score(self) -> None:
        client = StubLLMClient(default_score=0.42)
        assert client.score("p", "c") == 0.42


class TestStubLLMClientCallLog:
    def test_call_log_records_method_and_kwargs(self) -> None:
        client = StubLLMClient()
        client.complete("p1", max_tokens=5)
        client.chat([{"role": "user", "content": "x"}], temperature=0.1)
        methods = [m for m, _, _ in client.calls]
        assert methods == ["complete", "chat"]
        assert client.calls[0][2]["max_tokens"] == 5
        assert client.calls[1][2]["temperature"] == 0.1

    def test_reset_clears_call_log(self) -> None:
        client = StubLLMClient()
        client.complete("p")
        client.reset()
        assert client.calls == []
