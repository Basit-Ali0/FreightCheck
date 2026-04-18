# FreightCheck — Open Questions & Assumptions Log

This file is where the coding agent records anything it could not resolve
from the specs alone. Humans resolve spec conflicts and ambiguities — the
agent's job is to surface them clearly, not to guess silently.

---

## How to use this file

Add a new entry whenever one of the following happens:

1. **Spec ambiguity** — two reasonable interpretations of a spec line, and
   you had to pick one to keep working.
2. **Spec conflict** — two specs appear to disagree in a way the priority
   rules (Data Models > others) don't cleanly resolve.
3. **Spec gap** — you needed information the specs didn't provide, and you
   made a minimal-blast-radius choice to keep moving.
4. **Possible spec error** — you believe a spec is wrong. Do NOT silently
   contradict it; record your concern and continue following the spec.
5. **Environment gap** — a required secret, account, or tool is missing.
6. **Deferred decision** — something is decided "for now" but should be
   revisited before a later milestone.

Do **not** use this file for:
- Progress notes ("finished M2 today")
- TODO lists for yourself (use the agent's own task tracking)
- Design musings ("wouldn't it be nice if...")

Keep it tight. One entry per issue. Resolved entries stay in the file so
the decision history is searchable.

---

## Entry template

Copy this block for each new entry. Entries are chronological (newest at
the bottom of the Open section).

```
### Q-<NNN>: <short title>

- **Raised**: <YYYY-MM-DD> during <milestone>
- **Type**: ambiguity | conflict | gap | possible-error | environment | deferred
- **Context**: <1–3 sentences on what you were trying to do>
- **Spec references**:
    - `freightcheck_<doc>.md` §<section>: <exact line or paraphrase>
    - `freightcheck_<doc>.md` §<section>: <exact line or paraphrase>
- **What I did**: <the choice you made and why it has the smallest blast
  radius>
- **What I need from a human**: <specific question or decision needed>
- **Blocking?**: yes | no — if yes, you should have stopped instead of
  choosing. Explain why you proceeded.
- **Status**: open | resolved
- **Resolution** (fill in when resolved): <answer> — decided by <who> on
  <YYYY-MM-DD>
```

---

## Open

<!-- New entries go here. Move to "Resolved" when a human answers. -->

### Q-001: "CI passes on empty PR" cannot be verified locally

- **Raised**: 2026-04-18 during M0
- **Type**: environment
- **Context**: M0 DoD (Agent Briefing §Milestone 0) includes the item "CI passes on an empty PR". This requires a GitHub remote with Actions enabled. The local repo was `git init`'d with no remote per user instruction, so this DoD item cannot be verified by the agent.
- **Spec references**:
    - `freightcheck_agent_briefing.md` §"Milestone 0 → Definition of Done": "CI passes on an empty PR"
- **What I did**: Wrote `.github/workflows/ci.yml` with three jobs (backend lint, backend typecheck, frontend lint+typecheck+build), verified each command succeeds locally, and left a `TODO(M2/M3/M6)` comment pointing at Implementation Rules §9.1 for the test-runner extensions added in later milestones. Marked this DoD item as deferred rather than green.
- **What I need from a human**: Create the GitHub remote, push `main`, open an empty PR, and confirm `ci.yml` passes. Report back whether either job needs adjustment for the hosted runner (e.g. uv cache, Node version mismatch).
- **Blocking?**: no — every other M0 DoD item is verified locally; this item is purely a remote-side check.
- **Status**: open

### Q-002: README scope — M0 minimal vs M7 "full" vs M8 deploy

- **Raised**: 2026-04-18 during M0
- **Type**: ambiguity
- **Context**: Agent Briefing §"Milestone 0 → Build" says the repo skeleton includes `README.md` "(minimal — full README comes in Milestone 7)", but M7 is the Evaluation Harness milestone and the README requirements (deployed URL, demo GIF, caught-discrepancy example) appear only in M8's DoD. These three references don't line up.
- **Spec references**:
    - `freightcheck_agent_briefing.md` §"Milestone 0 → Build": "`README.md` (minimal — full README comes in Milestone 7)"
    - `freightcheck_agent_briefing.md` §"Milestone 7 → Build": no README items listed
    - `freightcheck_agent_briefing.md` §"Milestone 8 → Definition of Done": "README contains: deployed URL, 15-second GIF or screenshot, one concrete example..."
- **What I did**: Wrote a minimal M0 README per the explicit M0 wording (project name, 1-line description, pointer to `knowledge/freightcheck_prd.md` and `knowledge/freightcheck_environment_setup.md`). Will expand it in M8 per the M8 DoD. The "full README comes in Milestone 7" line in the M0 briefing appears to be a spec error — following M8 as the authoritative README milestone.
- **What I need from a human**: Confirm the README should be expanded in M8 (not M7). If that's correct, consider correcting the M0 briefing parenthetical to say "Milestone 8".
- **Blocking?**: no
- **Status**: open

### Q-004: ISO 6346 severity — Data Models §5 vs plausible domain intent

- **Raised**: 2026-04-18 during M3
- **Type**: ambiguity
- **Context**: Data Models §5 ("Field-level Validation Rules") lists `container_number_format` as severity **warning**, meaning a bad ISO 6346 check digit maps to `minor_mismatch` rather than `critical_mismatch`. In practice an invalid check digit almost always indicates a transcription error on a document that downstream parties (carrier, customs) treat as a hard stop, so "warning" feels low.
- **Spec references**:
    - `freightcheck_data_models.md` §5 "Field-level Validation Rules": container_number_format → warning
    - `freightcheck_data_models.md` §5: "Severity catalogue is the single source of truth for tool-generated results."
- **What I did**: Followed the spec verbatim — `check_container_number_format` returns `minor_mismatch` on an ISO 6346 check-digit failure. The only escalation path is a missing list on **both** BoL and Packing List, which returns `critical_mismatch` (because with no containers to validate, downstream audit steps collapse). Logged M3-3 in `manual_steps.md` so the severity can be re-examined before M5 (planner) ships.
- **What I need from a human**: Confirm the `minor_mismatch` mapping stays, or update Data Models §5 to bump `container_number_format` to `critical`. Either is a one-line change.
- **Blocking?**: no
- **Status**: open

### Q-003: Tailwind color hex values not specified

- **Raised**: 2026-04-18 during M0
- **Type**: gap
- **Context**: Implementation Rules §4.5 requires Tailwind color tokens `severity-critical`, `severity-warning`, `severity-info`, `confidence-low`, `confidence-medium`, `confidence-high`, but gives no hex values. Frontend Spec will likely specify them in M6.
- **Spec references**:
    - `freightcheck_implementation_rules.md` §4.5: "Colour palette defined in `tailwind.config.js` with named tokens: `severity-critical`, `severity-warning`, `severity-info`, `confidence-low`, `confidence-medium`, `confidence-high`."
- **What I did**: Picked conservative defaults in `frontend/tailwind.config.js` (red-600 / amber-600 / sky-600 / green-700). These are placeholders; the design token values should be confirmed against the Frontend Spec color specification in M6 before building components.
- **What I need from a human**: No immediate action. Flag for M6 design review.
- **Blocking?**: no
- **Status**: open

---

## Resolved

<!-- Move entries here once they are answered. Keep them for history. -->
