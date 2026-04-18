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
- [ ] **M0-2 · Get a Gemini API key.** Create one at
      https://aistudio.google.com and paste it into `backend/.env` as
      `GEMINI_API_KEY`. Required from M2 onwards (extraction calls).
- [ ] **M0-3 · Provision a MongoDB Atlas cluster.** Create the free M0 cluster,
      allow your IP (or `0.0.0.0/0` for dev), create a database user, and paste
      the connection string into `backend/.env` as `MONGODB_URI`. Required
      from M4 onwards (session persistence).
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

---

## Completed

_Nothing completed yet. When you tell me an item is done, I'll move it here
with the date and the milestone it closed out._
