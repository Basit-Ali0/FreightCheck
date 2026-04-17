# FreightCheck — LangGraph Flow Spec

**Version**: 1.0
**Status**: Draft
**Author**: Basit Ali
**Last Updated**: 2026-04-18

---

## Purpose

This document is the authoritative, node-by-node definition of the FreightCheck agent graph. System Design §5 gives the high-level picture; this spec gives the implementation contract. When building the agent, this is the document you implement against.

Dependencies: read **Data Models** (for `AgentState` and all types) and **Prompt Templates** (for every Gemini call) first.

---

## 1. Graph Definition

```python
# backend/agent/graph.py

from langgraph.graph import StateGraph, START, END
from agent.state import AgentState
from agent.nodes import (
    extract_all,
    plan_validations,
    execute_tool,
    reflect,
    compile_report,
)
from agent.edges import (
    route_from_reflect,  # conditional edge
)

def build_graph():
    g = StateGraph(AgentState)

    g.add_node("extract_all", extract_all)
    g.add_node("plan_validations", plan_validations)
    g.add_node("execute_tool", execute_tool)
    g.add_node("reflect", reflect)
    g.add_node("compile_report", compile_report)

    g.add_edge(START, "extract_all")
    g.add_edge("extract_all", "plan_validations")
    g.add_edge("plan_validations", "execute_tool")
    g.add_edge("execute_tool", "reflect")

    g.add_conditional_edges(
        "reflect",
        route_from_reflect,
        {
            "continue": "plan_validations",
            "terminate": "compile_report",
        },
    )

    g.add_edge("compile_report", END)

    return g.compile(checkpointer=get_checkpointer())
```

The graph is **compiled once at module load** and reused across sessions. Per-session state is passed in on `graph.invoke(initial_state)`.

---

## 2. Nodes

Each section below defines a node's contract. Nodes must follow the rules in §6 (State Reducers) — they return partial state updates, never mutate state.

---

### 2.1 `extract_all`

**File**: `backend/agent/nodes/extract_all.py`

**Purpose**: Extract structured fields and per-field confidence from all three documents in parallel. This is the only node that runs three Gemini calls concurrently.

**Inputs (from state)**:
- `raw_texts: dict[str, str]` with keys `"bol"`, `"invoice"`, `"packing_list"`

**Side effects**:
- Three parallel Gemini calls using the extraction prompts from Prompt Templates §2 (BoL, Invoice, Packing List)
- Each call returns structured JSON matching `ExtractedDocument` (fields + confidences)
- Tokens used are accumulated via the Gemini wrapper

**Outputs (partial state update)**:
```python
{
    "extracted_fields": {"bol": {...}, "invoice": {...}, "packing_list": {...}},
    "extraction_confidence": {"bol": {...}, "invoice": {...}, "packing_list": {...}},
    "needs_human_review": bool,          # True if any field confidence < 0.5
    "review_reasons": list[str],         # populated if needs_human_review is True
    "tokens_used": int,                  # additive via reducer
    "elapsed_ms": int,                   # additive via reducer
    "status": "processing",              # unchanged unless extraction fails
}
```

**Error paths**:
- If any of the three extraction calls fails after 2 corrective retries → set `error = "ExtractionError: ..."` and return. The graph will route to `compile_report` which will set `status = "failed"`.
- If extraction returns with a confidence < 0.5 for any field → set `needs_human_review = True` and append a reason like `"bol.gross_weight extracted with confidence 0.42: {rationale}"`. This does **not** halt the graph — extraction still succeeded, just uncertain.

**Parallelism**: use `asyncio.gather` on the three Gemini calls. No extraction depends on another's output.

**Checkpoint**: after this node completes, the checkpointer writes the current state to MongoDB. See §7.

---

### 2.2 `plan_validations`

**File**: `backend/agent/nodes/plan_validations.py`

**Purpose**: Ask Gemini (in `bind_tools` mode) to decide which tools to call next based on current state.

