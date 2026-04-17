# FreightCheck — Environment & Setup

**Version**: 1.0
**Status**: Draft
**Author**: Basit Ali
**Last Updated**: 2026-04-18

---

## Purpose

Every environment variable, external account, and setup step required to run FreightCheck locally and in production. No prior project knowledge assumed.

---

## 1. Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.11+ | Backend runtime |
| Node.js | 20+ (LTS) | Frontend build + dev server |
| `uv` | latest | Preferred Python dependency manager. `pip` works as fallback |
| Git | any | Repo checkout |
| MongoDB | Atlas free tier (cloud) — local not recommended | Persistence |
| A Google account | — | To get a Gemini API key |

No Docker required for local dev. Docker is used only for the production backend image on Render.

---

## 2. External Accounts

### 2.1 Google AI Studio (Gemini API Key)

1. Go to https://aistudio.google.com/app/apikey.
2. Sign in with any Google account.
3. Click **Create API key** → choose "Create API key in new project" (or use an existing project).
4. Copy the key immediately. It is shown only once.
5. Add it to `.env` as `GEMINI_API_KEY=...`.

**Pricing (as of 2026-04)**: Gemini 2.5 Flash has a generous free tier suitable for development and portfolio demos. Budget caps in `settings.py` prevent runaway cost. Production usage should monitor the quota dashboard.

**Quota**: free tier limits are RPM-based; FreightCheck stays well under them at demo scale. If quota is hit, the backend returns the session as `failed` with `GeminiAPIError` in `error_message`.

### 2.2 MongoDB Atlas

1. Go to https://www.mongodb.com/cloud/atlas/register and sign up.
2. Create a new free (M0) cluster. Region: pick the one closest to your Render deployment region.
3. **Database Access**: create a new database user with read/write to any database. Use a strong auto-generated password — copy it immediately.
4. **Network Access**: add IP `0.0.0.0/0` to the allow-list for now (MVP; tighten for production).
5. Connect → **Connect your application** → copy the `mongodb+srv://` connection string.
6. Replace `<password>` in the string with the actual password.
7. Append `/freightcheck?retryWrites=true&w=majority` to specify the database.
8. Add to `.env` as `MONGODB_URI=mongodb+srv://...`.

**Indexes**: created automatically on backend startup by `services/mongo.py:ensure_indexes()`. No manual step required.

### 2.3 Render (Backend hosting)

1. Sign up at https://render.com with GitHub OAuth.
2. Connect your FreightCheck repository.
3. Do NOT configure the web service manually — the `render.yaml` file in the repo defines it.
4. Set the following secrets under **Environment** when the first deploy prompts you:
   - `GEMINI_API_KEY`
   - `MONGODB_URI`
   - `ALLOWED_ORIGINS` = `https://<your-vercel-deployment>.vercel.app`

### 2.4 Vercel (Frontend hosting)

1. Sign up at https://vercel.com with GitHub OAuth.
2. Import the FreightCheck repository.
3. Set the **Root Directory** to `frontend/`.
4. Framework preset: Vite (auto-detected).
5. Environment variable: `VITE_API_URL` = `https://<your-render-deployment>.onrender.com`.
6. Deploy.

---

## 3. Environment Variables

### 3.1 Backend

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | **yes** | — | Google AI Studio API key. Never committed |
| `MONGODB_URI` | **yes** | — | Mongo connection string including password and database |
| `MONGODB_DB` | no | `freightcheck` | Database name; override for multi-env on the same cluster |
| `ALLOWED_ORIGINS` | no (dev) / **yes** (prod) | `http://localhost:5173` | Comma-separated CORS origins |
| `MAX_FILE_SIZE_MB` | no | `10` | Upload limit per file |
| `GEMINI_MODEL` | no | `gemini-2.5-flash` | Model override for evals or experiments |
| `GEMINI_MAX_RETRIES` | no | `2` | Network retry count on Gemini failures |
| `AGENT_MAX_ITERATIONS` | no | `8` | Planner loop hard cap |
| `AGENT_TOKEN_BUDGET` | no | `50000` | Per-session token cap |
| `AGENT_TIME_BUDGET_MS` | no | `25000` | Per-session time cap (ms) |
| `UPLOAD_CACHE_TTL_SECONDS` | no | `600` | How long upload-parsed text is cached before audit must be triggered |
| `LOG_LEVEL` | no | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FORMAT` | no | `json` in prod, `console` local | `json` or `console` |
| `PORT` | no (Render sets it) | `8000` | HTTP port for Uvicorn |

### 3.2 Frontend

| Variable | Required | Default | Description |
|---|---|---|---|
| `VITE_API_URL` | **yes** | `http://localhost:8000` | Backend base URL. Must include protocol, no trailing slash |

