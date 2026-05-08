# COAT-runtime-llm

LLM and embedder clients implementing the `LLMClient` port from
`COAT-runtime-core`. The runtime never calls a provider directly —
every adapter lives here, behind the same protocol so hosts can swap
providers without changing turn-loop code.

```text
COAT_runtime_llm/
├── base.py                  # BaseLLMClient (Abstract)
├── stub_client.py           # re-export of COAT_runtime_core.llm.StubLLMClient
├── openai_client.py         # ✅ M2 PR-1 — OpenAI + OpenAI-compatible gateways
├── anthropic_client.py      # M2 (planned)
├── azure_openai_client.py   # M2 (planned)
└── ollama_client.py         # M2 (planned)
```

## Install

The OpenAI extra installs the upstream SDK:

```bash
pip install "COAT-runtime-llm[openai]"
```

In the workspace dev environment (`uv sync --all-extras --dev`) the
SDK is pulled in as a dev dependency so CI can exercise the adapter
under mocks.

## Use

```python
from COAT_runtime_llm import OpenAILLMClient

llm = OpenAILLMClient(
    model="gpt-4o-mini",          # default
    api_key=None,                 # falls back to OPENAI_API_KEY env var
    base_url=None,                # set for Azure / vLLM / OpenRouter etc.
    timeout_seconds=20.0,
    default_temperature=0.0,      # deterministic by default
)

print(llm.complete("Say hi in one word."))
```

The same client works against any OpenAI-compatible HTTP gateway —
just override `base_url`. Native Azure OpenAI deployments will land
as a thin subclass in a follow-up PR (`AzureOpenAILLMClient`).

## Stub client for tests

The deterministic in-process stub used by the M1 example and the
test suite lives in `COAT_runtime_core.llm.StubLLMClient` and is
re-exported here for backwards compatibility:

```python
from COAT_runtime_llm import StubLLMClient
```

The stub has no upstream-SDK dependency — it ships in the core
runtime so the in-proc happy path stays runnable without any of the
provider extras installed.

## Errors

`OpenAIClientError` is raised for fatal misconfiguration:

* `OPENAI_API_KEY` not set and no `api_key=` passed,
* the optional `openai` extra not installed,
* the model returned an empty or non-JSON response when
  `structured()` was asked for JSON.

Network / 5xx / auth errors from the SDK bubble through unchanged
(`openai.OpenAIError` and friends) so callers can pattern-match on
the upstream error types they already know.
