# FreightCheck — Agent Briefing

**Version**: 1.0
**Status**: Active
**Author**: Basit Ali
**Last Updated**: 2026-04-18

---

## Read This First

You are a coding agent building **FreightCheck**, a logistics document auditing system. Before writing any code, read the documents in the order below. The documents are the authoritative specification — when this briefing and a spec disagree, the spec wins. When two specs disagree, the **Data Models** spec wins because it is the single source of truth for every field name, type, and schema.

---

## What You Are Building

FreightCheck accepts three shipping PDFs (Bill of Lading, Commercial Invoice, Packing List), runs a **planner-driven LangGraph agent** that extracts structured fields and cross-validates them, and returns a severity-graded exception report with full agent trajectory.

The system is deliberately agentic: a Gemini-backed planner (via `bind_tools`) decides which validations to run based on what was extracted and how confident it is. All domain logic lives in deterministic tools. Every planner decision and tool call is persisted and exposed via the API.

**Non-negotiables** (if you violate any of these, stop and re-read):
1. **Never invent prompts.** All prompts are defined verbatim in the Prompt Templates spec. If you need a prompt that isn't defined, add it there first, then reference it in code. Do not construct prompts inline in nodes or tools.
2. **Never invent field names.** All extraction and validation field names come from the Data Models spec. Canonical names are the identifiers used everywhere — Pydantic, Mongo, API, TypeScript. No abbreviations, no synonyms.
3. **Never store PDFs.** PDFs are held in memory only during text extraction. Only structured fields, confidence scores, exceptions, and trajectory are persisted.
4. **Never commit secrets.** `.env` is gitignored. `.env.example` is the template. `GEMINI_API_KEY` and `MONGODB_URI` are set in deployment environments only.
5. **Never hallucinate field values.** Extraction prompts require source-grounded output. If a field isn't present in the document, the model returns `null` with low confidence and a rationale — not a guessed value.

---

## Required Reading Order

Read every document completely before starting the milestone that needs it. Do not skim.

| # | Document | Read before starting | Purpose |
|---|---|---|---|
| 1 | `freightcheck_agent_briefing.md` | (this doc) | Entry point, milestones, Definition of Done |
| 2 | `freightcheck_prd.md` | Any work | Scope, non-goals, success criteria — read §1 (Executive Summary) and §2.3 (Non-Goals) in full. The rest is useful context but not line-by-line mandatory |
| 3 | `freightcheck_system_design.md` | Any code | Architecture, component boundaries, error boundaries, deployment topology. §5 is the load-bearing section for the agent |
| 4 | `freightcheck_data_models.md` | Any schema, any code touching fields | **Single source of truth.** Every field name, type, Pydantic model, Mongo doc shape, TS interface |
| 5 | `freightcheck_api_contract.md` | Any backend endpoint or frontend API call | Request/response shapes, status codes, polling logic |
| 6 | `freightcheck_langgraph_flow.md` | Any agent node or edge | Graph definition, per-node contracts, state reducers, tool registry, checkpointing |
| 7 | `freightcheck_prompt_templates.md` | Any Gemini call | **Verbatim prompts.** Extraction, planner, semantic validator, re-extraction, retry, summary. Injection defence wording |
| 8 | `freightcheck_implementation_rules.md` | Any file creation | Folder structure, naming, logging format, config, dependencies |
| 9 | `freightcheck_error_handling.md` | Any node, any tool, any endpoint | Agent-internal errors, retry policy, budget exhaustion, tool dispatch errors |
| 10 | `freightcheck_environment_setup.md` | Local dev, deploy | Env vars, `.env.example`, Mongo setup, Gemini setup, deploy steps |
| 11 | `freightcheck_frontend_spec.md` | Any frontend work | Component tree, pages, state, per-component API calls, styling |
| 12 | `freightcheck_testing_spec.md` | Any test | Unit/integration structure, Gemini mocking, coverage targets, CI |
| 13 | `freightcheck_evaluation_spec.md` | Agent MVP completion | Synthetic generator, eval suites, metrics, pass thresholds |

