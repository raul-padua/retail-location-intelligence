# Deploying to Vercel

This repository is a **polyglot** app: Next.js in `web/` and FastAPI in `server/`.
Vercel must not treat the repo root as a lone FastAPI app (that is what produced the
“No FastAPI entrypoint found…” error and the incorrect suggestion of
`scripts.generate_web_fixtures:app`).

## Preferred: one project with Services

Config lives in [`vercel.json`](../vercel.json):

- `web` → Next.js (`web/`)
- `api` → FastAPI (`server.app:app`)
- Public `/api/*` (and OpenAPI `/docs`) rewrite to the API; everything else to the UI

Keep each service object limited to schema-allowed fields (`root`, `framework`,
`entrypoint`, …). Do **not** put `maxDuration`, `memory`, or `includeFiles` on the
service itself — Vercel rejects those as additional properties
([project configuration](https://vercel.com/docs/project-configuration)).
Function limits can be tuned later in the dashboard if a deploy needs a longer Atlas
timeout.

### Dashboard checklist

1. Open [the Vercel project](https://vercel.com/rauls-projects-2f2cc179/retail-location-intelligence).
2. **Settings → Build and Deployment → Framework Preset** → set to **Services**
   (required when `services` is present in `vercel.json`; see
   [Vercel Services](https://vercel.com/docs/services)).
3. Keep **Root Directory** empty / repository root (do not set it to `web/`).
4. **Settings → Environment Variables** (Production + Preview):

   | Name | Value |
   | --- | --- |
   | `STATEBOOK_API_TOKEN` | optional on Vercel — defaults to public `demo` when unset |
   | `STATEBOOK_API_BASE_URL` | optional — defaults to `https://api.statebook.com` |
   | `RLI_LOG_LEVEL` | `INFO` |
   | `OPENAI_API_KEY` | optional; users can still paste a key in the sidebar |

   Hosted builds default `STATEBOOK_API_TOKEN` to the public StateBook `demo` token when
   the variable is missing (so the Burlington metro demo works even if project env does
   not reach the FastAPI service). Set the variable explicitly when you have a licensed
   token.

   Do **not** set `NEXT_PUBLIC_API_BASE` for the single-project Services deploy.
   If it is set to `http://localhost:8000`, **delete it** — that is what makes the
   browser call your laptop instead of this deployment’s `/api`. Production builds
   use same-origin relative `/api/...` URLs automatically.

   After changing env vars, **Redeploy**. Confirm with
   `https://<deployment>/api/health` → `settings.atlas_token_present` should be `true`
   and `settings.is_demo_token` should be `true` when using `demo`.

5. Confirm the deployment builds **both** services (web + api). If only Next.js
   appears in the build log, Framework Preset is not Services.
6. Redeploy from the Deployments tab (or push to `main`).

### Smoke check after deploy

- UI: `https://<deployment>/`
- Health: `https://<deployment>/api/health` ← must return JSON, not a Next 404
- OpenAPI: `https://<deployment>/docs`

## Fallback: two Vercel projects (if Services is unavailable)

If the Framework Preset **Services** option is missing on your plan:

1. **Frontend project** — Root Directory `web`, Framework Next.js. Set
   `NEXT_PUBLIC_API_BASE` to the API project’s public URL (no trailing slash).
2. **API project** — Root Directory `.` (repo root). `[tool.vercel] entrypoint =
   "server.app:app"` in `pyproject.toml` is already set. Env:
   `STATEBOOK_API_TOKEN=demo`, and `RLI_CORS_ORIGINS` to the exact frontend origin(s),
   comma-separated (no wildcards).

## Known deployment limits

- Sessions use a **two-hour idle TTL** by default and are snapshotted under
  `/tmp/rli_sessions` on Vercel so a soft recycle of the same instance can reload them.
  Keep the browser tab open (the client heartbeats every two minutes) for long demos.
  Multi-replica shared storage is still a productionization step — see
  [`docs/productionization.md`](productionization.md).
- Pattern-based injection detection remains a prototype control.
- Bundle includes numpy / pandas / scikit-learn; if the build hits size limits, enable
  [Large Functions](https://vercel.com/docs/functions/limitations#large-functions-beta)
  or slim the market-discovery extras for a thinner API image.
