# FreightCheck — API Contract

**Version**: 1.0  
**Status**: Draft  
**Author**: Basit Ali  
**Last Updated**: 2026-04-18  
**Base URL (Development)**: `http://localhost:8000`  
**Base URL (Production)**: `https://freightcheck-api.onrender.com` (placeholder)

---

## General Rules

- All request and response bodies are JSON unless the endpoint accepts file uploads (multipart/form-data)
- All timestamps are ISO 8601 UTC strings: `"2026-04-18T10:30:00Z"`
- All endpoints return `Content-Type: application/json`
- Authentication: None (MVP — no auth layer)
- CORS: Only the Vercel frontend origin is allowed in production
- File uploads: Maximum 10MB per file, PDF only
- On all errors, the response body always contains `{ "error": string, "detail": string }`
- Session status values: `processing`, `complete`, `failed`, `awaiting_review`
- Extraction `confidence` is a float in `[0.0, 1.0]`. Frontends should visually flag fields with confidence < 0.7 (medium) and always surface those with confidence < 0.5 (driving `awaiting_review`)

---

## Response Status Codes

| Code | Meaning |
|---|---|
| 200 | Success |
| 201 | Resource created |
| 400 | Bad request — invalid input |
| 404 | Resource not found |
| 413 | File too large |
| 422 | Unprocessable — valid format but cannot be processed (e.g. scanned PDF) |
| 500 | Internal server error |

---

## Endpoints

---

### POST `/upload`

Upload three shipping document PDFs. Extracts raw text from each and returns a `session_id` to be used in the subsequent `/audit` call.

**Request**

```
Content-Type: multipart/form-data
```

| Field | Type | Required | Description |
|---|---|---|---|
| `bol` | File (PDF) | Yes | Bill of Lading document |
| `invoice` | File (PDF) | Yes | Commercial Invoice document |
| `packing_list` | File (PDF) | Yes | Packing List document |

**Example Request (curl)**

```bash
curl -X POST http://localhost:8000/upload \
  -F "bol=@bill_of_lading.pdf" \
  -F "invoice=@commercial_invoice.pdf" \
  -F "packing_list=@packing_list.pdf"
```

**Success Response — 200**

```json
{
  "session_id": "3f7a1c2d-89b4-4e6f-a123-456789abcdef",
  "message": "Documents uploaded and parsed successfully",
  "documents_received": ["bol", "invoice", "packing_list"],
  "raw_text_lengths": {
    "bol": 1842,
    "invoice": 2310,
    "packing_list": 987
  }
}
```

| Field | Type | Description |
|---|---|---|
| `session_id` | string (uuid4) | Unique session identifier — pass to `/audit` |
| `message` | string | Human-readable status |
| `documents_received` | string[] | Confirms which documents were parsed |
| `raw_text_lengths` | object | Character count per document — useful for debugging |

**Error Responses**

```json
// 400 — Missing one or more files
{
  "error": "MissingDocumentError",
  "detail": "All three documents are required: bol, invoice, packing_list. Missing: packing_list"
}

// 400 — Wrong file type
{
  "error": "InvalidFileTypeError",
  "detail": "File 'invoice' must be a PDF. Received: image/jpeg"
}

// 413 — File too large
{
  "error": "FileTooLargeError",
  "detail": "File 'bol' exceeds the 10MB limit. Received: 14.3MB"
}

// 422 — Scanned / image-only PDF
{
  "error": "ImageOnlyPDFError",
  "detail": "File 'packing_list' contains no extractable text. Scanned PDFs are not supported in MVP."
}

// 500 — PDF parsing failure
{
  "error": "PDFParseError",
  "detail": "Failed to extract text from 'bol'. The file may be corrupted."
}
```

---

### POST `/audit`

Triggers the LangGraph agent for a given `session_id`. Creates an `AuditSession` in MongoDB and starts the agent as a background task. Returns immediately with `status: processing`.

**Request**