**Inputs (from state)**:
- `extracted_fields`, `extraction_confidence`
- `tool_calls` (prior calls and their results — inform the planner what's already done)
- `planner_decisions` (prior decisions — inform what was already queued)
- `iteration_count`
- `exceptions`, `validations` (so the planner can reason about findings so far)

**Side effects**:
- One Gemini call using the planner prompt from Prompt Templates §3, with `bind_tools(TOOL_REGISTRY.values())`
- Response must be a structured `PlannerDecision` (JSON via `response_schema`):
  ```json
  {
    "chosen_tools": [{"name": "validate_field_match", "args": {...}}, ...],
    "rationale": "one sentence",
    "terminate": false
  }
  ```
  Note: while the **PlannerDecision model stored in state** records `chosen_tools: list[str]`, the planner prompt returns tool names *with their args*. The node splits this into (a) a `plan` queue consumed by `execute_tool`, and (b) a `PlannerDecision` record for trajectory.
- Planner must choose only from tools in `TOOL_REGISTRY`. Any unknown name is rejected before dispatch (see §4).

**Outputs (partial state update)**:
```python
{
    "plan": [{"tool_name": "...", "args": {...}}, ...],  # FIFO queue for execute_tool
    "planner_decisions": [PlannerDecision(...)],          # appended via reducer
    "iteration_count": +1,                                 # via reducer
    "tokens_used": int,                                    # additive via reducer
    "elapsed_ms": int,                                     # additive via reducer
}
```

**Error paths**:
- If Gemini returns malformed JSON after 2 retries → set `error = "PlannerError: ..."`. Route to `compile_report` which runs the deterministic baseline.
- If Gemini returns a tool name not in `TOOL_REGISTRY` → do not call that tool. Record a synthetic failed `ToolCall` with `status="error"` and `error="Unregistered tool name: X"`. Continue with the rest of the plan. The planner will see this on the next iteration and re-plan.

**First-iteration behaviour**: on `iteration_count == 0`, the planner has only extractions and confidences to reason about. Its first decision typically queues 3–5 high-confidence validations.

**Empty plan handling**: if the planner returns `chosen_tools: []` with `terminate: false`, treat this as malformed — force `terminate: true` to prevent an infinite loop. (The `reflect` node will route to `compile_report` either way on iteration cap.)

---

### 2.3 `execute_tool`

**File**: `backend/agent/nodes/execute_tool.py`

**Purpose**: Drain the `plan` queue, dispatching each tool in FIFO order. Records every invocation as a `ToolCall`.

**Inputs (from state)**:
- `plan: list[{"tool_name": str, "args": dict}]`
- `extracted_fields`, `extraction_confidence` (needed by some tools)
- `iteration_count` (stamped on each ToolCall)

**Side effects**:
- For each entry in `plan`:
  1. Look up `TOOL_REGISTRY[tool_name]`. If absent, record a failed `ToolCall` and continue (never raise).
  2. Validate `args` against the tool's Pydantic-typed signature. If invalid, record failed `ToolCall`.
  3. Invoke the tool with `args`. Capture `result`, `duration_ms`, `status`, and `error` if raised.
  4. Append the `ToolCall` to the trajectory.
  5. Tools may themselves produce side effects on state: append to `validations`, append to `exceptions`, update `extracted_fields` and `extraction_confidence` (for `re_extract_field`), set `needs_human_review`.

**Outputs (partial state update)**:
```python
{
    "plan": [],                           # emptied (all drained)
    "tool_calls": [...],                   # N new ToolCall records appended via reducer
    "validations": [...],                  # appended via reducer (from tools)
    "exceptions": [...],                   # appended via reducer (from tools)
    "extracted_fields": {...},             # may be updated by re_extract_field
    "extraction_confidence": {...},        # may be updated by re_extract_field
    "needs_human_review": bool,            # may be set by escalate_to_human_review
    "review_reasons": [...],               # may be appended
    "tokens_used": int,                    # additive via reducer
    "elapsed_ms": int,                     # additive via reducer
}
```

**Error paths**:
- Individual tool failures are **never raised out of this node.** A failed tool produces a `ToolCall` with `status="error"`, and execution continues with the next queued tool. The planner will see failures on the next iteration.
- If the entire node raises an unexpected exception (not a tool failure — e.g. Mongo write failure via a tool) → set `error` and return.

**Timing**: tools run **sequentially** within a single `execute_tool` invocation. If multiple tools in the plan are independent and slow (semantic validators), a future optimisation may parallelise them — not for MVP.

---

### 2.4 `reflect`

**File**: `backend/agent/nodes/reflect.py`

**Purpose**: Decide whether to loop back to `plan_validations` or terminate to `compile_report`. This is the only conditional branching point in the graph.

**Inputs (from state)**:
- `planner_decisions` (the last one drives the primary decision)
- `iteration_count`
- `tokens_used`, `elapsed_ms`
- `error`

**Side effects**: none. `reflect` is pure logic.

**Outputs (partial state update)**:
```python
{}  # no state changes
```

**Routing** (via `route_from_reflect` in `agent/edges.py`):
```python
def route_from_reflect(state: AgentState) -> Literal["continue", "terminate"]:
    if state.get("error"):
        return "terminate"
    last = state["planner_decisions"][-1] if state["planner_decisions"] else None
    if last and last["terminate"]:
        return "terminate"
    if state["iteration_count"] >= settings.MAX_ITERATIONS:
        return "terminate"
    if state["tokens_used"] >= settings.TOKEN_BUDGET:
        return "terminate"
    if state["elapsed_ms"] >= settings.TIME_BUDGET_MS:
        return "terminate"
    return "continue"
```

**Default config values** (from `settings.py`, overridable via env):
| Constant | Default | Env var |
|---|---|---|
| `MAX_ITERATIONS` | 8 | `AGENT_MAX_ITERATIONS` |
| `TOKEN_BUDGET` | 50_000 | `AGENT_TOKEN_BUDGET` |
| `TIME_BUDGET_MS` | 25_000 | `AGENT_TIME_BUDGET_MS` |

---

### 2.5 `compile_report`

**File**: `backend/agent/nodes/compile_report.py`

**Purpose**: Produce the final `AuditReport`, set the final `status`, and run any deterministic baseline validations that weren't executed during the planner loop.

**Inputs (from state)**: all of it.

**Side effects**:
1. **Baseline sweep**: inspect which validations from the Data Models §5 catalogue were *not* executed (no matching `ToolCall`). Run each missing baseline validation deterministically (no Gemini calls for exact/numeric checks; Gemini for semantic checks only if budget permits — otherwise skip and record a warning in the summary).
2. Count exceptions by severity.
3. Generate a one-sentence summary via the summary prompt (Prompt Templates §6). If `error` is set or token budget is exhausted, skip the Gemini summary and use a deterministic template (e.g. `"{N} critical, {M} warning issues detected. Baseline only — agent did not complete planner loop."`).
4. Determine final status:
   - `status = "failed"` if `error` is set and no report could be produced
   - `status = "awaiting_review"` if `needs_human_review == True`
   - `status = "complete"` otherwise
5. Set `completed_at` and final `elapsed_ms`.
6. Write the final session state to MongoDB (synchronous, not via checkpointer — the final write is authoritative).

**Outputs (partial state update)**:
```python
{
    "report": AuditReport(...),
    "status": "complete" | "awaiting_review" | "failed",
    "completed_at": datetime.utcnow(),
    "elapsed_ms": int,  # final total
}
```

**Error paths**: if the final Mongo write fails, log the error with full state and raise — the FastAPI background task framework will log the failure but the endpoint has already returned. Future `/sessions/:id` queries will return the last checkpointed state (which will show `status="processing"` — the frontend polling loop's 60s timeout catches this).

---

## 3. Edges

| From | To | Condition |
|---|---|---|
| `START` | `extract_all` | unconditional |
| `extract_all` | `plan_validations` | unconditional |
| `plan_validations` | `execute_tool` | unconditional |
| `execute_tool` | `reflect` | unconditional |
| `reflect` | `plan_validations` | `route_from_reflect() == "continue"` |
| `reflect` | `compile_report` | `route_from_reflect() == "terminate"` |
| `compile_report` | `END` | unconditional |

**Note**: `extract_all` internally fans out (three parallel Gemini calls) but externally presents as a single node. LangGraph sees one edge in, one edge out.

---

## 4. Tool Registry

**File**: `backend/agent/tools.py`

```python
from typing import Callable
from langchain_core.tools import BaseTool, tool

# ... tool definitions from System Design §5.5 go here ...

TOOL_REGISTRY: dict[str, BaseTool] = {
    "validate_field_match": validate_field_match,
    "validate_field_semantic": validate_field_semantic,
    "re_extract_field": re_extract_field,
    "check_container_consistency": check_container_consistency,
    "check_incoterm_port_plausibility": check_incoterm_port_plausibility,
    "check_container_number_format": check_container_number_format,
    "flag_exception": flag_exception,
    "escalate_to_human_review": escalate_to_human_review,
}

def get_tool(name: str) -> BaseTool | None:
    """Return the tool or None if name is not registered. Never raises."""
    return TOOL_REGISTRY.get(name)
```

**Rules**:
- Tools receive `extracted_fields`, `extraction_confidence`, and any other state they need via a **tool context** object injected by the dispatcher in `execute_tool`. Tools do not receive the full `AgentState` TypedDict — they receive a typed `ToolContext` with only the fields they are allowed to read and mutate.
- Tool docstrings are the LLM's only documentation for each tool. Keep them exactly as specified in System Design §5.5.
- Adding a tool requires: (a) a new entry in `TOOL_REGISTRY`, (b) unit tests, (c) documentation in System Design §5.5 and the Validation Catalogue in Data Models §5. All three, or the tool is not considered registered.

---

## 5. Tool Dispatcher Contract

The `execute_tool` node uses the dispatcher below. It is the single funnel for all tool invocations.

```python
# backend/agent/dispatcher.py

from time import perf_counter
from uuid import uuid4
from datetime import datetime

def dispatch(
    tool_name: str,
    args: dict,
    ctx: ToolContext,
    iteration: int,
) -> ToolCall:
    tool = TOOL_REGISTRY.get(tool_name)
    started_at = datetime.utcnow()
    t0 = perf_counter()

    if tool is None:
        return ToolCall(
            tool_call_id=str(uuid4()),
            iteration=iteration,
            tool_name=tool_name,
            args=args,
            result=None,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            duration_ms=0,
            status="error",
            error=f"Unregistered tool name: {tool_name}",
        )

    try:
        validated_args = tool.args_schema.model_validate(args)
        result = tool.invoke(validated_args.model_dump(), config={"context": ctx})
        status = "success"
        error = None
    except Exception as e:
        result = None
        status = "error"
        error = f"{type(e).__name__}: {e}"

    completed_at = datetime.utcnow()
    duration_ms = int((perf_counter() - t0) * 1000)

    return ToolCall(
        tool_call_id=str(uuid4()),
        iteration=iteration,
        tool_name=tool_name,
        args=args,
        result=result,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        status=status,
        error=error,
    )
```

**Rules**:
- The dispatcher **never raises.** Every failure becomes a `ToolCall` with `status="error"`.
- The dispatcher **does not mutate state.** It returns a `ToolCall`; `execute_tool` merges state via the reducer.
- Args validation uses the tool's Pydantic args schema, which is auto-generated by the `@tool` decorator from the function signature. If validation fails, record the error without invoking the tool.

---

## 6. State Reducers

LangGraph merges partial updates from nodes into the running state. By default, dict keys overwrite and list keys replace. For FreightCheck we need additive list behaviour for trajectory and accumulator fields.

**File**: `backend/agent/state.py`

```python
from typing import Annotated, TypedDict, Any, Literal
from operator import add

# Additive list reducer: append new items
def append_list(left: list, right: list) -> list:
    if left is None:
        return right or []
    if right is None:
        return left
    return left + right

# Additive int reducer: sum
def sum_ints(left: int, right: int) -> int:
    return (left or 0) + (right or 0)

# Deep merge for nested dicts (extracted_fields, extraction_confidence)
def deep_merge(left: dict, right: dict) -> dict:
    if not left:
        return right or {}
    if not right:
        return left
    merged = {**left}
    for k, v in right.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged

class AgentState(TypedDict):
    session_id: str
    raw_texts: dict[str, str]

    extracted_fields: Annotated[dict, deep_merge]
    extraction_confidence: Annotated[dict, deep_merge]

    plan: list[dict]                                     # replaced each time (not appended)
    tool_calls: Annotated[list[dict], append_list]
    planner_decisions: Annotated[list[dict], append_list]
    iteration_count: Annotated[int, sum_ints]

    validations: Annotated[list[dict], append_list]
    exceptions: Annotated[list[dict], append_list]

    report: dict | None

    needs_human_review: bool                             # logical-OR on update
    review_reasons: Annotated[list[str], append_list]

    tokens_used: Annotated[int, sum_ints]
    elapsed_ms: Annotated[int, sum_ints]
    error: str | None

    status: Literal["processing", "complete", "failed", "awaiting_review"]
```

**Reducer rules**:
- `plan` is **replaced** on every `plan_validations` update — the planner's new plan always supersedes the prior one.
- `tool_calls`, `planner_decisions`, `validations`, `exceptions`, `review_reasons` are **appended**.
- `iteration_count`, `tokens_used`, `elapsed_ms` are **summed**. `plan_validations` returns `{"iteration_count": 1}` each time.
- `extracted_fields` and `extraction_confidence` are **deep-merged**, so `re_extract_field` can update a single field without clobbering the rest.
- `needs_human_review` uses the default (last-write-wins). Nodes set it to `True` and never set it back to `False` — once flagged, the session remains flagged.
- `status` uses the default (last-write-wins). Only `extract_all` and `compile_report` write this field.

---

## 7. Checkpointing

**File**: `backend/agent/checkpointing.py`

After every node, the graph writes the current state to MongoDB. This makes `GET /sessions/:id` show live progress during a running audit.

```python
from langgraph.checkpoint.base import BaseCheckpointSaver
# Custom or use langgraph.checkpoint.mongodb if available

class MongoCheckpointer(BaseCheckpointSaver):
    def __init__(self, collection):
        self.collection = collection

    def put(self, config, checkpoint, metadata, new_versions):
        session_id = config["configurable"]["thread_id"]
        self.collection.update_one(
            {"session_id": session_id},
            {"$set": _to_mongo_doc(checkpoint["channel_values"])},
            upsert=True,
        )
```

**Rules**:
- `thread_id` = `session_id`. One checkpoint per session.
- Only the latest state is persisted — no checkpoint history. FreightCheck does not support resuming or replaying; if a session crashes, the frontend polling loop catches it via the 60s timeout and the user re-runs.
- The `compile_report` node does a final authoritative write bypassing the checkpointer. If the checkpointer has raced ahead of `compile_report`, the compile_report write is still the final source of truth because it is synchronous and happens last.

---

## 8. Running The Graph

The FastAPI `POST /audit` handler triggers the graph as a FastAPI background task. The graph is not awaited — the endpoint returns immediately and the frontend polls.

```python
# backend/api/audit.py

@router.post("/audit")
async def start_audit(
    req: AuditRequest,
    background_tasks: BackgroundTasks,
    db = Depends(get_db),
):
    session = create_session(req.session_id, db)
    background_tasks.add_task(run_agent, session_id=req.session_id)
    return AuditResponse(
        session_id=req.session_id,
        status=SessionStatus.PROCESSING,
        message=f"Audit started. Poll /sessions/{req.session_id} for results.",
        created_at=session.created_at,
    )

async def run_agent(session_id: str):
    raw_texts = upload_cache.get(session_id)
    initial_state = make_initial_state(session_id, raw_texts)
    try:
        await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": session_id}},
        )
    except Exception as e:
        log.exception("agent.unhandled_error", session_id=session_id)
        mark_session_failed(session_id, str(e), get_db())
```

**Notes**:
- `graph.ainvoke` must be awaited — use the async graph interface, not the sync one.
- Any exception escaping the graph (should never happen if nodes follow error path rules, but defence-in-depth) is caught here and the session is marked `failed`.
- The background task is not retried. If a session fails, the user re-uploads and re-runs.

---

## 9. Example Trace

A successful audit walks through the graph as follows. Timestamps and tool names are illustrative.

```
t=0      extract_all starts
t=0      → Gemini.extract(bol)
t=0      → Gemini.extract(invoice)                    (parallel)
t=0      → Gemini.extract(packing_list)               (parallel)
t=12.1s  extract_all completes. All confidences > 0.9. tokens_used=14200.
         needs_human_review=False.
t=12.1s  [CHECKPOINT to Mongo]

t=12.1s  plan_validations starts (iteration 1)
t=13.2s  → Planner returns: chosen_tools=[validate_field_match(incoterm, bol, invoice),
                                           check_container_consistency()]
         rationale="High-confidence incoterm values present; container numbers
                    exactly match — run set equality"
         terminate=false
t=13.2s  [CHECKPOINT]

t=13.2s  execute_tool starts
t=13.2s  → dispatch validate_field_match(incoterm, bol, invoice)
           returns: critical_mismatch (CIF vs FOB). Appends exception.
t=13.3s  → dispatch check_container_consistency()
           returns: match.
t=13.3s  [CHECKPOINT]

t=13.3s  reflect: terminate=false, iteration=1, tokens=15300 < 50000. Continue.

t=13.3s  plan_validations starts (iteration 2)
t=14.4s  → Planner returns: chosen_tools=[validate_field_semantic(
              description_of_goods, bol, invoice)]
         rationale="Strings differ in surface form; need semantic comparison"
         terminate=false
t=14.4s  [CHECKPOINT]

t=14.4s  execute_tool
t=15.8s  → validate_field_semantic returns minor_mismatch. Warning appended.
t=15.8s  [CHECKPOINT]

t=15.8s  reflect: continue.

t=15.8s  plan_validations starts (iteration 3)
t=16.8s  → Planner returns: chosen_tools=[], terminate=true
         rationale="All catalogue validations complete; no low-confidence fields."

t=16.8s  reflect: terminate=true → compile_report

t=16.8s  compile_report
t=16.8s  → Baseline sweep: total_quantity, total_weight, invoice_total_vs_line_items,
           incoterm_port_plausibility, container_number_format, etc. → all pass.
t=17.2s  → Summary prompt → "1 critical incoterm conflict detected..."
t=17.2s  → status = complete, completed_at set, final Mongo write
t=17.2s  [END]
```

Total: ~17 seconds, 18.4k tokens, 3 planner iterations, 3 tool calls during loop plus deterministic baseline sweep.

---

## 10. Implementation Notes & Gotchas

- **Never call Gemini outside a node.** If validation logic needs Gemini, it goes in a tool that the planner can choose to invoke. This keeps tokens accounted for and trajectories complete.
- **Never call a tool from within another tool.** Tools are leaves. If composition is needed, it's a new tool.
- **`raw_texts` stays in state but is never checkpointed to Mongo.** Strip it from the checkpoint write. It's only needed for `extract_all` and `re_extract_field`.
- **The checkpointer writes are async** — do not `await` them in nodes. Let them race. The `compile_report` final write is synchronous and authoritative.
- **`re_extract_field` is the only tool that mutates `extracted_fields`.** All other tools read-only from extraction state.
- **The planner must never modify exceptions directly.** It only chooses tools; tools produce exceptions via their side-effect pathway.
- **Tool dispatcher validates args** — if the planner hallucinates arg names or types, the tool is not invoked and a failed `ToolCall` is recorded. The planner sees this in its next iteration's prompt context and re-plans.