The frontend never holds secrets. `VITE_API_URL` is the only variable.

### 3.3 `.env.example` (Backend)

The committed `.env.example` file must contain all variables from §3.1 with placeholder or default values:

```
# ---- Required (no defaults) ----
GEMINI_API_KEY=your-gemini-api-key-here
MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net/freightcheck?retryWrites=true&w=majority

# ---- Optional overrides ----
MONGODB_DB=freightcheck
ALLOWED_ORIGINS=http://localhost:5173
MAX_FILE_SIZE_MB=10

GEMINI_MODEL=gemini-2.5-flash
GEMINI_MAX_RETRIES=2

AGENT_MAX_ITERATIONS=8
AGENT_TOKEN_BUDGET=50000
AGENT_TIME_BUDGET_MS=25000

UPLOAD_CACHE_TTL_SECONDS=600

LOG_LEVEL=INFO
LOG_FORMAT=console
```

### 3.4 `.env.example` (Frontend)

```
VITE_API_URL=http://localhost:8000
```

### 3.5 `.gitignore` Requirements

The root `.gitignore` must include at minimum:

```
# Python
__pycache__/
*.pyc
.venv/
.mypy_cache/
.ruff_cache/
.pytest_cache/

# Node
node_modules/
dist/
.vite/

# Env
.env
.env.local
.env.*.local

# Eval outputs
backend/eval/reports/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
```

`.env.example` is **not** in `.gitignore` — it must be committed.

---

## 4. Local Development Setup

### 4.1 First-Time Setup

From a fresh clone:

```bash
# 1. Backend
cd backend
uv venv                         # or: python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
uv sync                          # or: pip install -e ".[dev]"
cp .env.example .env             # then fill in GEMINI_API_KEY and MONGODB_URI

# 2. Frontend (in a separate terminal)
cd frontend
npm install
cp .env.example .env
```

### 4.2 Running

Terminal 1 — backend:
```bash
cd backend
source .venv/bin/activate
uvicorn freightcheck.main:app --reload --port 8000
```

Terminal 2 — frontend:
```bash
cd frontend
npm run dev
```

Open http://localhost:5173.

### 4.3 Verify Setup

From a third terminal:
```bash
curl http://localhost:8000/health
# Expected: {"status":"ok","mongo":"connected","gemini":"configured"}
```

If `/health` returns `mongo: disconnected`, check `MONGODB_URI`. If `gemini: not_configured`, check `GEMINI_API_KEY`.

---

## 5. Deployment

### 5.1 Backend — Render

**`render.yaml`** (committed to the repo root):

```yaml
services:
  - type: web
    name: freightcheck-api
    runtime: docker
    dockerfilePath: ./backend/Dockerfile
    dockerContext: ./backend
    plan: free
    healthCheckPath: /health
    envVars:
      - key: GEMINI_API_KEY
        sync: false                     # set in Render dashboard
      - key: MONGODB_URI
        sync: false                     # set in Render dashboard
      - key: ALLOWED_ORIGINS
        sync: false                     # set in Render dashboard
      - key: LOG_FORMAT
        value: json
      - key: LOG_LEVEL
        value: INFO
```

**`backend/Dockerfile`**:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

COPY src ./src

ENV PYTHONPATH=/app/src
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "freightcheck.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Deploy flow**:
1. Merge to `main`.
2. Render auto-builds from the Dockerfile.
3. First build ≈ 3–5 minutes. Subsequent builds use layer cache.
4. Health check `/health` gates the rollout.

### 5.2 Frontend — Vercel

**`frontend/vercel.json`**:

```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": "vite",
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

The rewrites block makes client-side routing (React Router) work with direct URL access.

**Deploy flow**:
1. Merge to `main`.
2. Vercel auto-builds from the `frontend/` directory.
3. First build ≈ 30s.

### 5.3 Post-Deploy Checklist

- [ ] `curl https://<render-url>.onrender.com/health` returns `200`
- [ ] Frontend loads at `https://<vercel-url>.vercel.app`
- [ ] Upload + audit flow completes end-to-end using a sample BoL/Invoice/Packing List (included in `backend/tests/fixtures/pdfs/`)
- [ ] `GET /sessions` returns the completed session
- [ ] No secrets appear in Render or Vercel logs (search for `sk-` or the raw Mongo password)
- [ ] CORS from the Vercel domain succeeds; from other origins is rejected

---

## 6. Operational Notes

### 6.1 Render Free Tier

The free tier spins down after 15 minutes of inactivity. First request after a cold start takes 30–60s to wake the service. This is acceptable for a portfolio demo; the README's demo flow should note it or include a "warm up the backend" button.

Alternative: cron-ping the `/health` endpoint every 14 minutes via https://cron-job.org or GitHub Actions on a schedule. Not required.

### 6.2 MongoDB Atlas Free Tier

M0 has 512MB storage. FreightCheck sessions are ~10–20KB each including full trajectory. Portfolio usage is far below any limit. Automatic backups are not included on free tier — also not a concern at this scale.

### 6.3 Gemini API Cost

Budget caps in `settings.py` bound per-session token use. A typical audit consumes 15–25k tokens (≈ $0.0005–0.001 at Gemini 2.5 Flash pricing as of 2026-04). The free tier rate covers development and light production traffic.

### 6.4 Secrets Rotation

- Gemini API key: regenerate in Google AI Studio if leaked. Rotate every 6 months as a practice.
- Mongo password: rotate by creating a new database user with the same permissions, updating `MONGODB_URI` in Render, verifying health, then deleting the old user.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `/health` returns `mongo: disconnected` | `MONGODB_URI` wrong, IP not allowlisted, or cluster suspended | Verify string, check Atlas Network Access, check cluster status |
| `/health` returns `gemini: not_configured` | `GEMINI_API_KEY` env var missing | Set in Render dashboard (prod) or `.env` (local) |
| CORS error in browser | `ALLOWED_ORIGINS` doesn't include the frontend URL | Update and redeploy |
| Upload returns 413 | File > `MAX_FILE_SIZE_MB` | Increase the env var or compress the PDF |
| All audits return `failed` with `GeminiAPIError` | Rate limit hit or key invalid | Check Google AI Studio quota and key status |
| Frontend shows "Network Error" | Wrong `VITE_API_URL` in Vercel | Update env var, redeploy frontend |
| Session stuck in `processing` > 60s | Backend crashed mid-run or Mongo final write failed | Check Render logs; a bug report is warranted |
| Backend cold-start slow on Render free tier | Expected behaviour | Note it on the demo page, or add a warm-up ping |
| `mypy` errors after a deps update | Type stub drift | Pin the problematic dep or update stubs |

### 7.1 Reading Render Logs

```bash
# Via the Render dashboard: Logs tab on the service
# Or via CLI:
render logs -s freightcheck-api --tail
```

Log lines are JSON. Pipe through `jq` to filter:

```bash
render logs -s freightcheck-api --tail | jq 'select(.session_id == "YOUR-SESSION-ID")'
```

### 7.2 Reading Mongo State

```bash
# From a mongo shell connected via MONGODB_URI:
use freightcheck
db.audit_sessions.find({ session_id: "YOUR-SESSION-ID" }).pretty()
```

This shows the full session document including the trajectory, which is often the fastest way to debug a misbehaving audit.

---

## 8. Going Beyond MVP

Not required for the first deploy, but worth noting:

- **Custom domain on Vercel**: add a domain in project settings, update `ALLOWED_ORIGINS` on Render.
- **Render auto-scale**: upgrade from free to a starter plan for multi-instance scale — not useful until traffic justifies it.
- **Mongo shared cluster → dedicated**: when storage or ops needs exceed M0.
- **LangSmith**: add `LANGSMITH_API_KEY` and enable in `logging_config.py` for trace inspection UI.