---

## Build Milestones

Each milestone has a **Definition of Done (DoD)**. Do not claim a milestone complete until every DoD item is checked. Do not start the next milestone until the current one is done.

### Milestone 0 — Repository Setup

**Read**: Agent Briefing, Implementation Rules, Environment & Setup.

**Build**:
- Repo skeleton per Implementation Rules §Folder Structure
- `pyproject.toml` (backend) and `package.json` (frontend) with pinned dependencies from Implementation Rules §Dependencies
- `.env.example`, `.gitignore`, `README.md` (minimal — full README comes in Milestone 7)
- Ruff, Black, pytest configured for backend
- ESLint, Prettier, Vitest configured for frontend
- GitHub Actions: lint + typecheck on PR (no tests yet)

**Definition of Done**:
- [ ] `uv sync` (or `pip install -e .`) succeeds in `backend/`
- [ ] `npm install` succeeds in `frontend/`
- [ ] `ruff check backend/` returns 0 errors
- [ ] `mypy backend/` returns 0 errors
- [ ] `npm run typecheck` in `frontend/` returns 0 errors
- [ ] `.env.example` lists every variable documented in Environment & Setup
- [ ] No secrets committed (check `git log -p`)
- [ ] CI passes on an empty PR

---

### Milestone 1 — Schemas & Data Contracts

**Read**: Data Models (complete), API Contract (complete).

**Build**:
- Every Pydantic model from Data Models §1: `LineItem`, `BoLFields`, `InvoiceFields`, `PackingListFields`, `ExtractionConfidence`, `ExtractedDocument`, `ValidationStatus`, `ExceptionSeverity`, `ValidationResult`, `Evidence`, `ExceptionRecord`, `AuditReport`, `SessionStatus` (including `AWAITING_REVIEW`), `ToolCall`, `PlannerDecision`, `AuditSession`, all API request/response models, `TrajectoryResponse`
- The `AgentState` TypedDict from Data Models §2, exactly as specified
- Every TypeScript interface from Data Models §4 in `frontend/src/types/index.ts`
- Unit tests validating every Pydantic model roundtrips through `.model_dump()` + `.model_validate()`

**Definition of Done**:
- [ ] All model files exist at paths specified by Implementation Rules
- [ ] `pytest backend/tests/test_schemas.py` passes with every model roundtrip tested
- [ ] `mypy backend/` passes
- [ ] TypeScript interfaces compile with `strict: true`
- [ ] Field names in Pydantic, TS, and the Mongo schema example in Data Models §3 are character-identical (no casing drift)

---

### Milestone 2 — PDF Parsing & Upload Endpoint

**Read**: System Design §3.3, API Contract `POST /upload`, Error Handling Spec.

**Build**:
- `services/pdf_parser.py` — PyMuPDF wrapper, in-memory only, `ImageOnlyPDFError` detection
- `POST /upload` endpoint per API Contract
- Short-lived in-memory cache mapping `session_id → raw_texts` (expires in 10 minutes; keyed by uuid4). This is consumed by `POST /audit`
- Unit tests: happy path, non-PDF, oversized file, scanned PDF, corrupted PDF

**Definition of Done**:
- [ ] `curl -F bol=@a.pdf -F invoice=@b.pdf -F packing_list=@c.pdf /upload` returns a valid `UploadResponse`
- [ ] All four error cases (`MissingDocumentError`, `InvalidFileTypeError`, `FileTooLargeError`, `ImageOnlyPDFError`) return the exact error shape from API Contract
- [ ] No file writes to disk during upload (verify via filesystem monitoring in test)
- [ ] `pytest` for the endpoint and parser passes
- [ ] No ruff/mypy errors

---

### Milestone 3 — Agent Tools (No Planner Yet)

**Read**: System Design §5.5, Data Models §5 (Validation Catalogue), Prompt Templates (for semantic validator prompt).

