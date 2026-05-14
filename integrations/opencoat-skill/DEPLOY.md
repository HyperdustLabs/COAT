# Deploying the skill to `www.opencoat.ai`

One-time setup so `https://www.opencoat.ai/SKILL.md` serves the
contents of `SKILL.md` from this repo, while every other path on the
domain keeps going to the Strikingly-hosted landing page. The
mechanism is a Cloudflare Worker — see [`worker/README.md`](worker/README.md)
for what it does on every request, and [`worker/wrangler.toml`](worker/wrangler.toml)
for the route list.

Once these steps land you never have to repeat them; pushes to
`main` deploy the worker automatically via
[`.github/workflows/deploy-worker.yml`](.github/workflows/deploy-worker.yml).

## Estimated time

~15 minutes, mostly waiting for DNS propagation.

## Prerequisites

- Admin access to the `opencoat.ai` domain at GoDaddy (current
  registrar, nameservers `ns31/ns32.domaincontrol.com`).
- A Cloudflare account (free plan is fine).
- Admin access to the `HyperdustLabs/opencoat-skill` GitHub repo
  (this one).

## Steps

### 1. Add `opencoat.ai` to Cloudflare

1. Cloudflare dashboard → **Add a site** → enter `opencoat.ai` →
   **Free** plan.
2. Cloudflare scans the existing GoDaddy DNS and proposes a record
   set. **Accept everything as-is** — the existing A records
   pointing to Strikingly (`54.183.102.22`, `18.181.31.166`,
   `54.248.227.74`) and the `www.opencoat.ai` CNAME to
   `www.opencoat.ai.s.strikinglydns.com` all need to come along.
3. The "Proxy status" column for each record can stay on the
   default (proxied = orange cloud). The worker needs the proxy
   on so it can intercept requests.
4. Cloudflare gives you two nameservers (something like
   `<name>.ns.cloudflare.com`). Note them down.

### 2. Switch nameservers at GoDaddy

1. GoDaddy → **My Products** → `opencoat.ai` → **DNS** →
   **Nameservers** → **Change**.
2. Enter the two Cloudflare nameservers, save.
3. Cloudflare verifies the change usually within 5 minutes; can
   take up to 24 hours in pathological cases.

While DNS is propagating the Strikingly site keeps working — the
DNS records that resolve are the same, you've just changed who's
authoritative for them.

### 3. Create the Cloudflare API token

1. Cloudflare dashboard → **My Profile** → **API Tokens** →
   **Create Token**.
2. Use the **Edit Cloudflare Workers** template.
3. Under "Account Resources" pick your account. Under "Zone
   Resources" pick `opencoat.ai`.
4. **Create Token** → copy the token immediately (you can't see it
   again).
5. Also copy your **Account ID** from the right-hand sidebar of any
   zone overview page.

### 4. Add the token to GitHub

1. GitHub → `HyperdustLabs/opencoat-skill` → **Settings** →
   **Secrets and variables** → **Actions** → **New repository
   secret**.
2. Add two secrets:
   - `CLOUDFLARE_API_TOKEN` = the token from §3.
   - `CLOUDFLARE_ACCOUNT_ID` = the account id from §3.

### 5. Trigger the first deploy

Either:

- Merge any PR that touches `worker/` or a skill file (the workflow
  runs `on: push: branches: [main]`), **or**
- Run the workflow manually: GitHub → **Actions** → **Deploy
  Cloudflare Worker** → **Run workflow** → branch `main`.

The job:

1. Type-checks the worker (catches TS errors before they hit the
   edge).
2. Deploys via `cloudflare/wrangler-action@v3` → `wrangler deploy`.
3. Smoke-tests every route — fails the deploy if any of the eight
   skill paths returns a non-200 or the wrong `Content-Type`.

### 6. Smoke-test from your laptop

```bash
curl -I https://www.opencoat.ai/SKILL.md
# expected:
#   HTTP/2 200
#   content-type: text/markdown; charset=utf-8
#   cache-control: public, max-age=300, s-maxage=300
#   x-skill-source: github:HyperdustLabs/opencoat-skill@main/SKILL.md

# All eight routes:
for p in SKILL.md skill.md skill.json concerns.md inspection.md rules.md README.md readme.md; do
  printf '%-15s ' "$p"
  curl -sSL -o /dev/null -w '%{http_code} %{content_type}\n' "https://www.opencoat.ai/$p"
done

# Strikingly landing page still works:
curl -sSL -o /dev/null -w '%{http_code}\n' https://www.opencoat.ai/
# → 200
```

## Day-2 ops

### Where does each thing live?

| Concern                 | Lives in                                                            |
| ----------------------- | ------------------------------------------------------------------- |
| Marketing / landing     | Strikingly (no change — edit at `www.strikingly.com`)               |
| Skill content           | This repo, on `main`. Pushing to `main` auto-redeploys the worker.  |
| URL routing             | `worker/wrangler.toml` — add a route here to expose a new path.     |
| Edge cache TTL          | `EDGE_TTL_SECONDS` in `worker/wrangler.toml` (default 300s).        |
| Branch the worker reads | `GITHUB_BRANCH` in `worker/wrangler.toml`.                          |

### Adding a new skill file

1. Add `your-file.md` to the repo root, commit it on a branch.
2. Add a route + `PATH_MAP` entry:
   - `worker/wrangler.toml`: a new line under `routes = [...]`.
   - `worker/src/worker.ts`: a new key in `PATH_MAP`.
3. Merge the PR. The workflow re-deploys and the file is live at
   `https://www.opencoat.ai/your-file.md` within seconds.

### Cutting a release

If you want to freeze a known-good skill snapshot at a stable URL,
point the worker at a tag instead of `main`:

```toml
# worker/wrangler.toml
GITHUB_BRANCH = "v0.3.0"   # any ref raw.githubusercontent.com accepts
```

`raw.githubusercontent.com` accepts tags, branches, and commit SHAs
all in the same `<ref>` slot.

### Rollback

See [`worker/README.md`](worker/README.md) §Rollback. Two checkboxes
on the Cloudflare dashboard; no DNS changes needed.
