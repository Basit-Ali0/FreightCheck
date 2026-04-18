# FreightCheck — Implementation Rules

**Version**: 1.0
**Status**: Draft
**Author**: Basit Ali
**Last Updated**: 2026-04-18

---

## Purpose

Folder structure, naming conventions, coding patterns, dependency versions, logging format, and observability expectations. The coding agent must follow these rules exactly — inconsistency between files makes the codebase harder to navigate and review.

---

## 1. Repository Layout

```
FreightCheck/
├── knowledge/                      # All specs (this folder)
│   ├── freightcheck_agent_briefing.md
│   ├── freightcheck_prd.md
│   └── ...
├── backend/
│   ├── pyproject.toml
│   ├── uv.lock                     # or poetry.lock
│   ├── .env.example
│   ├── Dockerfile
│   ├── src/
│   │   └── freightcheck/
│   │       ├── __init__.py
│   │       ├── main.py              # FastAPI app entry
│   │       ├── settings.py          # pydantic-settings loader
│   │       ├── logging_config.py    # structured logger setup
│   │       ├── api/
│   │       │   ├── __init__.py
│   │       │   ├── upload.py
│   │       │   ├── audit.py
│   │       │   ├── sessions.py
│   │       │   └── health.py
│   │       ├── schemas/
│   │       │   ├── __init__.py
│   │       │   ├── documents.py     # BoLFields, InvoiceFields, etc.
│   │       │   ├── audit.py         # ValidationResult, ExceptionRecord, etc.
│   │       │   ├── agent.py         # ToolCall, PlannerDecision
│   │       │   └── api.py           # request/response models
│   │       ├── services/
│   │       │   ├── __init__.py
│   │       │   ├── pdf_parser.py
│   │       │   ├── gemini.py
│   │       │   ├── mongo.py
│   │       │   └── upload_cache.py
│   │       └── agent/
│   │           ├── __init__.py
│   │           ├── graph.py          # build_graph()
│   │           ├── state.py          # AgentState + reducers
│   │           ├── prompts.py        # every prompt string
│   │           ├── tools.py          # tool definitions + TOOL_REGISTRY
│   │           ├── dispatcher.py     # tool dispatch helper
│   │           ├── checkpointing.py  # MongoCheckpointer
│   │           ├── nodes/
│   │           │   ├── __init__.py
│   │           │   ├── extract_all.py
│   │           │   ├── plan_validations.py
│   │           │   ├── execute_tool.py
│   │           │   ├── reflect.py
│   │           │   └── compile_report.py
│   │           └── edges.py          # conditional edge logic
│   ├── tests/
│   │   ├── unit/
│   │   │   ├── test_schemas.py
│   │   │   ├── test_pdf_parser.py
│   │   │   ├── test_tools.py
│   │   │   └── ...
│   │   ├── integration/
│   │   │   ├── test_agent_happy_path.py
│   │   │   ├── test_api_endpoints.py
│   │   │   └── ...
│   │   ├── fixtures/
│   │   │   ├── pdfs/                 # small test PDFs
│   │   │   └── gemini_responses/     # mocked Gemini outputs
│   │   └── conftest.py
│   └── eval/
│       ├── __init__.py
│       ├── run.py                    # CLI entry
│       ├── synthetic_generator.py
│       ├── suites/
│       │   ├── extraction_accuracy.py
│       │   ├── confidence_calibration.py
│       │   ├── grounding.py
│       │   ├── mismatch_detection.py
│       │   ├── false_positive.py
│       │   ├── trajectory_correctness.py
│       │   ├── latency.py
│       │   ├── cost.py
│       │   └── injection_defence.py
│       └── reports/                  # gitignored
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── .env.example
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/
│       │   ├── client.ts              # fetch wrapper
│       │   ├── upload.ts
│       │   ├── audit.ts
│       │   └── sessions.ts
│       ├── types/
│       │   └── index.ts               # every TS interface from Data Models
│       ├── pages/
│       │   ├── UploadPage.tsx
│       │   ├── SessionsPage.tsx
│       │   └── SessionDetailPage.tsx
│       ├── components/
│       │   ├── UploadSlot.tsx
│       │   ├── RunAuditButton.tsx
│       │   ├── ProcessingView.tsx
│       │   ├── ReportView.tsx
│       │   ├── ExceptionCard.tsx
│       │   ├── ConfidencePill.tsx
│       │   ├── ReviewBanner.tsx
│       │   ├── TrajectoryTimeline.tsx
│       │   ├── ToolCallRow.tsx
│       │   ├── PlannerDecisionCard.tsx
│       │   ├── SessionListRow.tsx
│       │   └── ErrorDisplay.tsx
│       ├── hooks/
│       │   ├── usePollSession.ts
│       │   └── usePollTrajectory.ts
│       ├── state/
│       │   └── uploadState.ts         # Zustand store for upload flow
│       ├── styles/
│       │   └── globals.css
│       └── tests/                      # mirrors src/ structure
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── eval.yml
├── .gitignore
└── README.md
```