**Build**:
- `agent/tools.py` with every tool defined in System Design §5.5: `validate_field_match`, `validate_field_semantic`, `re_extract_field`, `check_container_consistency`, `check_incoterm_port_plausibility`, `check_container_number_format`, `flag_exception`, `escalate_to_human_review`
- `TOOL_REGISTRY: dict[str, Tool]` containing all of the above, keyed by name
- `services/gemini.py` — Gemini wrapper with retries, token accounting, and injection-defence delimiter helpers
- Unit tests for **every** tool with mocked Gemini (fixtures from Testing Spec)

**Definition of Done**:
- [ ] Every tool in System Design §5.5 exists, is registered in `TOOL_REGISTRY`, and has a docstring copied verbatim from the spec
- [ ] Every tool has at least one unit test for its happy path and one for an edge case
- [ ] `check_container_number_format` correctly validates and rejects ISO 6346 check digits (test with known-good and known-bad numbers from Testing Spec)
- [ ] Gemini wrapper correctly parses retry-on-malformed-JSON behaviour per Error Handling Spec
- [ ] Token accounting on Gemini calls returns non-zero usage in a live test (marked `@pytest.mark.integration`)

---

### Milestone 4 — LangGraph Agent

**Read**: LangGraph Flow Spec (complete), System Design §5 (complete), Prompt Templates (extraction and planner prompts).

**Build**:
- `agent/graph.py` — full LangGraph graph with nodes: `extract_all`, `plan_validations`, `execute_tool`, `reflect`, `compile_report`. Edges exactly as LangGraph Flow Spec §Edges.
- `agent/state.py` — state reducers per LangGraph Flow Spec §Reducers
- `agent/checkpointing.py` — writes `AuditSession` to MongoDB after every node
- Budget enforcement per System Design §5.6 (iterations, tokens, time)
- Integration test: full agent run with mocked Gemini responses, asserting the trajectory matches expected tool-call sequence

**Definition of Done**:
- [ ] Graph compiles (`graph.compile()` returns a Runnable)
- [ ] A happy-path integration test runs end-to-end with mocked Gemini in under 2 seconds
- [ ] Budget exhaustion test: mock Gemini to always return `terminate=false` — verify the graph terminates at `MAX_ITERATIONS` and `compile_report` runs the deterministic baseline
- [ ] Low-confidence test: mock one extraction to return confidence 0.4 — verify `status="awaiting_review"` and `review_reasons` is populated
- [ ] Injection test: inject a malicious prompt string into a raw_text fixture — verify the planner does not produce a tool name outside the registry
- [ ] After every node, the Mongo document reflects the latest state (verified by mocking the Mongo client and asserting write count)

---

### Milestone 5 — API Endpoints

**Read**: API Contract (complete), Error Handling Spec.

**Build**:
- `POST /audit` — creates `AuditSession`, spawns agent as FastAPI background task, returns immediately
- `GET /sessions` — list with pagination-free ordering by `created_at` desc
- `GET /sessions/:id` — full session detail
- `GET /sessions/:id/trajectory` — lightweight trajectory-only response
- CORS configured per System Design §8
- All error shapes from API Contract implemented
- Integration tests for every endpoint covering success, 404, and one error case each

**Definition of Done**:
- [ ] Every endpoint in API Contract exists and returns the documented shape
- [ ] `curl` examples from API Contract work against the running service
- [ ] Polling from a test client completes a full happy-path audit in < 30s against a live Gemini key (marked `@pytest.mark.integration`)
- [ ] OpenAPI docs (`/docs`) render correctly and response schemas match API Contract word-for-word
- [ ] CORS rejects requests from origins not in `ALLOWED_ORIGINS`

---

### Milestone 6 — Frontend

**Read**: Frontend Spec (complete), API Contract (complete).

**Build**: everything in Frontend Spec.

**Definition of Done**:
- [ ] All pages from Frontend Spec §Pages render without console errors
- [ ] Upload → audit → report flow works end-to-end against a running backend
- [ ] Trajectory view renders both planner decisions and tool calls, with correct ordering
- [ ] `awaiting_review` banner appears when status is `awaiting_review`, with `review_reasons` listed
- [ ] Confidence pills appear on fields with confidence < 0.9 and are highlighted distinctly for < 0.5
- [ ] All TypeScript types come from `src/types/index.ts` — no inline interfaces in components
- [ ] Vitest suite passes; coverage meets Testing Spec targets
- [ ] Frontend builds with `npm run build` producing no warnings

