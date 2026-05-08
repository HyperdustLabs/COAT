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
├── anthropic_client.py      # ✅ M2 PR-2 — Anthropic (Claude)
├── azure_openai_client.py   # ✅ M2 PR-3 — Azure OpenAI (key + AAD auth)
└── ollama_client.py         # M2 (planned)
```

## Provider matrix

All adapters implement the same `LLMClient` port — same four methods,
same `LLMClient` structural protocol, swappable at runtime:

| Provider | Class | Native JSON-schema | System prompt shape | `score()` | Auth |
| --- | --- | --- | --- | --- | --- |
| OpenAI / OpenAI-compatible gateways | `OpenAILLMClient` | ✅ strict mode | inline `role: "system"` row | numeric heuristic; `score_max_tokens=None` for o1 / o3 / gpt-5 | `OPENAI_API_KEY` |
| Azure OpenAI | `AzureOpenAILLMClient` (subclass of `OpenAILLMClient`) | ✅ strict mode (inherited) | inline `role: "system"` row (inherited) | inherited | `AZURE_OPENAI_API_KEY` **or** AAD token / token provider |
| Anthropic (Claude) | `AnthropicLLMClient` | forced tool-use (equivalent reliability) | hoisted to top-level `system=` kwarg; multiple rows concatenated | numeric heuristic; same regex | `ANTHROPIC_API_KEY` |
| In-proc stub | `StubLLMClient` (lives in `COAT_runtime_core.llm`) | scripted return value | n/a | scripted return value | none |

## Install

Each provider ships behind its own optional extra so you only pay for
the SDK you actually use:

```bash
pip install "COAT-runtime-llm[openai]"
pip install "COAT-runtime-llm[anthropic]"
pip install "COAT-runtime-llm[azure]"      # alias for the openai extra
```

In the workspace dev environment (`uv sync --all-extras --dev`) every
SDK is pulled in as a dev dependency so CI can exercise the adapters
under mocks.

## OpenAI

```python
from COAT_runtime_llm import OpenAILLMClient

llm = OpenAILLMClient(
    model="gpt-4o-mini",          # default
    api_key=None,                 # falls back to OPENAI_API_KEY env var
    base_url=None,                # set for Azure / vLLM / OpenRouter etc.
    timeout_seconds=20.0,
    default_temperature=0.0,      # deterministic by default
    score_max_tokens=8,           # tiny cap on score() — set None for o1 / o3 / gpt-5
)

print(llm.complete("Say hi in one word."))
```

The same client works against any OpenAI-compatible HTTP gateway —
just override `base_url`. For Azure-native deployments use
`AzureOpenAILLMClient` (below), which handles the deployment-based
routing and AAD token plumbing.

### Reasoning models (o1 / o3 / gpt-5 family)

These models reject `max_tokens` and expect `max_completion_tokens`
instead. Pass `score_max_tokens=None` to drop the score-specific
cap, and let the host (or a future provider subclass) handle the
right token-cap kwarg. The other three port methods stay
unaffected — they only set `max_tokens` when the caller (or the
client's `default_max_tokens`) explicitly asked for one.

## Azure OpenAI

Use `AzureOpenAILLMClient` for native Azure-deployed models — the
chat-completions surface is identical to upstream so every
`LLMClient` method is inherited verbatim from `OpenAILLMClient`.
Azure changes only the SDK constructor (auth shape, mandatory
`api_version`, deployment-based routing).

```python
from COAT_runtime_llm import AzureOpenAILLMClient

llm = AzureOpenAILLMClient(
    deployment="my-prod-deploy",                # required
    endpoint="https://my-resource.openai.azure.com",  # or AZURE_OPENAI_ENDPOINT
    api_version="2024-06-01",                   # default; or OPENAI_API_VERSION
    api_key=None,                               # falls back to AZURE_OPENAI_API_KEY
    timeout_seconds=20.0,
    default_temperature=0.0,
    score_max_tokens=8,
)
print(llm.complete("Say hi in one word."))
```

For Microsoft Entra (AAD) auth, pass a token provider — the SDK
calls it on each request so token rotation is automatic:

```python
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from COAT_runtime_llm import AzureOpenAILLMClient

