# FreightCheck — Error Handling Spec

**Version**: 1.0
**Status**: Draft
**Author**: Basit Ali
**Last Updated**: 2026-04-18

---

## Purpose

This document defines **agent-internal** error handling: retries, budget exhaustion, tool dispatch failures, partial state preservation. HTTP-layer error responses are in the **API Contract**. Component-level error boundaries are in the **System Design §9**. This spec focuses on the agent and the service layer.

When this document and the API Contract appear to overlap, the API Contract wins for HTTP shape, and this document wins for "what the agent does on the inside before the response is returned".

---

## 1. Exception Hierarchy

All custom exceptions live in `backend/src/freightcheck/errors.py`.

```python
class FreightCheckError(Exception):
    """Base class for all FreightCheck errors."""

# ---- Upload / PDF layer ----
class InvalidFileTypeError(FreightCheckError): ...
class FileTooLargeError(FreightCheckError): ...
class ImageOnlyPDFError(FreightCheckError): ...
class PDFParseError(FreightCheckError): ...
class MissingDocumentError(FreightCheckError): ...

# ---- Session layer ----
class SessionNotFoundError(FreightCheckError): ...
class DuplicateAuditError(FreightCheckError): ...

# ---- Gemini layer ----
class GeminiAPIError(FreightCheckError):
    """Network, auth, or rate-limit failure from Gemini."""
class ExtractionError(FreightCheckError):
    """Gemini produced unusable output for an extraction prompt after retries."""
class PlannerError(FreightCheckError):
    """Planner call failed or returned malformed output after retries."""
class SemanticValidationError(FreightCheckError):
    """Semantic validator prompt failed after retries."""

# ---- Agent layer ----
class InvalidToolError(FreightCheckError):
    """Planner requested a tool that is not in TOOL_REGISTRY."""
class ToolArgsValidationError(FreightCheckError):
    """Planner provided arguments that fail the tool's Pydantic args schema."""
class AgentBudgetError(FreightCheckError):
    """Iteration, token, or time budget exhausted. Not a crash — graceful."""

# ---- Database layer ----
class DatabaseError(FreightCheckError):
    """MongoDB read/write failure."""
```

**Rules**:
- Every raised exception must be a subclass of `FreightCheckError`. No raw `Exception` instances.
- Exception messages are structured: `"{error_type}: {context}"` — e.g. `"ExtractionError: BoL extraction returned invalid JSON after 2 retries. Last validation error: missing field 'gross_weight'."`.
- Exceptions carry a dict context via `self.context` for structured logging:
  ```python
  class FreightCheckError(Exception):
      def __init__(self, message: str, **context):
          super().__init__(message)
          self.context = context
  ```

---

## 2. Gemini Retry Policy

All Gemini calls go through `services/gemini.py`. The retry behaviour is identical regardless of caller.

### 2.1 Retryable vs Non-Retryable Failures

| Failure | Retryable? | Policy |
|---|---|---|
| HTTP 429 (rate limit) | Yes | Exponential backoff: 2s, 4s. After 2 retries: raise `GeminiAPIError` |
| HTTP 5xx | Yes | Same as rate limit |
| HTTP 4xx other than 429 | No | Raise `GeminiAPIError` immediately |
| Network timeout | Yes | Same as rate limit |
| Schema validation failure on response | Yes, but differently | Send corrective prompt (Prompt Templates §7.1, then §7.2). Max 2 schema retries |
| Auth failure (401/403) | No | Raise `GeminiAPIError`. Almost certainly a misconfigured API key |

**Schema retries and network retries are independent counters.** A single Gemini call may consume up to `2 network retries × 3 schema attempts = 6 roundtrips` in the worst case before raising.

### 2.2 Wrapper Contract