---

### Milestone 7 — Evaluation Harness

**Read**: Evaluation Spec (complete).

**Build**:
- `eval/synthetic_generator.py` — deterministic synthetic document set generator per Evaluation Spec
- `eval/suites/` — one file per suite (extraction accuracy, confidence calibration, grounding, mismatch detection, false positive, trajectory correctness, latency, cost)
- `eval/run.py` — CLI entry point; outputs a report per Evaluation Spec §Reporting Format
- CI job that runs the full eval suite on prompt or schema changes

**Definition of Done**:
- [ ] `python -m eval.run` produces a JSON + markdown report for every suite
- [ ] All target metrics from Evaluation Spec meet or exceed pass thresholds (or the failing suite is explicitly documented)
- [ ] Synthetic generator is deterministic: running twice with the same seed produces byte-identical documents
- [ ] CI runs the eval harness and fails if any pass threshold regresses

---

### Milestone 8 — Deployment

**Read**: Environment & Setup, System Design §8.

**Build**:
- Render config for backend (`render.yaml`)
- Vercel config for frontend (`vercel.json`)
- Production env vars set in both platforms
- README with deployed URLs, demo flow, "what interesting thing this caught" example

**Definition of Done**:
- [ ] Backend deployed and responds to `GET /health` (add this endpoint if not already present)
- [ ] Frontend deployed and completes a full audit against the deployed backend
- [ ] README contains: deployed URL, 15-second GIF or screenshot, one concrete example of a caught discrepancy with trajectory
- [ ] No secrets in deployed logs (verified by a log scan)
- [ ] CORS in production only allows the Vercel domain

---

## How You Work

### Before Writing Code

1. Confirm you have read every document listed for the current milestone.
2. Confirm the current milestone's predecessor is DoD-complete.
3. Open the current milestone's section in this doc and re-read the DoD.
4. Make a short plan. If the plan requires any information not in the specs, **stop and ask** rather than invent.

### While Writing Code

1. **If a spec is ambiguous**, prefer the interpretation that is more explicit, more testable, and more conservative. Write a short note in `notes/questions.md` describing the ambiguity and what you chose.
2. **If a spec appears wrong**, do not silently contradict it. Write your concern in `notes/questions.md` and continue using the spec's version. Humans resolve spec conflicts, not you.
3. **Never hardcode values that belong in config** (env vars, budgets, ports, URLs). Config goes in `settings.py` (backend) or `vite.config.ts` (frontend) and is loaded from env.
4. **Never skip a test to "save time".** Testing Spec is part of the DoD. A milestone with failing tests is not done.

### After Writing Code

1. Run every local check (ruff, mypy, pytest, eslint, vitest) before declaring the milestone done.
2. Walk through the milestone's DoD line by line. Uncheck any item you cannot verify.
3. If any DoD item fails, return to code — do not proceed.

---

## When To Stop And Ask

You must stop and ask a human in any of these cases:

- A spec document contradicts another spec document in a way you cannot resolve by reading the priority order (Data Models > others).
- A required environment variable, API key, or external resource is unavailable.
- A test is failing and you cannot determine whether the fix belongs in the code or the spec.
- You would need to invent a prompt, a field name, an endpoint, or a Pydantic model not in any spec.
- You believe a spec is materially wrong (not just ambiguous).
- A dependency version in Implementation Rules is no longer available or has known security issues.

Do not guess. Asking takes less time than unwinding wrong work.

---

## Success Means

The system passes every DoD across all milestones, every eval suite meets its pass threshold, the deployed demo works end-to-end, and the trajectory view makes the agent's decisions fully inspectable to a non-technical user. A freight analyst using the deployed demo should be able to verify the agent's reasoning without reading any code.
