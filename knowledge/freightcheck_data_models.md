# FreightCheck — Data Models

**Version**: 1.0  
**Status**: Draft  
**Author**: Basit Ali  
**Last Updated**: 2026-04-18

---

## Overview

This document is the **single source of truth** for all data structures in FreightCheck. Every field name, type, and constraint defined here must be used consistently across:

- Pydantic models (`backend/schemas/`)
- MongoDB documents (`audit_sessions` collection)
- API request/response bodies
- LangGraph AgentState
- Frontend TypeScript interfaces

If a field name changes, it changes here first. No exceptions.

---

## 1. Pydantic Models — Backend (`backend/schemas/`)

---

### 1.1 Document Extraction Models (`schemas/documents.py`)

These models define the structured output of Gemini field extraction for each document type. Every Gemini extraction call must return data that validates against one of these models.

---

#### `LineItem` (shared)

Used inside both `InvoiceFields` and `PackingListFields`.

```python
class LineItem(BaseModel):
    description: str
    quantity: int
    unit_price: float | None = None   # present in invoice, absent in packing list
    net_weight: float | None = None   # present in packing list, absent in invoice
```

| Field | Type | Required | Description |
|---|---|---|---|
| `description` | str | Yes | Item description as it appears in the document |
| `quantity` | int | Yes | Number of units |
| `unit_price` | float | No | Per-unit price in invoice currency. Null in packing list |
| `net_weight` | float | No | Net weight per package in kg. Null in invoice |

---

#### `BoLFields`

Extracted fields from a Bill of Lading document.

```python
class BoLFields(BaseModel):
    bill_of_lading_number: str
    shipper: str
    consignee: str
    vessel_name: str
    port_of_loading: str
    port_of_discharge: str
    container_numbers: list[str]
    description_of_goods: str
    gross_weight: float
    incoterm: str
```

| Field | Type | Required | Description |
|---|---|---|---|
| `bill_of_lading_number` | str | Yes | Unique BoL reference (e.g. "MSKU1234567") |
| `shipper` | str | Yes | Exporting party full name |
| `consignee` | str | Yes | Receiving/importing party full name |
| `vessel_name` | str | Yes | Name of the carrying vessel |
| `port_of_loading` | str | Yes | Origin port with country (e.g. "Nhava Sheva, India") |
| `port_of_discharge` | str | Yes | Destination port with country (e.g. "Jebel Ali, UAE") |
| `container_numbers` | list[str] | Yes | All container IDs (e.g. ["MSCU1234567"]) |
| `description_of_goods` | str | Yes | Cargo description as stated on BoL |
| `gross_weight` | float | Yes | Total shipment weight in kg |
| `incoterm` | str | Yes | Trade term (e.g. "CIF", "FOB", "EXW") |

**Extraction notes for Gemini prompt**:
- `container_numbers` must always be a list even if only one container is present
- `gross_weight` must be extracted as a float in kg — convert if document states tonnes or lbs
- `incoterm` must be extracted as the 3-letter code only (e.g. "CIF" not "Cost Insurance Freight")

---

#### `InvoiceFields`

Extracted fields from a Commercial Invoice document.

```python
class InvoiceFields(BaseModel):
    invoice_number: str
    seller: str
    buyer: str
    invoice_date: str               # format: YYYY-MM-DD
    line_items: list[LineItem]
    total_value: float
    currency: str                   # ISO 4217 code
    incoterm: str
```

| Field | Type | Required | Description |
|---|---|---|---|
| `invoice_number` | str | Yes | Unique invoice reference (e.g. "INV-2026-0042") |
| `seller` | str | Yes | Selling/exporting party full name |
| `buyer` | str | Yes | Buying/importing party full name |
| `invoice_date` | str | Yes | Date of invoice in YYYY-MM-DD format |
| `line_items` | list[LineItem] | Yes | All line items. Minimum 1 item |
| `total_value` | float | Yes | Total invoice value as stated on document |
| `currency` | str | Yes | ISO 4217 currency code (e.g. "USD", "EUR") |
| `incoterm` | str | Yes | Trade term (e.g. "CIF", "FOB", "EXW") |

