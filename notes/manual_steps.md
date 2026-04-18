# Manual Steps — Human Actions Required

This file tracks every action that requires a human (not the agent) to complete.
Items remain here until you tell me they are done, at which point I move them to
the **Completed** section at the bottom with a date.

Each item is tagged with the milestone that surfaced it. Nothing here blocks the
agent from implementing the next milestone unless explicitly noted.

---

## Open

### From Milestone 0 — Repository Setup

- [ ] **M0-4 · Confirm Tailwind severity / confidence color hex values.**
      `frontend/tailwind.config.js` currently uses conservative Tailwind
      palette defaults for `severity.{critical,warning,info}` and
      `confidence.{low,medium,high}` because the spec did not fix exact hex
      values (tracked as Q-003 in `notes/questions.md`). Swap in brand colors
      whenever convenient before M6 (UI build).

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

- **2026-04-18 · M0-1 · Push repo to GitHub.** Remote added at
  `https://github.com/Basit-Ali0/FreightCheck.git`; CI run
  [24610743391](https://github.com/Basit-Ali0/FreightCheck/actions/runs/24610743391)
  on commit `c4a38af` passed both jobs (backend lint+typecheck, frontend
  lint+typecheck+build). Closes Q-001. The first push also caught a
  real bug — `ruff format --check` flagged `settings.py` — fixed in
  commit `c4a38af`.
- **2026-04-18 · M0-2 · Get a Gemini API key.** Key pasted into
  `backend/.env`; live Gemini integration test
  (`tests/integration/test_gemini_live.py`) passed with a 688-token round
  trip, closing out the M3-1 Testing Spec §4.1 DoD check simultaneously.
- **2026-04-18 · M0-3 · Provision a MongoDB Atlas cluster.** Connection
  string pasted into `backend/.env`. Not exercised yet — M4 persistence
  code will be the first consumer.
- **2026-04-18 · M0-5 · Confirm README scope.** Decided: README stays
  minimal through M7 and gets the full treatment (deployed URL, demo
  GIF, discrepancy example) in M8 per the M8 DoD. Q-002 resolved.
- **2026-04-18 · M3-1 · Run the live Gemini integration test once
  locally.** `uv run pytest tests/integration/test_gemini_live.py -m
  integration -v -s` — PASSED, `tokens_used=688`.
- **2026-04-18 · M3-2 · Confirm Gemini model name & generation
  settings.** Decided: stay on `gemini-2.5-flash` with `temperature=0.0`
  and `response_mime_type="application/json"` for the life of the
  project. `GEMINI_MODEL` in `backend/.env` can still override per
  environment.