```python
# backend/src/freightcheck/services/gemini.py

async def call_gemini(
    prompt_name: str,
    prompt_template: str,
    template_vars: dict,
    response_schema: type[BaseModel],
    tools: list[BaseTool] | None = None,
    system_instruction: str = SYSTEM_INSTRUCTION,
) -> tuple[BaseModel, int]:
    """
    Returns (parsed_response, tokens_used).
    Raises ExtractionError / PlannerError / SemanticValidationError (chosen by
    caller via prompt_name) on schema failure after all retries.
    Raises GeminiAPIError on network failure after all retries.
    """
```

**Rules**:
- The wrapper is the **only** place that touches the Gemini SDK.
- The wrapper emits `agent.gemini_call` log events on every call (including retries).
- Token usage is accumulated per call and returned. Callers are responsible for summing into `AgentState.tokens_used`.
- The wrapper never invokes a tool. `bind_tools` returns a tool-call request; the dispatcher invokes it.

### 2.3 Mapping Prompt to Exception

| prompt_name prefix | Raises on final failure |
|---|---|
| `bol_extraction`, `invoice_extraction`, `packing_list_extraction`, `re_extraction` | `ExtractionError` |
| `planner` | `PlannerError` |
| `semantic_validator` | `SemanticValidationError` |
| `summary` | Never raises — returns empty string, caller uses fallback template |

---

## 3. Per-Node Error Handling

Each LangGraph node must follow the rules below. These are enforced by the LangGraph Flow Spec; repeated here for ergonomics.

### 3.1 `extract_all`

- On any of the three parallel extraction calls raising `ExtractionError` after retries:
  - Set `state["error"] = "ExtractionError: {which document}: {message}"`.
  - Do **not** set a failed `ToolCall` or `PlannerDecision` — this failure happens before the planner loop.
  - Return normally. The graph flows through the loop (which `reflect` will terminate because `error` is set) to `compile_report` which sets `status = "failed"` and records `error_message` on the session.
- On `GeminiAPIError`: same as above.
- Any field extracted with confidence < 0.5: set `needs_human_review = True`, append to `review_reasons`. Continue — this is not an error.

### 3.2 `plan_validations`

- On `PlannerError` after retries: set `state["error"] = "PlannerError: ..."`. Route to `compile_report` which runs the deterministic baseline — the session can still produce a useful report from extraction alone.
- On `GeminiAPIError`: same.
- On planner returning a tool name not in `TOOL_REGISTRY`: **do not raise.** `execute_tool` will record the failed dispatch. The next `plan_validations` iteration sees the failure and re-plans.
- On planner returning `chosen_tools: []` with `terminate: false`: force `terminate: true` in the stored `PlannerDecision`. Do not re-call the planner — treat this as a signal the planner is done.

### 3.3 `execute_tool`

- **Tool failures never raise out of this node.** They become `ToolCall`s with `status="error"`.
- Categories of tool failure and how each is recorded:
  | Category | `error` field format |
  |---|---|
  | Unregistered tool name | `"Unregistered tool name: {name}"` |
  | Args validation failure | `"ToolArgsValidationError: {pydantic_error}"` |
  | Tool raised `SemanticValidationError` | `"SemanticValidationError: {message}"` |
  | Tool raised `ExtractionError` (re_extract_field) | `"ExtractionError: {message}"` |
  | Tool raised `GeminiAPIError` | `"GeminiAPIError: {message}"` |
  | Tool raised any other `FreightCheckError` | `"{ClassName}: {message}"` |
  | Tool raised unexpected `Exception` | `"UnexpectedToolError: {type}: {message}"` — also log at `error` level with traceback |
- If the dispatcher itself fails (e.g. `TOOL_REGISTRY` lookup raises — should never happen), set `state["error"]` and route to `compile_report`.

### 3.4 `reflect`

- Pure logic — cannot raise except on genuinely impossible state corruption (e.g. `iteration_count` is `None`). In that case raise the exception; the graph framework will fail the session. This is a bug, not an error path.

### 3.5 `compile_report`

- The **last defence**. This node runs even after `error` is set, to ensure a session always ends in a terminal state.
- If `error` is set:
  - `status = "failed"`.
  - `error_message` = the error string.
  - `report = None`.
  - Still write the final state to Mongo.