**Extraction notes for Gemini prompt**:
- `invoice_date` must always be normalised to YYYY-MM-DD regardless of format in document
- `total_value` is the final total as stated — do not sum line items yourself
- `currency` must be the 3-letter ISO code only — not the symbol

---

#### `PackingListFields`

Extracted fields from a Packing List document.

```python
class PackingListFields(BaseModel):
    total_packages: int
    total_weight: float
    container_numbers: list[str]
    line_items: list[LineItem]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `total_packages` | int | Yes | Total number of packages/cartons |
| `total_weight` | float | Yes | Total gross weight in kg |
| `container_numbers` | list[str] | Yes | All container IDs referenced |
| `line_items` | list[LineItem] | Yes | All line items. Minimum 1 item |

**Extraction notes for Gemini prompt**:
- `total_weight` must be in kg — convert if document states tonnes or lbs
- `container_numbers` must always be a list even if only one container is present

---

### 1.2 Extraction Confidence (`schemas/documents.py`)

Every extraction node returns not just the structured fields but a parallel map of per-field confidence scores. The planner uses confidence to decide whether to re-extract, flag for human review, or proceed to validation.

#### `ExtractionConfidence`

```python
class ExtractionConfidence(BaseModel):
    field: str
    value: Any
    confidence: float             # 0.0 to 1.0
    rationale: str | None = None  # why the model is uncertain (present only when confidence < 0.7)
```

| Field | Type | Description |
|---|---|---|
| `field` | str | Canonical field name (must match the extraction model field) |
| `value` | Any | The extracted value — duplicated here for convenience when inspecting low-confidence fields |
| `confidence` | float | Model self-reported confidence in [0.0, 1.0]. Must be calibrated (see Evaluation Spec) |
| `rationale` | str | Present only when `confidence < 0.7`. Explains the source of uncertainty |

**Confidence bands**:

| Range | Meaning | Agent behaviour |
|---|---|---|
| `>= 0.9` | High | Proceed to validation |
| `0.7 – 0.89` | Medium | Proceed to validation, flag as warning if the field is involved in a mismatch |
| `0.5 – 0.69` | Low | Planner should invoke `re_extract_field` with a narrower prompt before validating |
| `< 0.5` | Very low | Set `needs_human_review = true` on the session |

Confidence is emitted by the extraction prompt itself — the Gemini response schema includes a `confidence` field per extracted value. See Prompt Templates spec for the exact schema.

Extraction output is stored alongside the structured fields:

```python
class ExtractedDocument(BaseModel):
    fields: BoLFields | InvoiceFields | PackingListFields
    confidences: dict[str, ExtractionConfidence]   # keyed by canonical field name
```

---

### 1.3 Validation and Exception Models (`schemas/audit.py`)

---

#### `ValidationStatus` (Enum)

```python
from enum import Enum

class ValidationStatus(str, Enum):
    MATCH = "match"
    MINOR_MISMATCH = "minor_mismatch"
    CRITICAL_MISMATCH = "critical_mismatch"
```

| Value | Meaning |
|---|---|
| `match` | Field values are consistent across documents |
| `minor_mismatch` | Values differ in formatting or phrasing but are semantically equivalent |
| `critical_mismatch` | Values are substantively different — action required |

---

#### `ExceptionSeverity` (Enum)

```python
class ExceptionSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
```

| Value | Meaning |
|---|---|
| `info` | Informational — no action required |
| `warning` | Should be reviewed — likely minor but not guaranteed |
| `critical` | Must be resolved before customs submission |

---

#### `ValidationResult`

The output of a single validation tool call (`validate_field_match`, `validate_field_semantic`, `check_container_consistency`, etc.).

```python
class ValidationResult(BaseModel):
    field: str
    doc_a: str
    val_a: Any
    doc_b: str
    val_b: Any
    status: ValidationStatus
    reason: str