---

## 2. Backend — Python Conventions

### 2.1 Python Version

**Python 3.11+ only.** Required for the `|` union syntax in type hints, `TypedDict` features, and `asyncio.TaskGroup`.

### 2.2 Dependencies

Dependency manager: **`uv`** (preferred) or Poetry. Versions below are pinned minimums — use the latest patch of each.

```toml
# pyproject.toml
[project]
name = "freightcheck"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "pymongo>=4.10",
    "motor>=3.6",                      # async Mongo driver
    "pymupdf>=1.24",
    "google-genai>=1.0",
    "langgraph>=0.2",
    "langchain-core>=0.3",
    "structlog>=24.4",
    "python-multipart>=0.0.12",        # for FastAPI file uploads
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "ruff>=0.7",
    "mypy>=1.13",
    "httpx>=0.27",                     # for test client
    "respx>=0.21",                     # for HTTP mocking
]
```

### 2.3 Naming

| Thing | Convention | Example |
|---|---|---|
| Module files | `snake_case.py` | `pdf_parser.py` |
| Classes | `PascalCase` | `BoLFields` |
| Functions, methods | `snake_case` | `extract_fields()` |
| Constants | `UPPER_SNAKE` | `MAX_ITERATIONS` |
| Env vars | `UPPER_SNAKE` | `GEMINI_API_KEY` |
| Pydantic field names | `snake_case`, matches Data Models exactly | `bill_of_lading_number` |
| LangGraph node names (strings) | `snake_case` | `"plan_validations"` |
| Tool names (strings, match function name) | `snake_case` | `"validate_field_match"` |
| Test files | `test_<thing>.py` | `test_tools.py` |
| Test functions | `test_<behaviour>` | `test_extract_bol_happy_path` |

### 2.4 Code Style

- **Formatter**: `ruff format` (configured via `pyproject.toml` to match Black style).
- **Linter**: `ruff check` with rules `E, F, I, N, UP, B, A, C4, PT, SIM, RET, ARG, PL, RUF`.
- **Line length**: 100.
- **Type hints**: every public function and method must be fully typed. Private helpers may omit types only when obvious. `mypy --strict` must pass.
- **Imports**: one import per line; absolute imports only (no relative `from ..foo import bar`); ordered by `ruff` (stdlib → third-party → first-party).
- **Docstrings**: every public function and class has a one-line summary docstring. Tools (the `@tool`-decorated functions) have docstrings copied verbatim from System Design §5.5 — these are read by the LLM.
- **f-strings** preferred over `.format()`, except for prompt templates (which use `.format()` to be explicit about placeholders).

### 2.5 Config Management

All config lives in `settings.py` via `pydantic-settings`:

```python
# backend/src/freightcheck/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # API
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]
    MAX_FILE_SIZE_MB: int = 10

    # Mongo
    MONGODB_URI: str
    MONGODB_DB: str = "freightcheck"

    # Gemini
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_MAX_RETRIES: int = 2

    # Agent budgets
    AGENT_MAX_ITERATIONS: int = 8
    AGENT_TOKEN_BUDGET: int = 50_000
    AGENT_TIME_BUDGET_MS: int = 25_000

    # Upload cache
    UPLOAD_CACHE_TTL_SECONDS: int = 600

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "json"

settings = Settings()
```

**Rules**:
- Never read `os.environ` anywhere except `settings.py`.
- Never hardcode a value that has a setting (ports, budgets, URLs, model names).
- `settings` is a module-level singleton imported as `from freightcheck.settings import settings`.

### 2.6 Async Rules