- If `needs_human_review` is True:
  - `status = "awaiting_review"`.
  - Report is generated normally.
- Baseline sweep: run every catalogue validation from Data Models §5 that does not have a corresponding `ToolCall` with `status="success"`.
  - If a baseline validation itself raises (should not happen for deterministic ones; can for semantic), record a `ToolCall` with `status="error"` and continue. Don't let one bad validation prevent the report.
- Summary generation: if the Gemini summary call raises, use the deterministic fallback template from Prompt Templates §6. Do not fail the session for a summary.
- Mongo write failure on the final write: log at `error` level with the full state, then raise. The FastAPI background task framework will record the failure. The session will appear stuck in `processing` from the client's perspective; the 60s polling timeout catches it.

---

## 4. Tool-Level Error Handling

Tools are defined in `backend/src/freightcheck/agent/tools.py`. Each tool has its own internal error behaviour.

### 4.1 `validate_field_match`

- If either doc is missing from `extracted_fields`: return `ValidationResult(status=critical_mismatch, reason="Field missing from {doc}")` — this is a finding, not a tool error.
- If the types don't line up (e.g. comparing a string to a list): raise `ValueError` caught by dispatcher → `ToolCall` error.
- Numeric overflow on tolerance calc: catch, treat as `critical_mismatch`.

### 4.2 `validate_field_semantic`

- Calls Gemini. On `SemanticValidationError` from the wrapper: re-raise (caught by dispatcher as a failed `ToolCall`).
- On `GeminiAPIError`: re-raise.

### 4.3 `re_extract_field`

- Calls Gemini with the re-extraction prompt.
- On `ExtractionError`: re-raise (caught by dispatcher). The field remains at its previous low-confidence value. The planner may re-try once more (budget permitting) or escalate.
- **Do not** mutate `extracted_fields` or `extraction_confidence` on failure. Success means both are updated via the ToolContext API.

### 4.4 `check_container_consistency`, `check_container_number_format`, `check_incoterm_port_plausibility`

- Pure deterministic logic. No external calls.
- If required extracted fields are absent: return a `ValidationResult(status=critical_mismatch, reason="Required field missing")`.
- Should not raise under any condition. If one does, it's a bug.

### 4.5 `flag_exception`, `escalate_to_human_review`

- State-mutation tools. Never raise.

---

## 5. Budget Exhaustion Semantics

Budgets are defined in `settings.py` (see Implementation Rules §2.5). Each is checked in `reflect`.

| Budget | Default | Semantics on exhaustion |
|---|---|---|
| `AGENT_MAX_ITERATIONS` | 8 | `reflect` routes to `compile_report`. `compile_report` runs baseline sweep for any un-attempted catalogue validations. Session ends `complete` (or `awaiting_review`) with a summary note: `"Planner loop terminated at iteration cap; baseline validations ran."` |
| `AGENT_TOKEN_BUDGET` | 50_000 | Same routing. Summary note: `"Token budget reached; agent terminated early."` |
| `AGENT_TIME_BUDGET_MS` | 25_000 | Same routing. Summary note: `"Time budget reached; agent terminated early."` |

**Key principle**: budget exhaustion is **not an error**. It does not set `state["error"]`. It does not produce `status = "failed"`. The user gets a complete (or awaiting_review) report — just one where the planner didn't finish exploring. This is a core correctness property: the planner is an optimisation, the baseline is the floor.

The summary string informing the user of early termination is generated deterministically (no Gemini call) since token budget is typically the reason.

---

## 6. Database Error Handling

All Mongo operations go through `services/mongo.py`. Reads and writes wrap the underlying Motor calls with structured error handling.

### 6.1 Read Failures

- `GET /sessions` and `GET /sessions/:id`: on `PyMongoError`, log at error level and return HTTP 500 with `{"error": "DatabaseError", "detail": "Failed to retrieve sessions. Please try again."}`.
- Frontend handles 500 as a retryable error (shows a toast, allows manual refresh).

### 6.2 Write Failures