```

| Field | Type | Description |
|---|---|---|
| `field` | str | Canonical field name being compared (e.g. "incoterm") |
| `doc_a` | str | First document identifier: "bol" / "invoice" / "packing_list" |
| `val_a` | Any | Value from doc_a |
| `doc_b` | str | Second document identifier |
| `val_b` | Any | Value from doc_b |
| `status` | ValidationStatus | match / minor_mismatch / critical_mismatch |
| `reason` | str | Human-readable explanation of the outcome |

---

#### `Evidence`

Embedded inside every `ExceptionRecord`. Provides the traceability trail.

```python
class Evidence(BaseModel):
    doc_a: str          # "bol" | "invoice" | "packing_list"
    val_a: Any          # value from doc_a
    doc_b: str          # "bol" | "invoice" | "packing_list"
    val_b: Any          # value from doc_b
```

---

#### `ExceptionRecord`

A single flagged discrepancy produced by the `flag_exception` tool.

```python
class ExceptionRecord(BaseModel):
    exception_id: str           # uuid4
    severity: ExceptionSeverity
    field: str
    description: str
    evidence: Evidence
```

| Field | Type | Description |
|---|---|---|
| `exception_id` | str (uuid4) | Unique identifier for this exception |
| `severity` | ExceptionSeverity | info / warning / critical |
| `field` | str | Canonical field name that has the discrepancy |
| `description` | str | Human-readable explanation for the freight analyst |
| `evidence` | Evidence | Source document values for both sides of the discrepancy |

---

#### `AuditReport`

The compiled final output of the agent. Written to MongoDB on agent completion.

```python
class AuditReport(BaseModel):
    critical_count: int
    warning_count: int
    info_count: int
    passed_count: int
    summary: str
```

| Field | Type | Description |
|---|---|---|
| `critical_count` | int | Number of critical exceptions |
| `warning_count` | int | Number of warning exceptions |
| `info_count` | int | Number of info exceptions |
| `passed_count` | int | Number of fields validated with no issues |
| `summary` | str | One-sentence agent-generated summary of audit outcome |

---

#### `SessionStatus` (Enum)

```python
class SessionStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"
    AWAITING_REVIEW = "awaiting_review"
```

| Value | Meaning |
|---|---|
| `processing` | Agent is running |
| `complete` | Agent finished, report available, no human action required |
| `failed` | Agent hit a fatal error (extraction failed after retries, budget exhausted, etc.) |
| `awaiting_review` | Agent finished but flagged one or more fields as very-low-confidence. Report is available but explicitly not final — human review required |

---

### 1.4 Agent Trajectory Models (`schemas/agent.py`)

These models capture the agent's decision-making process. They are first-class persisted state — losing them defeats the transparency guarantee of a planner-driven agent.

---

#### `ToolCall`

A single invocation of a tool by the agent. Every tool call made during a session is recorded.

```python
class ToolCall(BaseModel):
    tool_call_id: str              # uuid4
    iteration: int                 # planner loop iteration this call belongs to
    tool_name: str
    args: dict
    result: Any                    # tool return value (JSON-serialisable)
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    status: Literal["success", "error"]
    error: str | None = None
```

| Field | Type | Description |
|---|---|---|
| `tool_call_id` | str (uuid4) | Unique ID for this call |
| `iteration` | int | Planner loop iteration (1-indexed) |
| `tool_name` | str | Must match a registered tool name |
| `args` | dict | Exact kwargs the tool was called with |
| `result` | Any | Return value, JSON-serialisable |
| `started_at` / `completed_at` | datetime | UTC timestamps |
| `duration_ms` | int | Wall-clock duration |
| `status` | enum | `success` or `error` |
| `error` | str | Error message if `status == "error"` |

---

#### `PlannerDecision`

What the planner chose at a given iteration and why.

```python
class PlannerDecision(BaseModel):
    iteration: int
    chosen_tools: list[str]       # tool names the planner picked this iteration (may be empty)
    rationale: str                # one-sentence explanation from the planner LLM
    terminate: bool               # true when planner decides the loop is done
    created_at: datetime
