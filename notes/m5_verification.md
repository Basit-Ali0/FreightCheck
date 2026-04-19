# M5 verification

## Non-live (CI / local without Gemini)

Run from repo root using the backend virtualenv (or any environment where `pytest` and app dev dependencies are installed):

```bash
cd backend && pytest tests/integration/test_api_endpoints.py --tb=short
```

The live M5 file (`test_audit_live_m5.py`) self-skips when Gemini/Mongo are not configured for live use; you can still run it in CI to confirm skip behavior:

```bash
cd backend && pytest tests/integration/test_audit_live_m5.py --tb=short
```

## Live (`/upload` → `/audit` → trajectory poll → session detail)

Requires real **`GEMINI_API_KEY`**, **`MONGODB_URI`**, and any other env vars your deployment expects.

```bash
cd backend && pytest tests/integration/test_audit_live_m5.py -m integration --tb=short
```

**Status:** treat M5 as **not fully DoD-verified live** until this command has been run successfully in an environment with valid credentials.