- **During upload** (`/upload` does not write to Mongo — nothing to fail here; upload cache is in-memory).
- **During `POST /audit`** (creating the session): on failure, return HTTP 500 with `DatabaseError`. Do not spawn the background task.
- **During the agent run** (checkpointer writes): log at error level with traceback. Do not crash the node — the next checkpoint attempt may succeed. The final `compile_report` write is authoritative.
- **During `compile_report`'s final write**: if this fails, raise (after logging). The background task framework logs the failure. Session appears stuck in `processing`; polling times out on the client.

### 6.3 Consistency

FreightCheck does not use Mongo transactions. The trade-off is acceptable because:
- Checkpoint writes are idempotent (they overwrite the same document by `session_id`).
- The final `compile_report` write is the only write that matters for user-visible state.
- No cross-document invariants to maintain (single collection, one document per session).

---

## 7. Upload Cache Failures

The upload cache is an in-memory dict mapping `session_id → raw_texts` with a 10-minute TTL. Lives in `services/upload_cache.py`.

- On `/audit` call where the session ID is not in the cache: raise `SessionNotFoundError`, return HTTP 400 with the exact message from API Contract.
- On cache full (unlikely at portfolio scale): evict oldest entries. Not implemented in MVP; add a bounded LRU if needed post-deploy.
- Cache is lost on backend restart. Users must re-upload. This is acceptable given the 10-minute TTL and MVP scope.

---

## 8. Log-And-Continue vs Fail-Fast Summary

Use this table as the decision guide when implementing error handling in a new place.

| Failure | Behaviour |
|---|---|
| PDF has no extractable text | Fail-fast: 422 at upload, never reaches agent |
| PDF size exceeds limit | Fail-fast: 413 at upload |
| Wrong file type | Fail-fast: 400 at upload |
| Extraction (Gemini) fails after retries | Set `error`, route through graph, session ends `failed` |
| Planner (Gemini) fails after retries | Set `error`, route through graph, baseline sweep runs, session ends `failed` only if report can't be compiled |
| Planner returns unregistered tool | Log-and-continue: recorded as failed `ToolCall`, planner re-plans |
| Planner returns empty plan with terminate=false | Force terminate=true, log warning |
| Individual tool raises expected exception | Log-and-continue: failed `ToolCall`, agent continues |
| Individual tool raises unexpected exception | Log with traceback, failed `ToolCall`, agent continues |
| Iteration / token / time budget hit | Log-and-continue: route to `compile_report`, baseline runs |
| Low extraction confidence | Log-and-continue: session ends `awaiting_review` |
| Mongo read fails | Fail-fast: 500 at endpoint |
| Mongo checkpoint write fails | Log-and-continue: next checkpoint may succeed |
| Mongo final write in compile_report fails | Log-and-crash: background task fails, client polling times out |
| Summary Gemini call fails | Log-and-continue: use deterministic fallback template |
| Any `Exception` escaping a node (bug) | FastAPI background task catches, marks session `failed`, logs with traceback |

---

## 9. What NOT To Do

Common mistakes a coding agent might make under pressure:

- **Do not** catch `Exception` in node bodies. Catch specific `FreightCheckError` subclasses. Let genuinely unexpected exceptions propagate to the outermost `run_agent` handler.
- **Do not** raise inside a tool when you could return a finding. A tool returning `critical_mismatch` with `reason="Field missing"` is more useful than a tool raising `ValueError("missing field")`.
- **Do not** retry indefinitely. Every retry has a hard cap defined here.
- **Do not** swallow errors silently. Every caught exception logs at least once, usually at `warning` or `error` level.
- **Do not** set `status = "failed"` outside of `compile_report`. Only one node finalises status.
- **Do not** re-raise after catching in the dispatcher — tool failures stay as failed `ToolCall`s. If the dispatcher itself is broken, that's a different story (set `state["error"]`).
- **Do not** try to "recover" from a budget exhaustion by bumping the budget. Budgets are user/ops-controlled. The agent respects them.
