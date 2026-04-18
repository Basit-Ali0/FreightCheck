# Manual Steps — Human Actions Required

This file tracks every action that requires a human (not the agent) to complete.
Items remain here until you tell me they are done, at which point I move them to
the **Completed** section at the bottom with a date.

Each item is tagged with the milestone that surfaced it. Nothing here blocks the
agent from implementing the next milestone unless explicitly noted.

---

## Open

_No open manual steps. All M0–M3 items are resolved. New items will land
here as later milestones surface them._

---

## Deferred (post-MVP)

- **M1-1 · Migrate enums to `StrEnum`.** Deferred to post-MVP per the
  Agent Briefing's "no silent spec drift" rule. If the project ever
  chooses to modernise, the correct sequence is:
  1. Update `freightcheck_data_models.md` to use `enum.StrEnum` in every
     enum declaration.
  2. Log the change in `notes/questions.md`.
  3. Swap `class X(str, Enum)` → `class X(StrEnum)` in
     `backend/src/freightcheck/schemas/audit.py` and delete the
     `UP042` per-file ignore in `pyproject.toml`.
  Purely cosmetic; zero behavioural impact. Tracked as Q-006.

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
- **2026-04-18 · M0-4 · Confirm Tailwind severity / confidence color
  hex values.** Decided: keep the agent's picks
  (severity critical/warning/info = red-600 / amber-600 / sky-600,
  confidence low/medium/high = red-600 / amber-600 / green-700).
  `freightcheck_frontend_spec.md §6.1` updated so spec matches code
  (severity-info: blue-600 → sky-600; confidence-high: green-600 →
  green-700). Q-003 remains open for the M6 review of the broader
  palette (severity-passed, status-*, confidence-very-low) that the
  spec lists but the code hasn't implemented yet.
- **2026-04-18 · M2-1 · Smoke-test `POST /upload` with real PDFs.**
  Deferred. M2 DoD is satisfied by the synthetic fixtures in
  `tests/fixtures/pdfs/`; this curl check is not a milestone gate. Will
  be done informally after M5 once `/upload → /audit → /sessions/:id`
  is wired end-to-end. Systematic real-document testing belongs to M7's
  eval harness.
- **2026-04-18 · M2-2 · Decide on `MAX_FILE_SIZE_MB` for production.**
  Decided: keep the default 10 MB. Raise only on an actual user report
  of `FileTooLargeError`; the value is env-driven so the bump is a
  one-line Render change, no redeploy.
- **2026-04-18 · M3-3 · Review ISO 6346 tolerance policy.** Decided:
  severity `warning`, not `minor_mismatch`. An invalid ISO 6346 check
  digit is a single-document transcription-typo anomaly, not a
  cross-document contradiction, and must not dilute the `critical`
  severity Data Models §5 reserves for inter-document conflicts.
  `check_container_number_format` was refactored to emit one
  `ExceptionRecord` per bad container (severity `warning`) rather than
  a `ValidationResult`. Data Models §5 already records
  `container_number_format → warning`, so no spec change was needed.
  Q-004 resolved.
- **2026-04-18 · M3-4 · Migrate `google-generativeai` → `google-genai`.**
  Done. `knowledge/freightcheck_implementation_rules.md §2.2` pins
  `google-genai>=1.0`. `backend/src/freightcheck/services/gemini.py`
  rewritten to use `google.genai.Client(...)` / `client.aio.models.
  generate_content(...)` / `google.genai.types.GenerateContentConfig`.
  Error-mapping layer switched to `errors.APIError.code` with
  `_RETRYABLE_STATUS_CODES` (429 / 5xx) driving retry. Unit tests
  (114 passed, zero changes needed — they only touch `_raw_gemini_call`
  via monkeypatch). Live integration test passed at commit `f5df377`
  with no `FutureWarning` this time. Installed version:
  `google-genai==1.73.1`. Q-005 resolved.
- **2026-04-19 · M4 · LangGraph agent (graph + checkpoint mirror).**
  Implemented `build_graph()` / `make_initial_state()` per LangGraph
  Flow Spec: nodes `extract_all`, `plan_validations`, `execute_tool`,
  `reflect`, `compile_report`; conditional routing from `reflect`;
  `AgentState` reducers in `agent/state.py`; tool dispatcher in
  `agent/dispatcher.py`; `MongoMirroringSaver` (in-memory LangGraph
  checkpoints + optional sync Mongo callback) in
  `agent/checkpointing.py`. Extraction response schemas in
  `schemas/documents.py`; planner output schema in `schemas/planner.py`.
  Integration tests in `tests/integration/test_agent_graph.py` (mocked
  Gemini): happy path, iteration cap, low-confidence `awaiting_review`,
  unknown-tool injection, checkpoint write count. No new human-only
  steps for M4 — M5 will wire `POST /audit` and real Mongo persistence.
