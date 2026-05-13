# ADR 0009 — Consolidate 8 PyPI packages into 3

## Status

Accepted (v0.1.0, pre-PyPI publish).

## Context

The v0.2 design (see `docs/design/v0.2-system-design.md` §4) mapped each
architectural layer to its own publishable Python package, yielding **8
PyPI projects**:

```
opencoat-runtime-protocol
opencoat-runtime-core
opencoat-runtime-storage
opencoat-runtime-llm
opencoat-runtime-host-sdk
opencoat-runtime-host-plugins
opencoat-runtime-daemon
opencoat-runtime-cli
```

When we sat down to actually publish to PyPI, the cost of that mapping
became concrete:

- 16 "Pending Publisher" forms (8 projects × 2 indexes for Trusted
  Publishing) before the first release could land.
- 8 wheels + 8 sdists to verify on every cut.
- 8 `pyproject.toml` files to keep version-locked.
- Every internal call between layers crosses a wheel boundary, even
  though the layers are always installed together.
- End users have to read docs to figure out which of the 8 they need to
  `pipx install`; the answer is "the CLI one, which transitively pulls
  4 others". That's not a UX.

A second look revealed the structure was wrong-sized for the project:

| project           | LoC (.py) | independent consumer? |
| ----------------- | ---: | --- |
| protocol          |   544 | yes — third-party schemas, future TS/Go SDKs |
| core              | 5,727 | no — only used together with storage + LLM |
| storage           | 2,122 | no — only used by core/daemon |
| llm               | 1,219 | no — only used by core/daemon |
| daemon            | 1,615 | no — pulls cli + core + storage + llm |
| cli               | 2,292 | no — pulls daemon + core + storage |
| host-sdk          | **175** | yes — host integrators |
| host-plugins      | 1,400 | yes — host integrators (depends on host-sdk) |

`host-sdk` shipping **175 LoC** as its own PyPI project is the clearest
red flag. The runtime sub-packages are all symbiotic.

Compared against community practice in 2025-2026:

- **Single package + extras**: `ruff`, `uv`, `pydantic`, `httpx`, `rich`,
  `fastapi`, `openai-agents-python`. Same scale as us.
- **Many packages + namespace**: `apache-airflow-providers-*`,
  `opentelemetry-*`. ~100 contributors, broad 3rd-party integrations,
  per-integration release cadence. We're nowhere near this scale.
- **LangChain-style splits** (closest analogue to our 8-pack model) are
  widely criticised in the community (see langchain-ai/langchain#14694)
  as making both publishing and dependency management painful.

## Decision

Consolidate the 8 packages into **3 PyPI projects**, organised by
*consumer*, not by internal architectural layer:

| PyPI project                | Contents (Python modules)                                  | Consumer                |
| --------------------------- | ---------------------------------------------------------- | ----------------------- |
| `opencoat-runtime-protocol` | `opencoat_runtime_protocol`                                | schema-only consumers, language-agnostic SDKs |
| `opencoat-runtime`          | `opencoat_runtime_core` · `_storage` · `_llm` · `_daemon` · `_cli` | end users (operators, agent authors) |
| `opencoat-runtime-host`     | `opencoat_runtime_host_sdk` · `_openclaw` · `_hermes` · `_langgraph` · `_autogen` · `_crewai` · `_custom` | framework authors integrating their host with OpenCOAT |

Optional integrations (postgres, vector, openai, anthropic, http, grpc,
langgraph, …) ship as `[project.optional-dependencies]` extras on the
two consumer packages.

The Python module names are unchanged — `from opencoat_runtime_core
import OpenCOATRuntime` keeps working — so no downstream code edit is
required.

### Why protocol stays separate

It is the data contract package. Future TS / Go SDKs, third-party
observability tools (langfuse, langsmith, dify), and our own clients
should be able to depend on the schemas without pulling pydantic-heavy
runtime code. The split costs almost nothing (~544 LoC + JSON schemas)
and the optionality is worth it.

### Why runtime and host stay separate

The two have **different audiences**: runtime users *run OpenCOAT*; host
integrators *plug their framework into a running OpenCOAT*. Bundling
them would force every `langgraph` user to install the CLI and daemon,
or every operator to install all 6 adapters. The split here matches a
real consumer boundary, not just an internal one.

Crucially: `opencoat-runtime-host` depends only on
`opencoat-runtime-protocol`, not on `opencoat-runtime`. Host code never
imports from the core runtime in production (verified at the time of
this ADR — the only cross-import lived in one integration test).

## Consequences

### Positive

- **PyPI projects: 8 → 3** (62 % reduction).
- **Pending Publisher forms: 16 → 0** (we ship via API token first, can
  add Trusted Publishing later — see RELEASING.md §5).
- **Wheels per release: 8 → 3**.
- **End-user install**: `pipx install opencoat-runtime` is the single
  obvious command.
- **Skill.json `compatible_with`** drops to one package name.
- **No lockstep pin maintenance** between sibling packages (the
  `>=0.1.0,<0.2.0` matrix between 5 of the 8 simply vanishes).
- **Cross-layer imports** are now in-package — type checking, refactor,
  and goto-definition all become snappier.

### Negative

- **Lose physical layering**: the `protocol → core → storage` import
  boundary was previously enforced by wheel boundaries. Now it's
  enforced only by source-tree convention.
- **Mitigation**: layering is enforced by an import-graph linter
  (planned: add `tach` to `scripts/verify.sh` in M6+). Until then, code
  review and ruff's `isort` keep it honest. Note that the layering ADRs
  (0001 — concern as first-class unit, 0002 — AOP as mechanism, 0006 —
  six hexagonal ports) remain valid: they describe **module** layering,
  not **package** layering.
- **Future external plugin packages** (e.g. a third-party
  `opencoat-runtime-storage-redis`) must declare a peer dep on
  `opencoat-runtime>=X` rather than the older `opencoat-runtime-storage`.
  This is strictly less brittle than the old setup.

### Reversal cost

Splitting `opencoat-runtime` back into N sub-packages later is
mechanical and one-directional (no users to migrate, since each
sub-package would be a new name). Merging the other direction (8 → 3)
is what we're doing today and it cost a single PR.

## See also

- ADR 0005 — runtime/daemon **process** split (orthogonal to packaging;
  still applies, but both processes now ship in `opencoat-runtime`).
- ADR 0006 — six hexagonal ports (module-level decision, unaffected).
- `RELEASING.md` — operator handbook for the 3-package release flow.
