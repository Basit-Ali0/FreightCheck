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

### Q-004: ISO 6346 severity — Data Models §5 vs plausible domain intent

- **Raised**: 2026-04-18 during M3
- **Type**: ambiguity
- **Context**: Data Models §5 ("Field-level Validation Rules") lists `container_number_format` as severity **warning**. The concern was whether `check_container_number_format` should instead return `minor_mismatch` on a bad ISO 6346 check digit, or escalate to `critical_mismatch`, because in practice downstream parties (carrier, customs) treat an invalid container number as a hard stop.
- **Spec references**:
  - `freightcheck_data_models.md` §5 "Field-level Validation Rules": container_number_format → warning
  - `freightcheck_data_models.md` §5: "Severity catalogue is the single source of truth for tool-generated results."
- **What I did**: Initially emitted a `ValidationResult` with `minor_mismatch`. That conflated two axes — `ValidationResult.status` (match / minor / critical) describes a field-comparison outcome across two documents, whereas `ExceptionRecord.severity` (critical / warning / info) is what the user sees on the report. `check_container_number_format` is a single-document sanity check, not a comparison, so it belongs on the `ExceptionRecord` axis.
- **What I need from a human**: N/A — resolved below.
- **Blocking?**: no
- **Status**: resolved
- **Resolution**: Refactored `check_container_number_format` to emit one `ExceptionRecord` per bad container with `severity = ExceptionSeverity.WARNING`. Rationale: a bad ISO 6346 check digit is almost always a transcription typo, not cross-document conflict, and `critical` must stay reserved for inter-document contradictions (CIF vs FOB, different container sets, quantity mismatches) so it doesn't lose its meaning. Data Models §5 already records `container_number_format → warning` so no spec change was needed. Commit `10c9475`. Decided by Basit on 2026-04-18.

### Q-005: `google-generativeai` SDK is deprecated; should we migrate to `google-genai`?

- **Raised**: 2026-04-18 during M3 live test
- **Type**: possible-error
- **Context**: Running the M3-1 live integration test emitted a `FutureWarning`: "All support for the `google.generativeai` package has ended. It will no longer be receiving updates or bug fixes. Please switch to the `google.genai` package as soon as possible." Environment Setup §3.2 originally pinned `google-generativeai`.
- **Spec references**:
  - `freightcheck_environment_setup.md` §3.2 (pre-migration): `google-generativeai = "^0.8.3"`
  - `freightcheck_implementation_rules.md` §2.2 (post-migration): `google-genai>=1.0`
- **What I did**: N/A — resolved immediately; see resolution.
- **What I need from a human**: N/A.
- **Blocking?**: no
- **Status**: resolved
- **Resolution**: Migrated in M3 before the planner milestone lands. Only one file touches the SDK (`backend/src/freightcheck/services/gemini.py`) so the diff is contained and every downstream milestone (M4 agent, M7 eval, M8 deploy) consumes the new wrapper from day one — cheaper than migrating later and re-running the eval harness. Implementation Rules §2.2 pin switched to `google-genai>=1.0` (commit `f7e9431`, doc-only). Wrapper rewritten to use `google.genai.Client(...)` / `client.aio.models.generate_content(...)` / `google.genai.types.GenerateContentConfig` with `errors.APIError.code` driving retry (429 / 5xx via a frozen `_RETRYABLE_STATUS_CODES` set). Committed atomically as `f5df377`. Unit tests (114) untouched — they only stub `_raw_gemini_call`. Live integration test passed with no `FutureWarning`. Installed version: `google-genai==1.73.1`. Decided by Basit on 2026-04-18.

### Q-006: Enum pattern — `class X(str, Enum)` vs `StrEnum`

- **Raised**: 2026-04-18 during M1
- **Type**: deferred
- **Context**: Python 3.11+ offers `enum.StrEnum`, which is marginally cleaner than the spec's `class X(str, Enum)` pattern in `freightcheck_data_models.md`. Ruff's `UP042` flagged the schema file for it, so the backend `pyproject.toml` carries a per-file `UP042` ignore to keep the code literally matching the spec.
- **Spec references**:
  - `freightcheck_data_models.md` (every enum declaration): `class SessionStatus(str, Enum):`, `class DocumentType(str, Enum):`, `class ValidationStatus(str, Enum):`, `class ExceptionSeverity(str, Enum):`
  - `freightcheck_agent_briefing.md` "no silent spec drift" rule
- **What I did**: Kept the spec's literal pattern. Agent Briefing forbids silently "improving" the spec.
- **What I need from a human**: No action. Purely cosmetic; zero behavioural impact.
- **Blocking?**: no
- **Status**: deferred (post-MVP, possibly never)
- **Resolution**: Deferred. If migration is ever done, the sequence is: (1) update Data Models spec to `StrEnum` across all enum declarations, (2) log the spec change here, (3) swap the three base classes in `backend/src/freightcheck/schemas/audit.py` and delete the `UP042` ignore in `pyproject.toml`. Tracked in `notes/manual_steps.md` under "Deferred". Decided by Basit on 2026-04-18.

### Q-001: "CI passes on empty PR" cannot be verified locally

- **Raised**: 2026-04-18 during M0
- **Type**: environment
- **Context**: M0 DoD (Agent Briefing §Milestone 0) includes the item "CI passes on an empty PR". This requires a GitHub remote with Actions enabled. The local repo was `git init`'d with no remote per user instruction, so this DoD item cannot be verified by the agent.
- **Spec references**:
  - `freightcheck_agent_briefing.md` §"Milestone 0 → Definition of Done": "CI passes on an empty PR"
- **What I did**: Wrote `.github/workflows/ci.yml` with three jobs (backend lint, backend typecheck, frontend lint+typecheck+build), verified each command succeeds locally, and left a `TODO(M2/M3/M6)` comment pointing at Implementation Rules §9.1 for the test-runner extensions added in later milestones. Marked this DoD item as deferred rather than green.
- **What I need from a human**: Create the GitHub remote, push `main`, open an empty PR, and confirm `ci.yml` passes. Report back whether either job needs adjustment for the hosted runner (e.g. uv cache, Node version mismatch).
- **Blocking?**: no — every other M0 DoD item is verified locally; this item is purely a remote-side check.
- **Status**: resolved
- **Resolution**: Repo pushed to `https://github.com/Basit-Ali0/FreightCheck.git` on 2026-04-18. CI run [24610743391](https://github.com/Basit-Ali0/FreightCheck/actions/runs/24610743391) on commit `c4a38af` passed both jobs. First push failed on `ruff format --check src/freightcheck/settings.py` (formatting drift from the same-day settings edit) — fixed and re-pushed. Remaining annotations are Node.js 20 deprecation notices from `actions/checkout@v4`, `astral-sh/setup-uv@v3`, and `actions/setup-node@v4`; non-blocking through June 2026 per GitHub's timeline. Decided by Basit on 2026-04-18.

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
- **Status**: resolved
- **Resolution**: Confirmed — README stays minimal through M7 and gets the full treatment (deployed URL, demo GIF/screenshot, one concrete caught-discrepancy example) in M8 per that milestone's DoD. The "Milestone 7" wording in the M0 briefing is a spec typo. Decided by Basit on 2026-04-18.

