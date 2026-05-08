# Contributing to COAT Runtime

Thank you for working on COAT. This document captures **how we change the
codebase** so the milestones in
[`docs/design/v0.2-system-design.md`](docs/design/v0.2-system-design.md) §12
land cleanly and reviewably.

> Audience: humans and AI coding agents collaborating on this repo.
> Active from **M1 onwards**. M0 was a one-shot scaffold.

---

## TL;DR

```bash
git switch -c <branch>             # see naming below
# ... edit ...
./scripts/verify.sh                # local mirror of CI
git push -u origin HEAD             # opens PR on GitHub
# fill the PR template, wait for CI green, squash-merge
```

Direct pushes to `main` are no longer permitted from M1 on. Even single
commits go through a PR — that's our paper trail and CI gate.

---

## 1. Branching model

- `main` is always green and always deployable in spirit.
- All work happens on short-lived feature branches off `main`.

Branch names follow:

| Prefix | Use case | Example |
|---|---|---|
| `feat/`  | new capability scoped to a milestone task | `feat/m1-extractor` |
| `fix/`   | bug fix | `fix/copr-tokenizer-empty-input` |
| `docs/`  | docs / ADR only | `docs/adr-0009-vector-index` |
| `chore/` | tooling / CI / deps | `chore/ruff-0.16` |
| `refactor/` | non-behavioural cleanup | `refactor/coordinator-priority` |
| `test/`  | tests-only addition | `test/integration-turn-loop` |

Branches should die after merging — we squash-merge and delete the branch.

---

## 2. PR size & shape

- **Target ≤ 1000 lines of diff.** If a milestone task naturally exceeds
  this, split it up front (see the M1 plan below for an example).
- One PR per coherent concern. "Add extractor + fix unrelated typo +
  rename CLI flag" is three PRs.
- Every PR fills the [pull request template](.github/pull_request_template.md).
  The checklists are not decorative — they encode the contract.

### Suggested split for M1 (✅ landed)

```text
PR-1  feat/m1-concern-store      → memory ConcernStore + MemoryDCNStore
PR-2  feat/m1-joinpoint-pointcut → joinpoint catalog + 12 pointcut strategies
PR-3  feat/m1-coordinator         → coordinator / resolver / vector
PR-4  feat/m1-advice-weaver       → advice generator + weaver + verifier
PR-5  feat/m1-turn-loop           → wire facade.on_joinpoint end to end
PR-6  feat/m1-example-chat        → examples/01_simple_chat_agent
```

### Suggested split for M2

```text
PR-7  feat/m2-openai-client       → OpenAILLMClient                   ✅ landed
PR-8  feat/m2-anthropic-client    → AnthropicLLMClient                ← this PR
PR-9  feat/m2-azure-client        → AzureOpenAILLMClient + provider matrix
PR-10 feat/m2-extractor           → ConcernExtractor (NL governance docs → Concern)
PR-11 feat/m2-lifecycle           → ConcernLifecycleManager (reinforce/weaken/archive/revive)
PR-12 feat/m2-coding-agent        → examples/02_coding_agent_demo (real LLM)
```

PRs land in order; each one keeps `main` green.

---

## 3. Local verification (mandatory before opening a PR)

```bash
./scripts/verify.sh
```

This runs exactly what CI runs:

1. `uv sync --all-extras --dev`
2. `uv run ruff check .`
3. `uv run ruff format --check .`
4. `uv run python tools/schema_check.py`
5. `uv run pytest`

If a step fails, fix it before pushing — CI will reject the same way and
your reviewer's time is more valuable than yours.

---

## 4. What requires extra care

These changes always need an explicit reviewer sign-off:

- Anything under `packages/COAT-runtime-protocol/COAT_runtime_protocol/schemas/`
  — schemas are wire format. Bump `schema_version` if you change semantics
  and call out migration in the PR description.
- `packages/COAT-runtime-core/COAT_runtime_core/runtime.py`
  — the `COATRuntime` facade. Every host adapter and the daemon depend on
  these signatures.
- `packages/COAT-runtime-core/COAT_runtime_core/ports/*.py`
  — hexagonal ports. Adapter implementations across `storage`, `llm`, and
  `host-plugins` will follow.
- Any change to or addition of an ADR under [`docs/adr/`](docs/adr/).
  Architecture decisions are binding — supersede an ADR with a new ADR,
  don't silently rewrite history.
- Anything that affects a milestone's exit criteria.

For purely additive changes inside a single package (e.g. a new private
helper module), reviewer scrutiny is lighter.

---

## 5. Commit messages

Use Conventional-Commits-flavoured prefixes. The same vocabulary as the
branch prefixes:

```text
<type>(<scope>): <subject>

<optional body>
```

Examples seen in this repo:

```text
M0: monorepo skeleton, schemas, core, packages, CI
docs(readme): shorten hero title to COAT
chore(github): add pull request template
```

Body is optional but encouraged when explaining *why*.

---

## 6. Code style

Enforced automatically:

- `ruff check` (lint)
- `ruff format` (formatter)

Configured in [`pyproject.toml`](pyproject.toml). If a rule is wrong for
your case, add a tightly-scoped `# noqa: <code>` rather than disabling the
rule globally.

Type annotations: required on public APIs. Internal helpers may go without
when the type is obvious. We don't run `mypy --strict` yet (planned for
M2+) but please keep the types accurate so the future tightening is cheap.

---

## 7. Tests

- Every new module ships at least one test (smoke import + behavioural).
- `pytest --import-mode=importlib` is in effect — name your test files
  `test_<scope>.py` to keep them globally unique.
- For protocol changes, add round-trip tests under
  `packages/COAT-runtime-protocol/tests/`.
- Cross-package integration tests go under `tests/integration/`.

---

## 8. ADRs

Significant architectural choices live under [`docs/adr/`](docs/adr/) as
numbered Markdown files. To add a new one:

1. Pick the next number (currently 0009 onwards).
2. Use an existing ADR as the template (`docs/adr/0001-…` is short and clear).
3. Cite the ADR from the PR description so reviewers see the rationale up front.

---

## 9. Branch protection on `main`

Configured in GitHub *Settings → Branches → Branch protection rules*:

- ✅ Require a pull request before merging
- ✅ Require status checks to pass before merging
  - Required jobs: `Test (Python 3.11)`, `Test (Python 3.12)`, `Schema validation (no Python code)`
- ✅ Require branches to be up to date before merging
- ✅ Require linear history
- ✅ Restrict who can push (no direct pushes)
- ❌ Allow force pushes (off)
- ❌ Allow deletions (off)

Reviewer count is left at 0 in this single-human-plus-agent stage — the
gate is CI + the PR template's self-review checklist. Add a required
reviewer once a third collaborator joins.

---

## 10. Releasing

Out of scope until M2+. Follow the placeholder
[`scripts/release.sh`](scripts/release.sh) when we get there.
