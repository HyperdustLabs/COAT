# COAT-runtime-llm

LLM and embedder clients. M0 ships skeletons; M1 makes the `stub` client work
end-to-end and M2 adds OpenAI / Anthropic.

```text
COAT_runtime_llm/
├── base.py
├── stub_client.py        # zero-dep, deterministic responses (M1)
├── openai_client.py      # M2
├── anthropic_client.py   # M2
├── azure_openai_client.py# M2
└── ollama_client.py      # M2
```