```

| Field | Type | Description |
|---|---|---|
| `iteration` | int | Planner loop iteration (1-indexed) |
| `chosen_tools` | list[str] | Tools queued for this iteration. Empty list + `terminate=True` means "compile report now" |
| `rationale` | str | Natural-language reasoning emitted by the planner LLM. Stored for traceability |
| `terminate` | bool | If `True`, the next node is `compile_report` — no further tool calls |
| `created_at` | datetime | UTC timestamp |

---

#### `AuditSession`

The top-level MongoDB document model. Represents a complete audit session including the agent's trajectory.

```python
class AuditSession(BaseModel):
    session_id: str                                           # uuid4 — primary lookup key
    status: SessionStatus
    created_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None

    extracted_fields: dict[str, Any] = {}                     # BoLFields | InvoiceFields | PackingListFields per key
    extraction_confidence: dict[str, dict[str, ExtractionConfidence]] = {}
                                                              # per-doc, per-field confidence
    exceptions: list[ExceptionRecord] = []
    report: AuditReport | None = None

    # Trajectory
    tool_calls: list[ToolCall] = []
    planner_decisions: list[PlannerDecision] = []
    iteration_count: int = 0
    needs_human_review: bool = False
    review_reasons: list[str] = []                            # human-readable reasons triggering review

    # Budget tracking
    tokens_used: int = 0
    elapsed_ms: int = 0
```

| Field | Type | Default | Description |
|---|---|---|---|
| `session_id` | str (uuid4) | required | Primary lookup key |
| `status` | SessionStatus | required | processing / complete / failed / awaiting_review |
| `created_at` | datetime | required | UTC timestamp of session creation |
| `completed_at` | datetime | None | UTC timestamp of agent completion |
| `error_message` | str | None | Set only when status is `failed` |
| `extracted_fields` | dict | `{}` | Keyed by doc type: `{"bol": BoLFields, ...}` |
| `extraction_confidence` | dict | `{}` | Nested: `{"bol": {"incoterm": ExtractionConfidence, ...}, ...}` |
| `exceptions` | list | `[]` | All ExceptionRecords from agent run |
| `report` | AuditReport | None | Set only when status is `complete` or `awaiting_review` |
| `tool_calls` | list | `[]` | Ordered trajectory of every tool invocation |
| `planner_decisions` | list | `[]` | One entry per planner loop iteration |
| `iteration_count` | int | 0 | Number of planner iterations consumed |
| `needs_human_review` | bool | False | True when any field has confidence < 0.5 or planner explicitly escalates |
| `review_reasons` | list[str] | `[]` | Why review was triggered (e.g. "gross_weight extracted with confidence 0.42") |
| `tokens_used` | int | 0 | Cumulative Gemini tokens consumed by this session |
| `elapsed_ms` | int | 0 | Wall-clock time from session start to terminal state |

---

### 1.5 API Request/Response Models (`schemas/api.py`)

---

#### `UploadResponse`

```python
class UploadResponse(BaseModel):
    session_id: str
    message: str
    documents_received: list[str]
    raw_text_lengths: dict[str, int]
```

---

#### `AuditRequest`

```python
class AuditRequest(BaseModel):
    session_id: str
```

---

#### `AuditResponse`

```python
class AuditResponse(BaseModel):
    session_id: str
    status: SessionStatus
    message: str
    created_at: datetime
```

---

#### `SessionSummary`

Used in the `GET /sessions` list response.

```python
class SessionSummary(BaseModel):
    session_id: str
    status: SessionStatus
    created_at: datetime
    completed_at: datetime | None = None
    critical_count: int | None = None
    warning_count: int | None = None
    info_count: int | None = None
    needs_human_review: bool = False
    iteration_count: int = 0
```

---

#### `SessionListResponse`

```python
class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]
    total: int
```

---

#### `TrajectoryResponse`

Used by the `GET /sessions/:id/trajectory` endpoint. Returns the agent's decision log without the heavier extracted-fields payload.

```python
class TrajectoryResponse(BaseModel):
    session_id: str
    status: SessionStatus
    iteration_count: int
    planner_decisions: list[PlannerDecision]
    tool_calls: list[ToolCall]
    tokens_used: int
    elapsed_ms: int
```

---

## 2. LangGraph Agent State (`agent/graph.py`)

The `AgentState` TypedDict is the state object passed through all LangGraph nodes. Each node receives the full state and returns a partial update.

```python
from typing import TypedDict, Any, Literal

