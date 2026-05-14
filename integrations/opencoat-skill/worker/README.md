# Worker — `opencoat-skill-proxy`

Cloudflare Worker that exposes the skill files at the root of
`https://www.opencoat.ai/` while leaving the Strikingly-hosted
landing page on the same host untouched. See [`../DEPLOY.md`](../DEPLOY.md)
for the one-time Cloudflare / DNS / GitHub-secret setup.

## Map

| Public URL                                   | Source on GitHub                                   |
| -------------------------------------------- | -------------------------------------------------- |
| `https://www.opencoat.ai/SKILL.md`           | `SKILL.md` on `main`                               |
| `https://www.opencoat.ai/skill.md` (alias)   | `SKILL.md` on `main`                               |
| `https://www.opencoat.ai/skill.json`         | `skill.json` on `main`                             |
| `https://www.opencoat.ai/concerns.md`        | `concerns.md` on `main`                            |
| `https://www.opencoat.ai/inspection.md`      | `inspection.md` on `main`                          |
| `https://www.opencoat.ai/rules.md`           | `rules.md` on `main`                               |
| `https://www.opencoat.ai/README.md`          | `README.md` on `main`                              |
| `https://www.opencoat.ai/readme.md` (alias)  | `README.md` on `main`                              |

Every other path on `www.opencoat.ai` flows through to Strikingly as
before — the worker is configured with explicit
`{ pattern = "www.opencoat.ai/<exact-file>" }` routes, so it never
intercepts the marketing site's own pages.

## What the worker does on a hit

1. Reads the public path → looks up the canonical repo file in
   `PATH_MAP`. Lowercase aliases collapse onto the uppercase
   filenames in the repo so there's only one source of truth.
2. Fetches
   `https://raw.githubusercontent.com/HyperdustLabs/opencoat-skill/main/<repo-file>`
   with a 5-minute Cloudflare edge cache (`cf.cacheTtl: 300`).
3. Replaces the upstream `Content-Type` (`text/plain` for `.md`)
   with `text/markdown; charset=utf-8` or `application/json; charset=utf-8`.
4. Adds CORS headers (`Access-Control-Allow-Origin: *`) so
   browser-based agents can `fetch()` without a preflight failing.
5. Adds an `X-Skill-Source: github:<owner>/<repo>@<branch>/<path>`
   header so users can verify provenance with `curl -I`.
6. Passes `ETag` through so `If-None-Match` clients see 304s.

## Local development

```bash
cd worker
npm install
npx wrangler dev
# → http://localhost:8787/SKILL.md
```

`wrangler dev` runs the worker against a local sandbox; routes are
ignored locally so any path resolves through `PATH_MAP`.

## Deploy

CI handles this on every push to `main` via
[`.github/workflows/deploy-worker.yml`](../.github/workflows/deploy-worker.yml).
For a manual deploy:

```bash
cd worker
npx wrangler login          # one-time
npx wrangler deploy
```

## Rollback

Two options:

1. **Disable the worker on a single route**: Cloudflare dashboard →
   *Workers Routes* → toggle off any of the eight routes. Strikingly
   immediately serves whatever it has at that path (typically a 404
   page), and the rest of the skill stays live.
2. **Disable the whole worker**: Cloudflare dashboard →
   *Workers & Pages* → `opencoat-skill-proxy` → *Pause*. All eight
   routes fall through to Strikingly.

No DNS changes are needed in either case.
