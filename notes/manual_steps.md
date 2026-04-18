# Manual Steps — Human Actions Required

This file tracks every action that requires a human (not the agent) to complete.
Items remain here until you tell me they are done, at which point I move them to
the **Completed** section at the bottom with a date.

Each item is tagged with the milestone that surfaced it. Nothing here blocks the
agent from implementing the next milestone unless explicitly noted.

---

## Open

### From Milestone 0 — Repository Setup

- [ ] **M0-1 · Push repo to GitHub.** Create a `freightcheck` repository on
      GitHub and push the local `main` branch. Needed to verify the
      `.github/workflows/ci.yml` CI pipeline actually runs green on a PR
      (tracked as Q-001 in `notes/questions.md`).
- [ ] **M0-4 · Confirm Tailwind severity / confidence color hex values.**
      `frontend/tailwind.config.js` currently uses conservative Tailwind
      palette defaults for `severity.{critical,warning,info}` and
      `confidence.{low,medium,high}` because the spec did not fix exact hex
      values (tracked as Q-003 in `notes/questions.md`). Swap in brand colors
      whenever convenient before M6 (UI build).
- [ ] **M0-5 · Confirm README scope.** Current `README.md` is M0-minimal
      (project name + links). The "full setup instructions" section is planned
      for M7/M8 (tracked as Q-002). Tell me if you want it expanded earlier.

### From Milestone 1 — Schemas & Data Contracts

- [ ] **M1-1 · (Optional) Migrate enums to `StrEnum`.** Enums in
      `backend/src/freightcheck/schemas/audit.py` follow the spec's literal
      `class X(str, Enum)` pattern. `pyproject.toml` carries a per-file
      `UP042` ignore for this file as a result. If you want to modernise, swap
      the three base classes to `enum.StrEnum` and delete the ignore — no
      behavioural change. Not blocking.

### From Milestone 2 — PDF Parsing & Upload Endpoint

- [ ] **M2-1 · Smoke-test `POST /upload` with real PDFs.** The DoD calls for a
      `curl -F bol=@a.pdf -F invoice=@b.pdf -F packing_list=@c.pdf /upload`
      check. Automated tests cover this end-to-end with synthetic PDFs
      generated via PyMuPDF, but a one-time manual run against three real
      shipping PDFs is worth doing before M5 ships the audit endpoint. From
      `backend/`: `uv run uvicorn freightcheck.main:app --reload` then
      `curl -F bol=@path/to/bol.pdf -F invoice=@... -F packing_list=@... \
      http://localhost:8000/upload`. Expect a 200 with `session_id`,
      `documents_received`, and non-zero `raw_text_lengths` per doc.
- [ ] **M2-2 · Decide on `MAX_FILE_SIZE_MB` for production.** Default is 10 MB
      (Implementation Rules section 2.5). Some BoLs can be larger. Adjust in
      Render env vars if you see `FileTooLargeError` in production logs.

### From Milestone 3 — Agent Tools & Gemini Wrapper

- [ ] **M3-2 · Confirm Gemini model name & generation settings.** The wrapper
      defaults to `gemini-2.5-flash` with `temperature=0.0` and
      `response_mime_type="application/json"` (matching the Environment Setup
      spec). If you want a different model (`gemini-2.5-pro`, `-flash-lite`,
      etc.) override `GEMINI_MODEL` in `backend/.env` or pass `model=...`
      explicitly at call sites.
- [ ] **M3-3 · Review ISO 6346 tolerance policy.** `check_container_number_format`
      currently downgrades an invalid check digit to `minor_mismatch` per Data
      Models §5's warning-only catalogue entry, but a missing container list
      on both BoL and Packing List returns `critical_mismatch`. Confirm that
      matches your audit policy before M5 — the LangGraph planner will escalate
      accordingly.
- [ ] **M3-4 · Decide whether to migrate off `google-generativeai`.** The live
      Gemini test surfaced a `FutureWarning`: the `google-generativeai` SDK
      is EOL upstream and the replacement is `google-genai`. Pinning stays as
      specified in Environment Setup §3.2 for now. Tracked as Q-005 in
      `notes/questions.md`. Tell me to migrate and I'll swap the client in
      `backend/src/freightcheck/services/gemini.py` (contained diff).

---

## Completed

- **2026-04-18 · M0-2 · Get a Gemini API key.** Key pasted into
  `backend/.env`; live Gemini integration test
  (`tests/integration/test_gemini_live.py`) passed with a 688-token round
  trip, closing out the M3-1 Testing Spec §4.1 DoD check simultaneously.
- **2026-04-18 · M0-3 · Provision a MongoDB Atlas cluster.** Connection
  string pasted into `backend/.env`. Not exercised yet — M4 persistence
  code will be the first consumer.
- **2026-04-18 · M3-1 · Run the live Gemini integration test once
  locally.** `uv run pytest tests/integration/test_gemini_live.py -m
  integration -v -s` — PASSED, `tokens_used=688`.