class AgentState(TypedDict):
    # ---- Raw input ----
    session_id: str
    raw_texts: dict[str, str]
    # Keys: "bol", "invoice", "packing_list"
    # Values: raw extracted text from PyMuPDF

    # ---- Extraction output ----
    extracted_fields: dict[str, Any]
    # Keys: "bol", "invoice", "packing_list"
    # Values: BoLFields | InvoiceFields | PackingListFields (as dicts for JSON serialisation)

    extraction_confidence: dict[str, dict[str, dict]]
    # Nested: { "bol": { "incoterm": {"field": ..., "value": ..., "confidence": 0.92, "rationale": null}, ... }, ... }
    # Values are ExtractionConfidence dicts

    # ---- Planner & trajectory ----
    plan: list[str]
    # Tool names the planner has queued for the current iteration
    # Consumed FIFO by execute_tool; empty list means planner must re-plan or terminate

    tool_calls: list[dict]
    # Ordered list of ToolCall dicts — the agent's full trajectory

    planner_decisions: list[dict]
    # One PlannerDecision dict per iteration

    iteration_count: int
    # Incremented each time plan_validations runs. Hard cap defined in agent config (default 8)

    # ---- Validation accumulators ----
    validations: list[dict]
    # List of ValidationResult dicts

    exceptions: list[dict]
    # List of ExceptionRecord dicts

    # ---- Terminal state ----
    report: dict | None
    # AuditReport dict — set only by compile_report node

    needs_human_review: bool
    # True when any extraction confidence < 0.5 or planner explicitly escalates

    review_reasons: list[str]
    # Human-readable reasons triggering review. Empty unless needs_human_review is True

    # ---- Budget & errors ----
    tokens_used: int
    elapsed_ms: int
    error: str | None
    # Set by any node that encounters a fatal error (extraction failure after retries,
    # budget exhausted, planner iteration cap hit). Causes graph to route to compile_report
    # with status=failed rather than crashing.

    status: Literal["processing", "complete", "failed", "awaiting_review"]
    # Mirrored to MongoDB on every node completion for real-time polling
```

**Rules**:
- Nodes must never mutate state directly — always return a partial dict
- All Pydantic models are serialised to dicts before being stored in state (for JSON compatibility)
- The `error` field is checked at the start of every node — if set, node routes to `compile_report` for graceful shutdown, never silent crash
- `iteration_count` is incremented by `plan_validations` only, not by tool executions
- `plan` is drained by `execute_tool` as tools are dispatched; an empty `plan` plus `terminate=True` from the last planner decision routes to `compile_report`

---

## 3. MongoDB Document Schema

Collection: `audit_sessions`

This is the exact shape of a document as stored in MongoDB Atlas. Field names here must match the Pydantic model field names exactly.

```json
{
  "_id": "<ObjectId — auto-generated by MongoDB>",
  "session_id": "<uuid4 string>",
  "status": "processing | complete | failed | awaiting_review",
  "created_at": "<ISODate>",
  "completed_at": "<ISODate> | null",
  "error_message": "<string> | null",

  "needs_human_review": "<bool>",
  "review_reasons": ["<string>"],

  "iteration_count": "<int>",
  "tokens_used": "<int>",
  "elapsed_ms": "<int>",

  "extraction_confidence": {
    "bol": {
      "<field_name>": {
        "field": "<string>",
        "value": "<any>",
        "confidence": "<float 0.0-1.0>",
        "rationale": "<string> | null"
      }
    },
    "invoice": { "...": "..." },
    "packing_list": { "...": "..." }
  },

  "tool_calls": [
    {
      "tool_call_id": "<uuid4>",
      "iteration": "<int>",
      "tool_name": "<string>",
      "args": { "...": "..." },
      "result": "<any>",
      "started_at": "<ISODate>",
      "completed_at": "<ISODate>",
      "duration_ms": "<int>",
      "status": "success | error",
      "error": "<string> | null"
    }
  ],

  "planner_decisions": [
    {
      "iteration": "<int>",
      "chosen_tools": ["<string>"],
      "rationale": "<string>",
      "terminate": "<bool>",
      "created_at": "<ISODate>"
    }
  ],

  "extracted_fields": {
    "bol": {
      "bill_of_lading_number": "<string>",
      "shipper": "<string>",
      "consignee": "<string>",
      "vessel_name": "<string>",
      "port_of_loading": "<string>",
      "port_of_discharge": "<string>",
      "container_numbers": ["<string>"],
      "description_of_goods": "<string>",
      "gross_weight": "<float>",
      "incoterm": "<string>"
    },
    "invoice": {
      "invoice_number": "<string>",
      "seller": "<string>",
      "buyer": "<string>",
      "invoice_date": "<string YYYY-MM-DD>",
      "line_items": [
        {
          "description": "<string>",
          "quantity": "<int>",
          "unit_price": "<float>",
          "net_weight": null
        }
      ],
      "total_value": "<float>",
      "currency": "<string ISO 4217>",
      "incoterm": "<string>"
    },
    "packing_list": {
      "total_packages": "<int>",
      "total_weight": "<float>",
      "container_numbers": ["<string>"],
      "line_items": [
        {
          "description": "<string>",
          "quantity": "<int>",
          "unit_price": null,
          "net_weight": "<float>"
        }
      ]
    }
  },

  "exceptions": [
    {
      "exception_id": "<uuid4 string>",
      "severity": "critical | warning | info",
      "field": "<string>",
      "description": "<string>",
      "evidence": {
        "doc_a": "bol | invoice | packing_list",
        "val_a": "<any>",
        "doc_b": "bol | invoice | packing_list",
        "val_b": "<any>"
      }
    }
  ],

  "report": {
    "critical_count": "<int>",
    "warning_count": "<int>",
    "info_count": "<int>",
    "passed_count": "<int>",
    "summary": "<string>"
  }
}
```

### MongoDB Indexes

```javascript
// Primary lookup — must be unique
db.audit_sessions.createIndex({ "session_id": 1 }, { unique: true })

