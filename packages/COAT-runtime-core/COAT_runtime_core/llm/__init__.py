"""Bundled LLM clients (currently: stub only).

Real providers (openai, anthropic, ollama, …) live in adapter packages.
The stub keeps the in-proc happy path runnable in CI without network."""

from .stub import StubLLMClient

__all__ = ["StubLLMClient"]