- All FastAPI endpoints: `async def`.
- All Gemini calls: async (use the SDK's async API; wrap with `asyncio.to_thread` if the SDK is sync-only).
- All Mongo calls: use Motor (async), not PyMongo directly.
- `extract_all` fans out via `asyncio.gather`.
- Node functions in LangGraph are `async def`.

### 2.7 Error Patterns

- Never use bare `except:`. Always catch a specific exception class.
- Custom exceptions live in `freightcheck/errors.py` (see Error Handling Spec).
- Every exception raised to FastAPI must be mapped to an HTTP status via an exception handler.
- Inside agent tools, exceptions are **not raised** out — they are returned as a failed `ToolCall`. See LangGraph Flow Spec §5.

---

## 3. Backend — Logging & Observability

### 3.1 Logger Setup

Use `structlog` configured for JSON output in production and console output locally:

```python
# backend/src/freightcheck/logging_config.py
import logging, structlog
from freightcheck.settings import settings

def configure_logging():
    logging.basicConfig(level=settings.LOG_LEVEL, format="%(message)s")
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if settings.LOG_FORMAT == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL)
        ),
        cache_logger_on_first_use=True,
    )

log = structlog.get_logger()
```

### 3.2 Required Log Events

Every one of these events must be logged. Missing any is a DoD failure for the relevant milestone.

| Event | Where | Fields |
|---|---|---|
| `api.request` | FastAPI middleware | method, path, status, duration_ms, session_id (if present) |
| `upload.received` | upload endpoint | session_id, bytes_received, files_count |
| `upload.parsed` | upload endpoint | session_id, per-doc raw_text_length, duration_ms |
| `agent.started` | audit endpoint | session_id |
| `agent.node_entered` | every node (middleware-style) | session_id, node_name, iteration_count |
| `agent.node_completed` | every node | session_id, node_name, duration_ms, tokens_used (delta) |
| `agent.gemini_call` | Gemini wrapper | session_id, prompt_name, prompt_version, tokens_used, duration_ms, retry_count |
| `agent.tool_dispatched` | dispatcher | session_id, tool_name, tool_call_id, iteration, status, duration_ms |
| `agent.planner_decision` | plan_validations | session_id, iteration, chosen_tool_count, terminate |
| `agent.budget_exhausted` | reflect | session_id, reason (iterations/tokens/time), iteration_count, tokens_used, elapsed_ms |
| `agent.completed` | compile_report | session_id, status, critical_count, warning_count, elapsed_ms, tokens_used |
| `agent.error` | any node setting error | session_id, error_type, error_message, node_name |
| `mongo.write` | every Mongo write | session_id, collection, operation, duration_ms |
| `mongo.error` | Mongo failure | session_id, operation, error |

### 3.3 Correlation

Every log line emitted during a request must include `session_id`. Use `structlog.contextvars.bind_contextvars(session_id=...)` at the start of the request handler and node entry.

### 3.4 No Print Statements

`print()` is not allowed in committed code. `ruff` is configured to flag it. Use `log.info(...)` for everything.

### 3.5 LangSmith (Optional, v1.1)

LangSmith tracing is not enabled in MVP. When added in v1.1, the setup will go in `logging_config.py` guarded by a `LANGSMITH_API_KEY` env var — absence of the key silently disables tracing.

---

## 4. Frontend — TypeScript Conventions

### 4.1 Stack

| Thing | Choice | Version |
|---|---|---|
| Language | TypeScript 5.6+ with `strict: true` | |
| Framework | React 18 | |
| Build | Vite 5+ | |
| Styling | Tailwind CSS 3+ | |
| State management | **Zustand** for cross-page state (upload flow); React useState/useReducer for local | |
| HTTP client | Native `fetch` wrapped in `api/client.ts` — no axios, no React Query for MVP | |
| Routing | React Router 6+ | |
| Testing | Vitest + React Testing Library | |
| Lint | ESLint with `@typescript-eslint`, `react`, `react-hooks` plugins | |
| Format | Prettier | |

No React Query in MVP. Polling is handled by hooks in `hooks/` with simple `setInterval` + cleanup.

### 4.2 Naming

| Thing | Convention | Example |
|---|---|---|
| Component files | `PascalCase.tsx` | `UploadSlot.tsx` |
| Hook files | `camelCase.ts`, prefix `use` | `usePollSession.ts` |
| Other TS files | `camelCase.ts` | `client.ts` |
| Component names | `PascalCase` | `UploadSlot` |
| Props interfaces | `{ComponentName}Props` | `UploadSlotProps` |
| Custom hook names | `camelCase`, prefix `use` | `usePollSession` |
| Types (shared from Data Models) | `PascalCase`, identical to Pydantic model names | `BoLFields`, `ExceptionRecord` |
| Event handlers | `on{Event}` in props, `handle{Event}` in implementation | `onUpload`, `handleUpload` |

### 4.3 File Rules

- **One component per file.** Filename matches the default export name.
- **No default exports for utility functions or hooks.** Named exports only. Components use default exports.
- **All TS types from the data contract come from `src/types/index.ts`.** Do not define `interface BoLFields` anywhere else. If a component needs a prop that is a subset of a shared type, use `Pick<T, ...>` or inline structural types — but never redefine.
- **No `any`.** `unknown` is acceptable. If the backend returns data that TS cannot fully type, use `unknown` + a Zod parser (add Zod as dep only when introduced).

### 4.4 Component Structure

```tsx
// src/components/ExceptionCard.tsx
import { ExceptionRecord } from "@/types";

interface ExceptionCardProps {
  exception: ExceptionRecord;
}

export default function ExceptionCard({ exception }: ExceptionCardProps) {
  // ...
}
```

- Props destructured in signature, not inside body.
- No inline styles. Tailwind classes only.
- No class components.
- No `React.FC<>` type — prefer inline prop types.

### 4.5 Styling

- Tailwind via PostCSS. Config at `frontend/tailwind.config.js`.
- Colour palette defined in `tailwind.config.js` with named tokens: `severity-critical`, `severity-warning`, `severity-info`, `confidence-low`, `confidence-medium`, `confidence-high`.
- No `@apply` in global CSS; use Tailwind classes directly on elements.
- `globals.css` only for font imports and base resets.

### 4.6 API Client

All backend calls go through `src/api/client.ts`:

```ts
const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: "Unknown", detail: res.statusText }));
    throw new ApiError(res.status, body.error, body.detail);
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(public status: number, public errorCode: string, public detail: string) {
    super(`${errorCode}: ${detail}`);
  }
}
```

All endpoint-specific functions live in `src/api/upload.ts`, `src/api/audit.ts`, `src/api/sessions.ts` and use `apiFetch<T>` internally. Components never call `fetch` directly.

### 4.7 Environment Variables (Frontend)

| Var | Purpose | Default |
|---|---|---|
| `VITE_API_URL` | Backend base URL | `http://localhost:8000` |

No other env vars in MVP. No secrets in the frontend — ever.

---

## 5. MongoDB Conventions

- **One collection in MVP**: `audit_sessions` (as defined in Data Models §3).
- **Indexes** created at application startup in `services/mongo.py`:
  ```python
  async def ensure_indexes(db):
      await db.audit_sessions.create_index("session_id", unique=True)
      await db.audit_sessions.create_index([("created_at", -1)])
  ```
- **No raw PDFs in Mongo.** Enforced by the schema — there is no field for them.
- **No schema validation rules in Mongo itself** (no `$jsonSchema` validator). Pydantic at the application layer is the single source of truth.
- **Reads and writes** go through helper functions in `services/mongo.py`, never directly on the collection from a node or endpoint.

---

## 6. Dependencies — Hard Rules

### 6.1 Approved List

The following are the only third-party dependencies allowed in MVP. Adding a new one requires updating this document first.

**Backend**: FastAPI, Uvicorn, Pydantic, pydantic-settings, PyMongo, Motor, PyMuPDF, google-genai, LangGraph, LangChain core, structlog, python-multipart. Dev: pytest, pytest-asyncio, pytest-cov, ruff, mypy, httpx, respx.

**Frontend**: React, React DOM, React Router, Tailwind CSS, Zustand. Dev: Vite, TypeScript, Vitest, React Testing Library, ESLint plus standard plugins, Prettier.

### 6.2 Explicitly Disallowed

- **Any ORM for Mongo** (Motor + Pydantic is sufficient; odmantic and beanie add complexity without value).
- **axios** (fetch + wrapper is sufficient).
- **React Query / TanStack Query** (over-engineered for 2 polling endpoints).
- **Redux, MobX** (Zustand is sufficient).
- **chroma, weaviate, any vector DB** (explicitly out of scope per PRD).
- **LangChain full package** — only `langchain-core` is permitted. LangChain's full package pulls in hundreds of integrations we don't use.

### 6.3 Version Pinning

Lockfiles (`uv.lock`, `package-lock.json`) are committed. CI installs from lockfiles, not from the loose ranges in `pyproject.toml` / `package.json`.

---

## 7. File Header Template

Every source file starts with a one-line comment identifying it:

```python
# backend/src/freightcheck/agent/nodes/plan_validations.py
"""Planner node — calls Gemini with bind_tools and returns a PlannerDecision."""
```

```tsx
// src/components/ExceptionCard.tsx — renders one exception with severity badge and evidence.
```

No copyright blocks, no author tags, no change logs in source files. Git history is the change log.

---

## 8. Commits & Branches

### 8.1 Branching

- Trunk-based. Feature branches `feat/<milestone>-<short-name>`, short-lived (< 2 days).
- PR titles: `[M3] Implement validate_field_match tool` — milestone tag in brackets.
- Squash-merge feature branches into `main`. The atomic commits on the feature branch are preserved in the PR's history; the squash keeps `main` readable at the milestone level.

### 8.2 Commit Granularity

Prefer small, atomic commits over batched ones. Every commit must be a reviewable logical unit — one passing test plus the code it covers, or one focused refactor, or one coherent set of related files (e.g. "add `BoLFields` Pydantic model and its roundtrip test"). Commit as soon as a unit is complete and locally green: lint, typecheck, and the tests relevant to that unit pass.

Do **not** batch a milestone's work into one commit. Do not split a single logical change across multiple commits. If you are tempted to write "and also" in a commit message, split the commit.

### 8.3 Commit Messages

- Imperative mood, ≤ 72 chars subject line.
- Blank line, then optional body explaining the *why* if non-obvious.
- No emoji. No trailing punctuation on the subject.
- Good: `Add BoLFields Pydantic model with roundtrip test`
- Good: `Fix tolerance comparison in validate_field_match`
- Bad: `updates` / `WIP` / `more changes` / `misc fixes`

### 8.4 Forbidden

- Commits with `WIP`, `temp`, or `misc` in the message.
- Commits that fail `ruff check`, `mypy --strict`, `npm run typecheck`, or `npm run lint`.
- Commits that break tests that were passing in the prior commit.
- Commits that mix unrelated changes (e.g. "add tool + update README + fix unrelated typo").
- Artificially inflated commit counts — splitting a single logical change across multiple commits to pad history. The measure of a good commit history is how easy it is to `git bisect` and how readable a single commit's diff is, not how many squares you painted green.

### 8.5 Pre-Commit Hooks

ruff, ruff format, mypy, ESLint, Prettier, and `npm run typecheck` run on pre-commit. Backend and frontend tests do **not** run on pre-commit — they are too slow and would discourage the atomic-commit discipline above. They run in CI instead. If a hook fails, fix the issue in the same commit rather than committing a broken state and fixing it later.

---

## 9. CI Jobs

Two workflows in `.github/workflows/`.

### 9.1 `ci.yml` — on every PR

- Install deps from lockfiles
- `ruff check backend/`
- `ruff format --check backend/`
- `mypy backend/src/freightcheck/`
- `pytest backend/tests/unit/` (unit tests only, no Gemini key required)
- `npm run lint` in `frontend/`
- `npm run typecheck` in `frontend/`
- `npm run build` in `frontend/`
- `npm run test` in `frontend/`

**CI must pass before merge.** No overrides.

### 9.2 `eval.yml` — nightly and on prompt/schema changes

- Full integration tests (requires `GEMINI_API_KEY` and `MONGODB_URI` from GitHub secrets)
- `python -m eval.run --all` (full eval suite)
- Fails if any pass threshold from Evaluation Spec regresses
- Posts a summary comment on the triggering PR

Prompt or schema changes are detected via path filters in the workflow:
```yaml
on:
  pull_request:
    paths:
      - 'backend/src/freightcheck/agent/prompts.py'
      - 'backend/src/freightcheck/schemas/**'
      - 'knowledge/freightcheck_data_models.md'
      - 'knowledge/freightcheck_prompt_templates.md'
```

---

## 10. Things Not To Do

Explicit list of anti-patterns. If the coding agent is tempted to do any of these, it should re-read the relevant spec instead.

- **Do not** add a new field to a Pydantic model without updating Data Models first.
- **Do not** call Gemini outside of `services/gemini.py`.
- **Do not** write PDFs to disk. The upload cache is memory-only.
- **Do not** pass raw `AgentState` into tools. Tools receive a typed `ToolContext`.
- **Do not** catch `Exception` broadly inside a node — catch specific exceptions and let genuinely unexpected ones set `state["error"]`.
- **Do not** use `print()`. Ever.
- **Do not** hard-code the Gemini model name, Mongo URI, or any budget. Use `settings`.
- **Do not** write tests that call the real Gemini API in the unit suite. Those go in integration and eval.
- **Do not** add a new tool without (a) updating Data Models §5, (b) updating System Design §5.5, (c) adding unit tests, (d) registering it in `TOOL_REGISTRY`.
- **Do not** compose prompts inline. All prompts come from `backend/agent/prompts.py`.
- **Do not** use `any` in TypeScript.
- **Do not** redefine a type that exists in `src/types/index.ts`.
- **Do not** commit secrets. `.env` is gitignored; `.env.example` is not.