// Session history — ordered by most recent first
db.audit_sessions.createIndex({ "created_at": -1 })
```

---

## 4. Frontend TypeScript Interfaces

These interfaces must mirror the API response shapes exactly. Defined in `frontend/src/types/index.ts`.

```typescript
export type SessionStatus = "processing" | "complete" | "failed" | "awaiting_review"
export type ExceptionSeverity = "critical" | "warning" | "info"
export type DocumentType = "bol" | "invoice" | "packing_list"
export type ToolCallStatus = "success" | "error"

export interface ExtractionConfidence {
  field: string
  value: unknown
  confidence: number
  rationale: string | null
}

export interface ToolCall {
  tool_call_id: string
  iteration: number
  tool_name: string
  args: Record<string, unknown>
  result: unknown
  started_at: string
  completed_at: string
  duration_ms: number
  status: ToolCallStatus
  error: string | null
}

export interface PlannerDecision {
  iteration: number
  chosen_tools: string[]
  rationale: string
  terminate: boolean
  created_at: string
}

export interface LineItem {
  description: string
  quantity: number
  unit_price: number | null
  net_weight: number | null
}

export interface BoLFields {
  bill_of_lading_number: string
  shipper: string
  consignee: string
  vessel_name: string
  port_of_loading: string
  port_of_discharge: string
  container_numbers: string[]
  description_of_goods: string
  gross_weight: number
  incoterm: string
}

export interface InvoiceFields {
  invoice_number: string
  seller: string
  buyer: string
  invoice_date: string
  line_items: LineItem[]
  total_value: number
  currency: string
  incoterm: string
}

export interface PackingListFields {
  total_packages: number
  total_weight: number
  container_numbers: string[]
  line_items: LineItem[]
}

export interface Evidence {
  doc_a: DocumentType
  val_a: unknown
  doc_b: DocumentType
  val_b: unknown
}

export interface ExceptionRecord {
  exception_id: string
  severity: ExceptionSeverity
  field: string
  description: string
  evidence: Evidence
}

export interface AuditReport {
  critical_count: number
  warning_count: number
  info_count: number
  passed_count: number
  summary: string
}

export interface AuditSession {
  session_id: string
  status: SessionStatus
  created_at: string
  completed_at: string | null
  error_message: string | null

  extracted_fields: {
    bol?: BoLFields
    invoice?: InvoiceFields
    packing_list?: PackingListFields
  }
  extraction_confidence: {
    bol?: Record<string, ExtractionConfidence>
    invoice?: Record<string, ExtractionConfidence>
    packing_list?: Record<string, ExtractionConfidence>
  }