```json
{
  "session_id": "3f7a1c2d-89b4-4e6f-a123-456789abcdef"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | string (uuid4) | Yes | Returned from `/upload` |

**Example Request (curl)**

```bash
curl -X POST http://localhost:8000/audit \
  -H "Content-Type: application/json" \
  -d '{"session_id": "3f7a1c2d-89b4-4e6f-a123-456789abcdef"}'
```

**Success Response — 201**

```json
{
  "session_id": "3f7a1c2d-89b4-4e6f-a123-456789abcdef",
  "status": "processing",
  "message": "Audit started. Poll /sessions/3f7a1c2d-89b4-4e6f-a123-456789abcdef for results.",
  "created_at": "2026-04-18T10:30:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `session_id` | string | Echo of the session_id |
| `status` | string | Always `"processing"` on successful trigger |
| `message` | string | Includes the polling URL for convenience |
| `created_at` | string | ISO 8601 timestamp of session creation |

**Error Responses**

```json
// 400 — session_id missing from body
{
  "error": "ValidationError",
  "detail": "Field 'session_id' is required."
}

// 400 — session_id not found in upload cache
{
  "error": "SessionNotFoundError",
  "detail": "No upload found for session_id '3f7a1c2d...'. Upload documents first via POST /upload."
}

// 400 — audit already triggered for this session
{
  "error": "DuplicateAuditError",
  "detail": "An audit has already been triggered for session_id '3f7a1c2d...'. Poll /sessions/:id for results."
}

// 500 — MongoDB write failure
{
  "error": "DatabaseError",
  "detail": "Failed to create audit session. Please try again."
}
```

---

### GET `/sessions`

Returns a list of all audit sessions ordered by `created_at` descending. Used by the frontend session history page.

**Request**

No body. No query parameters in MVP.

**Example Request (curl)**

```bash
curl http://localhost:8000/sessions
```

**Success Response — 200**

```json
{
  "sessions": [
    {
      "session_id": "3f7a1c2d-89b4-4e6f-a123-456789abcdef",
      "status": "complete",
      "created_at": "2026-04-18T10:30:00Z",
      "completed_at": "2026-04-18T10:30:22Z",
      "critical_count": 2,
      "warning_count": 1,
      "info_count": 0,
      "needs_human_review": false,
      "iteration_count": 3
    },
    {
      "session_id": "7c8d9e10-11f2-4a5b-9c6d-7e8f9a0b1c2d",
      "status": "awaiting_review",
      "created_at": "2026-04-18T11:00:00Z",
      "completed_at": "2026-04-18T11:00:24Z",
      "critical_count": 0,
      "warning_count": 2,
      "info_count": 0,
      "needs_human_review": true,
      "iteration_count": 5
    },
    {
      "session_id": "9b2e4f1a-12c3-4d5e-b678-901234cdef56",
      "status": "failed",
      "created_at": "2026-04-18T09:15:00Z",
      "completed_at": null,
      "critical_count": null,
      "warning_count": null,
      "info_count": null,
      "needs_human_review": false,
      "iteration_count": 0
    }
  ],
  "total": 3
}
```

| Field | Type | Description |
|---|---|---|
| `sessions` | array | List of session summaries |
| `session_id` | string | Unique session identifier |
| `status` | string | `processing` / `complete` / `failed` / `awaiting_review` |
| `created_at` | string | When audit was triggered |
| `completed_at` | string / null | When agent finished. Null if processing or failed |
| `critical_count` | int / null | Count of critical exceptions. Null if not complete/awaiting_review |
| `warning_count` | int / null | Count of warnings. Null if not complete/awaiting_review |
| `info_count` | int / null | Count of info flags. Null if not complete/awaiting_review |
| `needs_human_review` | bool | True for `awaiting_review` sessions or any session where the planner escalated |
| `iteration_count` | int | Number of planner loop iterations consumed. 0 on `failed` sessions that didn't reach the planner |
| `total` | int | Total number of sessions |

**Error Responses**

```json
// 500 — MongoDB read failure
{
  "error": "DatabaseError",
  "detail": "Failed to retrieve sessions. Please try again."
}
```

---

### GET `/sessions/:id`

Returns the full detail of a single audit session including all extracted fields, exceptions, and the compiled report. This is the primary polling endpoint.

**Path Parameter**

| Parameter | Type | Description |
|---|---|---|
| `id` | string (uuid4) | The `session_id` from `/upload` or `/sessions` |

**Example Request (curl)**

```bash
curl http://localhost:8000/sessions/3f7a1c2d-89b4-4e6f-a123-456789abcdef
```

**Success Response — 200 (status: processing)**

```json
{
  "session_id": "3f7a1c2d-89b4-4e6f-a123-456789abcdef",
  "status": "processing",
  "created_at": "2026-04-18T10:30:00Z",
  "completed_at": null,
  "error_message": null,
  "extracted_fields": {},
  "extraction_confidence": {},
  "exceptions": [],
  "report": null,
  "tool_calls": [],
  "planner_decisions": [],
  "iteration_count": 0,
  "needs_human_review": false,
  "review_reasons": [],
  "tokens_used": 0,
  "elapsed_ms": 0
}
```

**Success Response — 200 (status: complete)**

```json
{
  "session_id": "3f7a1c2d-89b4-4e6f-a123-456789abcdef",
  "status": "complete",
  "created_at": "2026-04-18T10:30:00Z",
  "completed_at": "2026-04-18T10:30:22Z",
  "error_message": null,

  "extracted_fields": {
    "bol": {
      "bill_of_lading_number": "MSKU1234567",
      "shipper": "Acme Exports Pvt Ltd",
      "consignee": "Global Traders LLC",
      "vessel_name": "MSC AURORA",
      "port_of_loading": "Nhava Sheva, India",
      "port_of_discharge": "Jebel Ali, UAE",
      "container_numbers": ["MSCU1234567", "MSCU7654321"],
      "description_of_goods": "Textile Goods — Cotton Fabric",
      "gross_weight": 12400.0,
      "incoterm": "CIF"
    },
    "invoice": {
      "invoice_number": "INV-2026-0042",
      "seller": "Acme Exports Pvt Ltd",
      "buyer": "Global Traders LLC",
      "invoice_date": "2026-04-10",
      "line_items": [
        { "description": "Cotton Fabric", "quantity": 500, "unit_price": 12.50 }
      ],
      "total_value": 6250.00,
      "currency": "USD",
      "incoterm": "FOB"
    },
    "packing_list": {
      "total_packages": 50,
      "total_weight": 12400.0,
      "container_numbers": ["MSCU1234567", "MSCU7654321"],
      "line_items": [
        { "description": "Cotton Fabric", "quantity": 500, "net_weight": 248.0 }
      ]
    }
  },

  "extraction_confidence": {
    "bol": {
      "incoterm": { "field": "incoterm", "value": "CIF", "confidence": 0.98, "rationale": null },
      "gross_weight": { "field": "gross_weight", "value": 12400.0, "confidence": 0.94, "rationale": null },
      "container_numbers": { "field": "container_numbers", "value": ["MSCU1234567", "MSCU7654321"], "confidence": 0.99, "rationale": null }
    },
    "invoice": {
      "incoterm": { "field": "incoterm", "value": "FOB", "confidence": 0.97, "rationale": null },
      "total_value": { "field": "total_value", "value": 6250.00, "confidence": 0.99, "rationale": null }
    },
    "packing_list": {
      "total_weight": { "field": "total_weight", "value": 12400.0, "confidence": 0.95, "rationale": null },
      "container_numbers": { "field": "container_numbers", "value": ["MSCU1234567", "MSCU7654321"], "confidence": 0.99, "rationale": null }
    }
  },

  "exceptions": [
    {
      "exception_id": "e1a2b3c4-0001",
      "severity": "critical",
      "field": "incoterm",
      "description": "Incoterm is 'CIF' on the Bill of Lading but 'FOB' on the Commercial Invoice. These are conflicting trade terms that affect insurance and freight cost responsibility.",
      "evidence": {
        "doc_a": "bol",
        "val_a": "CIF",
        "doc_b": "invoice",
        "val_b": "FOB"
      }
    },
    {
      "exception_id": "e1a2b3c4-0002",
      "severity": "warning",
      "field": "description_of_goods",
      "description": "Description differs slightly between documents. BoL says 'Textile Goods — Cotton Fabric', Invoice says 'Cotton Fabric'. Likely a formatting difference but should be verified.",
      "evidence": {
        "doc_a": "bol",
        "val_a": "Textile Goods — Cotton Fabric",
        "doc_b": "invoice",
        "val_b": "Cotton Fabric"
      }
    }
  ],

  "report": {
    "critical_count": 1,
    "warning_count": 1,
    "info_count": 0,
    "passed_count": 8,
    "summary": "1 critical incoterm conflict detected between BoL and Invoice. Shipment should not be submitted until resolved."
  },

  "tool_calls": [
    {
      "tool_call_id": "tc-0001",
      "iteration": 1,
      "tool_name": "validate_field_match",
      "args": { "field": "incoterm", "doc_a": "bol", "doc_b": "invoice", "tolerance": 0.0 },
      "result": { "status": "critical_mismatch", "val_a": "CIF", "val_b": "FOB", "reason": "Exact string mismatch on trade term code" },
      "started_at": "2026-04-18T10:30:15.120Z",
      "completed_at": "2026-04-18T10:30:15.140Z",
      "duration_ms": 20,
      "status": "success",
      "error": null
    },
    {
      "tool_call_id": "tc-0002",
      "iteration": 1,
      "tool_name": "check_container_consistency",
      "args": {},
      "result": { "status": "match", "reason": "Container sets identical across BoL and Packing List" },
      "started_at": "2026-04-18T10:30:15.141Z",
      "completed_at": "2026-04-18T10:30:15.155Z",
      "duration_ms": 14,
      "status": "success",
      "error": null
    },
    {
      "tool_call_id": "tc-0003",
      "iteration": 2,
      "tool_name": "validate_field_semantic",
      "args": { "field": "description_of_goods", "doc_a": "bol", "doc_b": "invoice" },
      "result": { "status": "minor_mismatch", "reason": "Semantically equivalent but BoL description is broader. Flagged as warning." },
      "started_at": "2026-04-18T10:30:17.800Z",
      "completed_at": "2026-04-18T10:30:19.210Z",
      "duration_ms": 1410,
      "status": "success",
      "error": null
    }
  ],

  "planner_decisions": [
    {
      "iteration": 1,
      "chosen_tools": ["validate_field_match", "check_container_consistency"],
      "rationale": "Both incoterm values extracted with high confidence (>0.97) so exact match is appropriate. Container numbers extracted identically on both docs — run set-equality check.",
      "terminate": false,
      "created_at": "2026-04-18T10:30:15.100Z"
    },
    {
      "iteration": 2,
      "chosen_tools": ["validate_field_semantic"],
      "rationale": "description_of_goods values differ in surface form ('Textile Goods — Cotton Fabric' vs 'Cotton Fabric'). Needs semantic comparison, not exact match.",
      "terminate": false,
      "created_at": "2026-04-18T10:30:17.750Z"
    },
    {
      "iteration": 3,
      "chosen_tools": [],
      "rationale": "All catalogue validations complete. No low-confidence fields require re-extraction.",
      "terminate": true,
      "created_at": "2026-04-18T10:30:20.000Z"
    }
  ],

  "iteration_count": 3,
  "needs_human_review": false,
  "review_reasons": [],
  "tokens_used": 18420,
  "elapsed_ms": 22100
}
```

**Success Response — 200 (status: awaiting_review)**

Returned when any extracted field has confidence < 0.5, the planner explicitly escalates, or the planner budget was exhausted with low-confidence fields still present. The report is still produced — `awaiting_review` means "usable but not final", not "failed".

```json
{
  "session_id": "7c8d9e10-11f2-4a5b-9c6d-7e8f9a0b1c2d",
  "status": "awaiting_review",
  "created_at": "2026-04-18T11:00:00Z",
  "completed_at": "2026-04-18T11:00:24Z",
  "error_message": null,

  "extracted_fields": { "...": "..." },
  "extraction_confidence": {
    "bol": {
      "gross_weight": {
        "field": "gross_weight",
        "value": 12400.0,
        "confidence": 0.42,
        "rationale": "Weight appears in two places with conflicting values (12400 kg vs 13200 kg). Chose the one on the cargo manifest line."
      }
    }
  },
  "exceptions": [ "..." ],
  "report": { "...": "..." },
  "tool_calls": [ "..." ],
  "planner_decisions": [ "..." ],
  "iteration_count": 5,
  "needs_human_review": true,
  "review_reasons": [
    "bol.gross_weight extracted with confidence 0.42 — two conflicting values in source document"
  ],
  "tokens_used": 24100,
  "elapsed_ms": 24800
}
```

**Success Response — 200 (status: failed)**

```json
{
  "session_id": "9b2e4f1a-12c3-4d5e-b678-901234cdef56",
  "status": "failed",
  "created_at": "2026-04-18T09:15:00Z",
  "completed_at": null,
  "error_message": "GeminiAPIError: Failed to extract fields from 'invoice' after 2 retries. The document may be malformed.",
  "extracted_fields": {},
  "extraction_confidence": {},
  "exceptions": [],
  "report": null,
  "tool_calls": [],
  "planner_decisions": [],
  "iteration_count": 0,
  "needs_human_review": false,
  "review_reasons": [],
  "tokens_used": 14200,
  "elapsed_ms": 8100
}
```

**Error Responses**

```json
// 404 — session not found
{
  "error": "SessionNotFoundError",
  "detail": "No session found with id '9b2e4f1a-...'"
}

// 500 — MongoDB read failure
{
  "error": "DatabaseError",
  "detail": "Failed to retrieve session. Please try again."
}
```

---

### GET `/sessions/:id/trajectory`

Returns the agent's decision log without the heavier extracted-fields payload. Used by the frontend's "Trajectory" tab and by live polling during a session — cheaper to refetch every 2 seconds than the full `/sessions/:id` response.

**Path Parameter**

| Parameter | Type | Description |
|---|---|---|
| `id` | string (uuid4) | The `session_id` |

**Example Request (curl)**

```bash
curl http://localhost:8000/sessions/3f7a1c2d-89b4-4e6f-a123-456789abcdef/trajectory
```

**Success Response — 200**

```json
{
  "session_id": "3f7a1c2d-89b4-4e6f-a123-456789abcdef",
  "status": "complete",
  "iteration_count": 3,
  "planner_decisions": [
    {
      "iteration": 1,
      "chosen_tools": ["validate_field_match", "check_container_consistency"],
      "rationale": "Both incoterm values extracted with high confidence (>0.97)...",
      "terminate": false,
      "created_at": "2026-04-18T10:30:15.100Z"
    }
  ],
  "tool_calls": [
    {
      "tool_call_id": "tc-0001",
      "iteration": 1,
      "tool_name": "validate_field_match",
      "args": { "field": "incoterm", "doc_a": "bol", "doc_b": "invoice", "tolerance": 0.0 },
      "result": { "status": "critical_mismatch", "val_a": "CIF", "val_b": "FOB" },
      "started_at": "2026-04-18T10:30:15.120Z",
      "completed_at": "2026-04-18T10:30:15.140Z",
      "duration_ms": 20,
      "status": "success",
      "error": null
    }
  ],
  "tokens_used": 18420,
  "elapsed_ms": 22100
}
```

**Error Responses**

```json
// 404 — session not found
{
  "error": "SessionNotFoundError",
  "detail": "No session found with id '9b2e4f1a-...'"
}
```

---

### POST `/sessions/:id/resolve-review` *(v1.1 — reserved)*

Reserved for human-in-the-loop resolution of `awaiting_review` sessions. Not implemented in MVP but documented here so the shape is stable.

```json
// Planned request body
{
  "resolutions": [
    {
      "exception_id": "e1a2b3c4-0001",
      "action": "accept | override | reject",
      "override_value": "optional — required if action is 'override'",
      "reviewer_note": "optional"
    }
  ]
}
```

MVP clients should not call this endpoint. Documented here so future additions are not breaking.

---

## Frontend Polling Logic

The frontend polls `GET /sessions/:id/trajectory` every 2 seconds after triggering `/audit` to render the agent's live progress, then fetches `GET /sessions/:id` once on a terminal status for the full payload.

```javascript
// Pseudocode — api.js

async function pollSession(sessionId, onTerminal) {
  const interval = setInterval(async () => {
    const trajectory = await getTrajectory(sessionId)   // lightweight

    updateTrajectoryView(trajectory)  // render planner decisions + tool calls as they arrive

    if (["complete", "failed", "awaiting_review"].includes(trajectory.status)) {
      clearInterval(interval)
      const full = await getSession(sessionId)           // fetch full payload once
      onTerminal(full)
    }

    // status === "processing" → keep polling
  }, 2000)
}
```

Client code must handle all four terminal statuses distinctly:

| Status | UI treatment |
|---|---|
| `complete` | Render report normally |
| `awaiting_review` | Render report **plus** a prominent banner listing `review_reasons`; highlight low-confidence fields |
| `failed` | Show `error_message`; offer retry |
| `processing` | Continue polling |

**Polling timeout**: If status is still `processing` after 60 seconds, stop polling and show a timeout error. This guards against a silent agent hang.

---

## Exception Severity Reference

| Severity | Meaning | Example |
|---|---|---|
| `critical` | Must be resolved before submission — shipment will likely be held | Incoterm conflict, quantity mismatch between BoL and invoice |
| `warning` | Should be reviewed — likely a formatting difference but not guaranteed | Description phrased differently across documents |
| `info` | Informational — no action required but worth noting | Minor weight rounding difference within tolerance |

---

## Full Field Reference — Extracted Fields

### Bill of Lading (`extracted_fields.bol`)

| Field | Type | Description |
|---|---|---|
| `bill_of_lading_number` | string | Unique BoL reference number |
| `shipper` | string | Exporting party |
| `consignee` | string | Receiving party |
| `vessel_name` | string | Name of the carrying vessel |
| `port_of_loading` | string | Origin port |
| `port_of_discharge` | string | Destination port |
| `container_numbers` | string[] | List of container IDs |
| `description_of_goods` | string | Cargo description |
| `gross_weight` | float | Total weight in kg |
| `incoterm` | string | Trade term (e.g. CIF, FOB, EXW) |

### Commercial Invoice (`extracted_fields.invoice`)

| Field | Type | Description |
|---|---|---|
| `invoice_number` | string | Unique invoice reference |
| `seller` | string | Selling/exporting party |
| `buyer` | string | Buying/importing party |
| `invoice_date` | string | Date of invoice (YYYY-MM-DD) |
| `line_items` | array | List of items with description, quantity, unit_price |
| `total_value` | float | Total invoice value |
| `currency` | string | Currency code (e.g. USD, EUR) |
| `incoterm` | string | Trade term |

### Packing List (`extracted_fields.packing_list`)

| Field | Type | Description |
|---|---|---|
| `total_packages` | int | Total number of packages/cartons |
| `total_weight` | float | Total weight in kg |
| `container_numbers` | string[] | List of container IDs |
| `line_items` | array | List of items with description, quantity, net_weight |
