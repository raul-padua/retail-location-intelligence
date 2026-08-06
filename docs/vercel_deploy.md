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
   | `STATEBOOK_API_TOKEN` | `demo` (or your licensed token) |
   | `STATEBOOK_API_BASE_URL` | `https://api.statebook.com` |
   | `RLI_LOG_LEVEL` | `INFO` |
   | `OPENAI_API_KEY` | optional; users can still paste a key in the sidebar |

   Do **not** set `NEXT_PUBLIC_API_BASE` for the single-project Services deploy.
   If it is set to `http://localhost:8000`, **delete it** — that is what makes the
   browser call your laptop instead of this deployment’s `/api`. Production builds
   use same-origin relative `/api/...` URLs automatically.

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

- Session state is **in-memory**. On serverless instances it can reset between cold
  starts; Fluid compute usually keeps a short demo usable, but this is not
  multi-replica production storage.
- Pattern-based injection detection remains a prototype control.
- Bundle includes numpy / pandas / scikit-learn; if the build hits size limits, enable
  [Large Functions](https://vercel.com/docs/functions/limitations#large-functions-beta)
  or slim the market-discovery extras for a thinner API image.