  exceptions: ExceptionRecord[]
  report: AuditReport | null

  tool_calls: ToolCall[]
  planner_decisions: PlannerDecision[]
  iteration_count: number
  needs_human_review: boolean
  review_reasons: string[]

  tokens_used: number
  elapsed_ms: number
}

export interface SessionSummary {
  session_id: string
  status: SessionStatus
  created_at: string
  completed_at: string | null
  critical_count: number | null
  warning_count: number | null
  info_count: number | null
  needs_human_review: boolean
  iteration_count: number
}

export interface SessionListResponse {
  sessions: SessionSummary[]
  total: number
}
```

---

## 5. Validation Catalogue

This is the **catalogue of validations available to the planner**. It is not a fixed sequence — the planner chooses which validations to invoke on each session based on what was extracted and the confidence scores. Field names here are the canonical identifiers used in `ExceptionRecord.field` and `ValidationResult.field`. They must never be abbreviated or renamed.

Every validation below maps to one or more invocations of the agent tools defined in the System Design (`validate_field_match`, `validate_field_semantic`, `check_container_consistency`, `check_incoterm_port_plausibility`, `check_container_number_format`).

| Canonical Field Name | Compared Across | Validation Type | Tool |
|---|---|---|---|
| `incoterm` | BoL ↔ Invoice | String — exact (uppercased) | `validate_field_match` |
| `shipper_seller` | BoL (shipper) ↔ Invoice (seller) | String — semantic (Gemini) | `validate_field_semantic` |
| `consignee_buyer` | BoL (consignee) ↔ Invoice (buyer) | String — semantic (Gemini) | `validate_field_semantic` |
| `total_quantity` | Invoice (sum of line_items.quantity) ↔ Packing List (sum of line_items.quantity) | Numeric — exact | `validate_field_match` |
| `total_weight` | BoL (gross_weight) ↔ Packing List (total_weight) | Numeric — tolerance ±0.5 kg | `validate_field_match` |
| `container_numbers` | BoL ↔ Packing List | List — set equality | `check_container_consistency` |
| `description_of_goods` | BoL ↔ Invoice (line_items[0].description) | String — semantic (Gemini) | `validate_field_semantic` |
| `invoice_total_vs_line_items` | Invoice (total_value) ↔ sum of (quantity × unit_price) | Numeric — tolerance ±0.01 | `validate_field_match` |
| `incoterm_port_plausibility` | Invoice (incoterm) + BoL (port_of_loading, port_of_discharge) | Domain rule — see below | `check_incoterm_port_plausibility` |
| `container_number_format` | BoL (container_numbers) and Packing List (container_numbers) | Programmatic — ISO 6346 check-digit | `check_container_number_format` |
| `currency_seller_plausibility` | Invoice (currency) + Invoice (seller country inferred) | Domain rule — warning only | `validate_field_semantic` |

**Domain rule details**:

- **`incoterm_port_plausibility`**: EXW should not carry freight charges and the named place should be origin-adjacent. CIF/CIP require a named destination port that matches BoL `port_of_discharge`. FOB requires a named origin port matching BoL `port_of_loading`. Mismatch → `critical`.
- **`container_number_format`**: Validates each container number against ISO 6346 (4 letters + 7 digits with mod-11 check digit). Purely programmatic — no LLM required. Invalid format → `warning`.
- **`currency_seller_plausibility`**: Rough heuristic — a seller with an obviously non-matching currency (e.g. German seller invoicing in INR, Chinese seller invoicing in BRL) is flagged as `info`. Never `critical`.

---

## 6. Validation Tolerance Rules

| Field Type | Comparison Method | Tolerance |
|---|---|---|
| Numeric (weight) | Absolute difference | ±0.5 kg |
| Numeric (monetary) | Absolute difference | ±0.01 (currency unit) |
| Numeric (quantity) | Exact integer match | 0 |
| String (names, descriptions) | Gemini semantic comparison | N/A — Gemini decides |
| String (codes: incoterm, currency) | Exact string match (uppercased) | 0 |
| List (container numbers) | Set equality (order-insensitive) | 0 |
