/**
 * opencoat-skill proxy worker.
 *
 * Strategy:
 *
 *   www.opencoat.ai/<skill-file>
 *       → raw.githubusercontent.com/<owner>/<repo>/<branch>/<repo-file>
 *
 * Where ``<repo-file>`` is ``SKILL.md`` for both ``/SKILL.md`` and the
 * lowercase Moltbook-style alias ``/skill.md`` (and similarly
 * ``README.md`` ↔ ``/readme.md``). Every other path is rejected with
 * 404 — the worker only intercepts the nine routes declared in
 * ``wrangler.toml``, so Cloudflare never even invokes us for the
 * Strikingly-hosted marketing pages.
 *
 * Why a worker (and not just a static GitHub Pages site on a
 * subdomain): keeps the public skill URL on ``www.opencoat.ai`` at
 * the root, matching Moltbook's convention exactly, without
 * disturbing the Strikingly landing page that lives at the same
 * host. The marketing team and the skill team stay decoupled.
 *
 * Bonus duties the proxy takes on:
 *
 *   1. Rewrite ``Content-Type`` — raw.githubusercontent.com serves
 *      ``.md`` as ``text/plain`` which trips agents that branch on
 *      the MIME. We emit ``text/markdown; charset=utf-8`` /
 *      ``application/json; charset=utf-8`` instead.
 *   2. CORS — ``Access-Control-Allow-Origin: *`` so browser-based
 *      agents can ``fetch()`` directly without a CORS preflight.
 *   3. Provenance header — ``X-Skill-Source`` records exactly which
 *      ``owner/repo@branch/path`` produced the body, so users can
 *      verify what they're getting in a single ``curl -I``.
 *   4. Short edge cache (5min) — absorbs a swarm of agents
 *      fetching during a deploy burst without hammering GitHub's
 *      raw-file rate limits.
 */

interface Env {
  GITHUB_OWNER: string;
  GITHUB_REPO: string;
  GITHUB_BRANCH: string;
  EDGE_TTL_SECONDS: string;
}

// Public path → repo path. Lowercase aliases collapse onto the
// canonical uppercase filenames so we never have two versions of the
// same file drifting in the repo.
const PATH_MAP: Record<string, string> = {
  "SKILL.md": "SKILL.md",
  "skill.md": "SKILL.md",
  "skill.json": "skill.json",
  "concerns.md": "concerns.md",
  "inspection.md": "inspection.md",
  "rules.md": "rules.md",
  "README.md": "README.md",
  "readme.md": "README.md",
  "bootstrap_daemon.sh": "bootstrap_daemon.sh",
};

function contentTypeFor(repoPath: string): string {
  if (repoPath.endsWith(".json")) return "application/json; charset=utf-8";
  if (repoPath.endsWith(".md")) return "text/markdown; charset=utf-8";
  if (repoPath.endsWith(".sh")) return "text/plain; charset=utf-8";
  return "text/plain; charset=utf-8";
}

function corsHeaders(): HeadersInit {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    // Tight allow list — only the headers a typical ``fetch()`` from
    // an agent would send. No auth header is forwarded because the
    // skill files are public and the worker is read-only.
    "Access-Control-Allow-Headers": "Accept, Cache-Control, If-None-Match, If-Modified-Since",
    "Access-Control-Max-Age": "86400",
  };
}

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("method not allowed", {
        status: 405,
        headers: { Allow: "GET, HEAD, OPTIONS", ...corsHeaders() },
      });
    }

    const url = new URL(request.url);
    // Strip the leading slash so ``/SKILL.md`` becomes ``SKILL.md``.
    // ``URL.pathname`` is already normalised — no ``..`` traversal
    // possible. We additionally reject any path with a slash so an
    // attacker can't smuggle ``/SKILL.md/../../etc/passwd``.
    const pubPath = url.pathname.replace(/^\/+/, "");
    if (pubPath.includes("/") || !(pubPath in PATH_MAP)) {
      return new Response(`skill file not found: /${pubPath}`, {
        status: 404,
        headers: { "Content-Type": "text/plain; charset=utf-8", ...corsHeaders() },
      });
    }
    const repoPath = PATH_MAP[pubPath];

    const upstreamUrl =
      `https://raw.githubusercontent.com/${env.GITHUB_OWNER}/` +
      `${env.GITHUB_REPO}/${env.GITHUB_BRANCH}/${repoPath}`;

    // Parse TTL allowing an explicit ``0`` to disable the edge cache.
    // Naive ``parseInt(...) || 300`` would silently rewrite ``"0"``
    // back to 300, which makes emergency content rollouts stale for
    // up to five minutes after maintainers intentionally opt out.
    const parsedTtl = Number.parseInt(env.EDGE_TTL_SECONDS ?? "300", 10);
    const ttl = Number.isFinite(parsedTtl) && parsedTtl >= 0 ? parsedTtl : 300;

    const upstream = await fetch(upstreamUrl, {
      // Forward the *incoming* method so ``HEAD`` probes (curl -I,
      // uptime monitors) ask GitHub for headers only instead of
      // pulling the full body every time. Both ``GET`` and ``HEAD``
      // are safely cacheable by Cloudflare and use independent edge
      // cache keys, so this doesn't poison the cache for the other
      // verb.
      method: request.method,
      // Cloudflare-specific cache hint: cache the upstream response
      // at the Cloudflare edge for ``ttl`` seconds regardless of
      // the upstream's own Cache-Control. ``ttl === 0`` disables
      // the edge cache entirely (every request hits GitHub).
      cf: ttl > 0 ? { cacheTtl: ttl, cacheEverything: true } : { cacheTtl: 0, cacheEverything: false },
      headers: {
        "User-Agent": "opencoat-skill-worker/1.0 (+https://github.com/HyperdustLabs/opencoat-skill)",
        Accept: "text/plain, */*",
      },
    });

    if (!upstream.ok) {
      // GitHub raw returns 404 for unknown paths and 5xx during
      // outages — surface the same status so the client can branch
      // on it, but rewrite the body so it's actionable instead of
      // GitHub-flavored.
      const body =
        upstream.status === 404
          ? `upstream missing: ${repoPath}@${env.GITHUB_BRANCH} — re-check the branch / file name`
          : `upstream error ${upstream.status} fetching ${repoPath}`;
      return new Response(body, {
        status: upstream.status,
        headers: { "Content-Type": "text/plain; charset=utf-8", ...corsHeaders() },
      });
    }

    // Stream the body through, replacing headers. ``HEAD`` requests
    // get an empty body but the same headers as a ``GET`` would —
    // ``new Response(null, …)`` is the documented Workers idiom.
    const body = request.method === "HEAD" ? null : upstream.body;
    return new Response(body, {
      status: 200,
      headers: {
        "Content-Type": contentTypeFor(repoPath),
        "Cache-Control": `public, max-age=${ttl}, s-maxage=${ttl}`,
        "X-Skill-Source": `github:${env.GITHUB_OWNER}/${env.GITHUB_REPO}@${env.GITHUB_BRANCH}/${repoPath}`,
        // ETag passthrough so conditional ``If-None-Match`` requests
        // can short-circuit at the edge and the client gets a 304.
        ...(upstream.headers.get("etag") ? { ETag: upstream.headers.get("etag")! } : {}),
        ...corsHeaders(),
      },
    });
  },
};
