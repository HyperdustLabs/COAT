# Releasing OpenCOAT

How to cut a new version of all 8 `opencoat-runtime-*` packages.

CI does the heavy lifting (`.github/workflows/release.yml`); the human
work is concentrated in the **first-time PyPI setup** below. After
that, every release is `git tag vX.Y.Z && git push --tags`.

---

## 0. First-time PyPI setup (one-shot, before v0.1.0)

These steps need to happen exactly once, by an account with admin
rights on `HyperdustLabs/OpenCOAT` and a working PyPI account. After
this is done, every future release is hands-off.

### 0.1. Create a PyPI account

1. Register at <https://pypi.org/account/register/>
   (use a HyperdustLabs-owned email so the account can be transferred
   to the org later).
2. **Enable 2FA** — required for any new account since 2024-01-01.
3. Repeat for TestPyPI: <https://test.pypi.org/account/register/>
   (separate account; same email is fine).

### 0.2. Pre-register 8 Pending Publishers (Trusted Publishing, OIDC)

For each of the 8 package names, in **both** PyPI and TestPyPI:

1. Go to <https://pypi.org/manage/account/publishing/>
   (and <https://test.pypi.org/manage/account/publishing/>).
2. "Add a new pending publisher".
3. Fill the form:

   | Field | Value |
   | --- | --- |
   | PyPI Project Name | one of the 8 names below (one row per project) |
   | Owner | `HyperdustLabs` |
   | Repository name | `OpenCOAT` |
   | Workflow filename | `release.yml` |
   | Environment name | `pypi` (on PyPI) / `testpypi` (on TestPyPI) |

The 8 project names:

```text
opencoat-runtime-protocol
opencoat-runtime-core
opencoat-runtime-storage
opencoat-runtime-llm
opencoat-runtime-host-sdk
opencoat-runtime-host-plugins
opencoat-runtime-daemon
opencoat-runtime-cli
```

That's **16 forms total** (8 projects × 2 indexes). Each takes ~30
seconds. They become real publishers the first time the workflow
publishes a wheel for that name.

### 0.3. Create the two GitHub Environments

In `HyperdustLabs/OpenCOAT` → Settings → Environments:

1. **`testpypi`** — no protection rules. Used by `workflow_dispatch`.
2. **`pypi`** — strongly recommended: add yourself as a required
   reviewer so prod publishes always need a manual approval click.
   Optional: restrict to `refs/tags/v*` deployment branches.

The workflow references both environments by name; if they don't
exist the publish job fails fast with a clear "environment not
configured" error.

### 0.4. Reserve the names with a TestPyPI smoke test

```text
GitHub → Actions → Release → Run workflow → target: testpypi
```

This builds all 8 wheels, runs `twine check`, and publishes them
to TestPyPI. The Pending Publishers from step 0.2 turn into real
publishers on this push, and the names are reserved.

Verify in a clean venv:

```bash
python -m venv /tmp/oc-test-install
/tmp/oc-test-install/bin/pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  opencoat-runtime-cli
/tmp/oc-test-install/bin/opencoat --version
```

(`--extra-index-url` falls back to real PyPI for transitive deps
like `pydantic`, which TestPyPI doesn't necessarily mirror.)

If anything goes wrong here, **stop and fix before tagging** — the
prod PyPI step can't undo a bad upload.

---

## 1. Cutting a release (every time)

Once 0.1–0.4 are done, every release is:

```bash
# pre-flight on a clean checkout of main
bash scripts/verify.sh

# decide the version. SemVer:
#   0.1.0 → 0.1.1   patch (bugfix, no API change)
#   0.1.0 → 0.2.0   minor (additive API, breaking only inside same major)
#   0.1.0 → 1.0.0   major (breaking)

# bump every pyproject.toml in lockstep — see scripts/_bump_to_010.py
# for the pattern (a parameterised version of that lands in M6+ when
# we automate this; today it's a focused find/replace).

# tag + push
git tag v0.1.0
git push origin v0.1.0
```

The `release.yml` workflow then:

1. Builds all 8 wheels + sdists with `uv build`.
2. Runs `twine check` (PEP 639 metadata sanity).
3. Uploads them to PyPI via OIDC (Trusted Publishing).

Tag → PyPI is typically ~3–5 minutes end-to-end.

---

## 2. After the release lands

1. Sanity check in a clean venv:

   ```bash
   pipx install --force "opencoat-runtime-cli==X.Y.Z"
   opencoat --version
   ```

2. Cut a GitHub release with the auto-generated changelog at
   <https://github.com/HyperdustLabs/OpenCOAT/releases/new?tag=vX.Y.Z>.

3. If the major bumped, also bump the `compatible_with` minimum in
   <https://github.com/HyperdustLabs/opencoat-skill/blob/main/skill.json>.

---

## 3. Common gotchas

| symptom | fix |
| --- | --- |
| Trusted Publishing fails with "no token" | the `id-token: write` permission or the environment name is missing — double-check `release.yml` |
| `twine check` complains about `License-Expression` | bump to `hatchling>=1.27` (PEP 639 native support) |
| One package builds an empty wheel | `[tool.hatch.build.targets.wheel] packages = ["..."]` is missing or wrong; run `uv build` locally and `unzip -l dist/*.whl` to confirm |
| Pin mismatch (cli wants core 0.1.x, only 0.2.0 on PyPI) | bump every `opencoat-runtime-*` pyproject in the same release; never publish a partial set |
| TestPyPI 403 "no permission" | the Pending Publisher form had a typo (project name, env name, or filename) — re-check **all 16 forms** |

---

## 4. PyPI org transfer (later, when HyperdustLabs becomes a PyPI org)

PyPI started rolling out Organizations in 2023. Today the safest path
is "individual account → maintainer of org → projects transferred".
When HyperdustLabs is registered as a PyPI org:

1. Add the org as a maintainer on each of the 8 projects.
2. Transfer ownership project-by-project from the individual
   account to the org.
3. Update the Pending Publisher form for any new projects (the 8
   existing ones keep working — Trusted Publishing is per-project,
   not per-owner).

No code change needed; the workflow already publishes by project name.