provider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://cognitiveservices.azure.com/.default",
)
llm = AzureOpenAILLMClient(
    deployment="my-prod-deploy",
    endpoint="https://my-resource.openai.azure.com",
    azure_ad_token_provider=provider,
)
```

A few things the adapter pins down so hosts can stay generic:

* **Deployment is the routing key.** Azure routes on deployment
  name, not model family — the constructor takes `deployment=...`
  and stores it where the parent's `chat.completions.create(...)`
  expects `model=`. There is no model dropdown on the call site.
* **`api_version` is required.** Defaults to `2024-06-01`; falls
  back to `OPENAI_API_VERSION` when set; per-call value beats env.
* **One credential at a time.** The constructor enforces mutual
  exclusion between `api_key`, `azure_ad_token`, and
  `azure_ad_token_provider`. Misconfiguring more than one fails
  fast at startup with a descriptive `AzureOpenAIClientError`
  (which is an alias of `OpenAIClientError` so existing handlers
  keep working).

## Anthropic (Claude)

```python
from COAT_runtime_llm import AnthropicLLMClient

llm = AnthropicLLMClient(
    model="claude-3-5-sonnet-latest",  # default
    api_key=None,                      # falls back to ANTHROPIC_API_KEY env var
    base_url=None,                     # for on-prem proxies / gateways
    timeout_seconds=20.0,
    default_temperature=0.0,           # deterministic by default
    default_max_tokens=1024,           # required by Anthropic — never None
    score_max_tokens=8,                # tiny cap for the score() heuristic
)

print(llm.complete("Say hi in one word."))
```

A few provider-specific behaviours the adapter takes care of so the
host doesn't have to:

* **System messages are hoisted.** Anthropic's API takes a top-level
  `system=` kwarg rather than a `role: "system"` entry inside
  `messages`. Hosts that pass an OpenAI-style mixed list keep
  working — the adapter splits the system rows out and concatenates
  multiple of them with blank lines.
* **`max_tokens` is always set on the wire.** Every ``messages.create``
  carries ``max_tokens``; if you omit it per-call, the client fills in
  ``default_max_tokens`` (1024 by default). The constructor rejects only
  **negative** values — ``0`` is permitted at construction (Codex review
  on PR-8); if Anthropic rejects ``0`` for a given route the SDK still
  surfaces a clean error. There is no equivalent of OpenAI's
  ``score_max_tokens=None`` to omit the score cap; bump ``score_max_tokens``
  if you need more headroom.
* **`structured()` uses forced tool use.** Claude has no JSON-schema
  `response_format`, so the adapter defines a single `respond` tool
  whose `input_schema` IS your schema, pins the model to it via
  `tool_choice`, and returns the resulting `tool_use` block's input
  dict. This is the same reliability tier as OpenAI strict-mode.
* **`stop` becomes `stop_sequences`.** Renamed at the kwarg layer; the
  abstract `LLMClient.complete()` surface is unchanged.

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

Each provider ships its own client-side error type for fatal
misconfiguration; both are subclasses of `RuntimeError` so a host
that doesn't care which SDK it's wired up to can catch the base.

`OpenAIClientError` (aliased as `AzureOpenAIClientError`):

* `OPENAI_API_KEY` / `AZURE_OPENAI_API_KEY` not set and no
  `api_key=` passed,
* the optional `openai` extra not installed,
* the model returned an empty or non-JSON response when
  `structured()` was asked for JSON,
* (Azure-only) endpoint not configured, multiple credentials passed
  simultaneously, or empty deployment.

`AnthropicClientError`:

* `ANTHROPIC_API_KEY` not set and no `api_key=` passed,
* the optional `anthropic` extra not installed,
* `default_max_tokens` / `score_max_tokens` constructed with a
  negative value,
* the model declined to call the forced `respond` tool in
  `structured()`.

Network / 5xx / auth errors from each SDK bubble through unchanged
(`openai.OpenAIError`, `anthropic.AnthropicError`, …) so callers can
pattern-match on the upstream error types they already know.
