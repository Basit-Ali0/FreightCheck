# FreightCheck — Product Requirements Document

**Version**: 1.0  
**Status**: Draft  
**Author**: Basit Ali  
**Last Updated**: 2026-04-18

---

## 1. Executive Summary

### Problem Statement
Freight forwarders and logistics operators manually cross-check multiple shipping documents — Bills of Lading, Commercial Invoices, and Packing Lists — to identify discrepancies before customs clearance. This process is error-prone, time-consuming, and when missed, results in shipment holds, demurrage charges, and compliance penalties.

### Proposed Solution
FreightCheck is an AI-powered logistics document auditing system. Users upload three core shipping documents and a LangGraph-orchestrated agent extracts structured fields from each, cross-validates them against each other, and produces a structured exception report with severity-graded discrepancies and evidence trails.

### Success Criteria
- Field extraction accuracy >= 90% across all three document types on synthetic test set
- End-to-end audit completion (upload to report) <= 30 seconds for standard 3-document set
- Critical mismatch detection rate >= 95% on known-discrepancy test documents
- Exception report correctly cites source document and field for every flagged item
- Extraction confidence scores are calibrated: fields reported at ≥ 0.9 confidence are correct ≥ 90% of the time on the synthetic set
- Agent trajectory is fully inspectable — every planner decision, tool call, input, and output is persisted and exposed via the API
- Low-confidence extractions (< 0.5) trigger `awaiting_review` rather than being silently included in the report
- Extracted field values are grounded in source text — extraction prompts enforce source-span citation and the synthetic eval checks for non-grounded outputs

---

## 2. User Experience & Functionality

### User Personas

**Primary — Freight Operations Analyst**
Mid-level logistics professional responsible for document verification before customs submission. Handles 20–50 shipment document sets per week. Currently does this manually across spreadsheets and printed documents. Non-technical — needs a clean, simple UI.

**Secondary — Developer / Evaluator (Portfolio Context)**
A technical recruiter or engineering interviewer reviewing FreightCheck as a portfolio project. Needs to understand the agent architecture, see real agentic decision-making, and verify the system handles edge cases.

---

### User Stories & Acceptance Criteria

**Story 1 — Document Upload**
As a freight analyst, I want to upload my three shipping documents in one place so that I don't have to navigate multiple screens.

Acceptance Criteria:
- User can upload exactly three PDFs: Bill of Lading, Commercial Invoice, Packing List
- Each upload slot is labelled and distinct — no ambiguity about which document goes where
- Files up to 10MB are accepted
- Non-PDF files are rejected with a clear error message
- Upload state is preserved if one file fails — user does not need to re-upload all three

**Story 2 — Audit Execution**
As a freight analyst, I want to trigger an audit with one click so that the system checks all documents automatically.

Acceptance Criteria:
- Single "Run Audit" button becomes active only when all three documents are uploaded
- Processing state is shown with a visible indicator while the agent runs
- If audit fails (Gemini error, parsing failure), user sees a specific error message — not a generic crash
- Audit session is persisted in MongoDB regardless of outcome (status: failed or complete)

**Story 3 — Exception Report**
As a freight analyst, I want to see a clear report of all discrepancies so that I know exactly what needs to be corrected before submission.

Acceptance Criteria:
- Report shows a summary header: count of critical issues, warnings, and passed checks
- Every exception card shows: field name, what Document A said, what Document B said, severity badge, and reason for flagging
- Passed validations are also shown (collapsed by default) so the user can verify what was checked
- Report is human-readable without requiring knowledge of the underlying agent logic
- Each exception is traceable — source document and exact field is cited

**Story 4 — Session History**
As a freight analyst, I want to retrieve a previous audit session so that I can reference past checks without re-uploading.

Acceptance Criteria:
- Sessions page lists past audits with timestamp and status
- Clicking a session loads the full report without re-running the agent
- Sessions are stored persistently in MongoDB

**Story 5 — Agent Transparency**
As a freight analyst (and a technical evaluator), I want to see exactly what the agent decided to check and why so that I can trust the result and understand why a particular validation was or wasn't run.

Acceptance Criteria:
- Report view has a "Trajectory" tab showing ordered planner decisions and tool calls
- Each planner decision shows: iteration number, tools chosen, rationale text
- Each tool call shows: tool name, args, result, duration
- Trajectory is available even for `awaiting_review` and `failed` sessions (partial traces are useful for debugging)

**Story 6 — Human Review Escalation**
As a freight analyst, I want the agent to tell me when it is uncertain rather than silently guessing, so that I can apply judgement to ambiguous cases before submission.

Acceptance Criteria:
- Sessions with any extraction confidence < 0.5 end in `awaiting_review` status
- Report view displays a prominent banner on `awaiting_review` sessions
- The specific fields triggering review are highlighted with their confidence and rationale
- Report still contains all findings produced before escalation — review is additive, not blocking

---

### Non-Goals (Out of Scope for MVP)

- User authentication and multi-tenant access
- Support for document types beyond BoL, Commercial Invoice, and Packing List
- Automated correction or amendment of documents
- Integration with external customs or freight systems (e.g. Flexport, SAP TM)
- Real-time collaboration or sharing of audit reports
- Support for non-English documents
- Mobile-responsive design (desktop-only for MVP)
- Paid plans, billing, or rate limiting

---

## 3. AI System Requirements

### Agent Architecture
FreightCheck is a **planner-driven LangGraph agent**. After extracting structured fields from all three documents, a Gemini-backed planner (running in tool-calling mode via `bind_tools`) inspects what was extracted along with per-field confidence scores and decides which validation tools to invoke next. The loop continues until the planner signals termination or a budget cap is reached.

The planner is deliberately thin — it reasons about *which tool to call next*, not about freight logistics. All domain rules live in the tools themselves, which are deterministic and independently testable. If the planner misbehaves, the `compile_report` node runs the full catalogue of validations as a deterministic floor, so a usable report is always produced.

**Why not a fixed chain**: a fixed sequence wastes work running validations against low-confidence extractions and can't adapt to cheap-path sessions (matching high-confidence fields need no semantic check) or hard sessions (container mismatches need extra format checks). See System Design §5.4 for the full justification.

**Transparency contract**: every planner decision (chosen tools + rationale) and every tool invocation (args, result, timing) is persisted and exposed via the API. Users can inspect exactly what the agent did. See the Data Models spec for `PlannerDecision` and `ToolCall`.

### Tools the Agent Has Access To

These are LangGraph tools bound to the planner via `bind_tools`. The full signatures and docstrings live in `backend/agent/tools.py` and are the authoritative reference — the planner reads the docstrings to decide when to call each tool.

| Tool | Purpose |
|---|---|
| `validate_field_match` | Exact or tolerance-based comparison for numeric and exact-string fields |
| `validate_field_semantic` | Gemini-backed comparison for strings that may differ in formatting but be semantically equivalent (seller/shipper names, goods descriptions) |
| `re_extract_field` | Re-run extraction for a single field with a narrower prompt — used when confidence for that field is below 0.7 |
| `check_container_consistency` | Set-equality check of container numbers across BoL and Packing List |
| `check_incoterm_port_plausibility` | Domain rule: EXW/CIF/FOB have hard requirements about which ports must appear where |
| `check_container_number_format` | ISO 6346 mod-11 check-digit validation — purely programmatic |
| `flag_exception` | Record a domain-level exception the planner notices that doesn't fit a specific validation tool |
| `escalate_to_human_review` | Explicit escalation when the planner cannot resolve ambiguity |

### LLM Requirements
- **Model**: Google Gemini 2.5 Flash (via Google Generative AI Python SDK)
- **Extraction calls**: structured output via `response_schema` — each extraction returns both values and per-field confidence scores with a rationale for low-confidence cases
- **Planner calls**: tool-calling mode (`bind_tools`). Output constrained to `PlannerDecision` schema (chosen tool names + rationale + terminate flag). Any unregistered tool name is rejected before dispatch
- **Semantic validation calls**: structured output, focused rubric prompt (no free text)
- **Prompt ownership**: All prompts defined in `backend/agent/prompts.py` — no dynamic prompt construction outside this file
- **Injection defence**: untrusted document text wrapped in XML-style delimiters with explicit instructions that delimited content is data, not instructions. Schema-constrained output means injection attempts that try to rewrite format will fail validation. See System Design §3.5

### Evaluation Strategy

Extraction and agent-trajectory quality are evaluated independently. Both run as part of CI on every prompt change.

- **Extraction accuracy**: 10 synthetic document sets with known field values. Measure field-level accuracy (exact-match for codes/numerics, semantic-match for strings) per document type. Target: ≥ 90%.
- **Confidence calibration**: on the same set, bucket extracted fields by confidence band (0.9+, 0.7–0.89, 0.5–0.69, < 0.5) and measure accuracy per band. A calibrated system has accuracy that tracks the band. Target: 0.9+ band accuracy ≥ 90%.
- **Grounding**: synthetic set includes documents with subtly corrupted text (e.g. missing weight line). Verify the agent does not hallucinate a value — either low-confidence + rationale, or escalation to human review.
- **Mismatch detection**: 5 document sets with intentional discrepancies (quantity mismatch, incoterm conflict, missing container number, ISO 6346 bad check-digit, incoterm/port contradiction). Verify all are flagged at correct severity. Target: ≥ 95%.
- **False positive rate**: 5 fully consistent document sets. Verify zero critical exceptions raised.
- **Agent trajectory correctness**: annotated traces on 10 sessions, scoring whether the planner invoked the *right* tools given the state. Captures whether the planner adds value over the deterministic baseline.
- **Latency decomposition**: p50/p95 end-to-end and per-node. Target: end-to-end p95 ≤ 30 s. Extraction ≈ 10–15 s, planner loop ≈ 8–12 s, compile_report ≈ 1 s.
- **Cost**: tokens per session (p50/p95) and USD cost per session at current Gemini pricing. Target: p95 ≤ 50k tokens.

Full methodology, synthetic data generator spec, and harness design will live in the Evaluation Spec.

---

## 4. Technical Specifications

### Architecture Overview

```
User (Browser)
    ↓ uploads 3 PDFs
React + Vite Frontend (Vercel)
    ↓ POST /upload → POST /audit
FastAPI Backend (Render/Railway)
    ↓ PyMuPDF extracts raw text
    ↓ creates AuditSession in MongoDB (status: processing)
    ↓ triggers LangGraph agent (async background task)
LangGraph Agent
    ↓ Node: extract_all  (parallel fan-out → Gemini × 3 with confidence scores)
    ↓ Loop (max 8 iterations, token + time budgeted):
    ↓   Node: plan_validations  (Gemini bind_tools → PlannerDecision)
    ↓   Node: execute_tool       (runs chosen tools, records ToolCall trajectory)
    ↓   Node: reflect            (continue loop or terminate?)
    ↓ Node: compile_report       (runs deterministic baseline if budget exhausted,
    ↓                             sets status = complete | awaiting_review | failed)
MongoDB Atlas
    ↓ AuditSession updated after every node — full trajectory persisted
Frontend polls GET /sessions/:id  (or /sessions/:id/trajectory for lightweight updates)
    ↓ renders exception report + agent trajectory view
```

### Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite |
| Backend | Python 3.11+, FastAPI |
| Agent Orchestration | LangGraph |
| LLM | Google Gemini 2.5 Flash |
| PDF Parsing | PyMuPDF (fitz) |
| Data Validation | Pydantic v2 |
| Database | MongoDB Atlas (free tier) |
| Frontend Deployment | Vercel |
| Backend Deployment | Render or Railway |

### API Integration Points

- **Google Gemini API** — requires `GEMINI_API_KEY` env variable
- **MongoDB Atlas** — requires `MONGODB_URI` env variable
- **No third-party auth** — no authentication layer in MVP

### Security & Privacy

- Uploaded PDFs are held in memory only during processing — not written to disk or stored in the database
- Only extracted fields (structured JSON) and exception records are persisted in MongoDB
- No plaintext document content is stored
- `GEMINI_API_KEY` and `MONGODB_URI` must never be committed to the repository — enforced via `.gitignore` and `.env`
- CORS configured to allow only the Vercel frontend domain in production

---

## 5. Risks & Roadmap

### Phased Rollout

**MVP (Current Scope)**
- Three document upload (BoL, Invoice, Packing List)
- Planner-driven LangGraph agent with `extract_all` → planner loop → `compile_report`
- Per-field extraction confidence scores (calibrated against synthetic set)
- Full agent trajectory persisted (planner decisions + tool calls) and exposed via API
- Deterministic baseline validations as a floor if planner exhausts budget
- `awaiting_review` session status for low-confidence extractions
- Exception report with severity grading and evidence trails
- Session persistence in MongoDB
- Synthetic document generator + evaluation harness (CI-runnable)
- React frontend with upload, processing, report, and trajectory inspection views
- Session history page
- Deployed on Render (backend) + Vercel (frontend)

**v1.1 — Post-MVP Hardening**
- `POST /sessions/:id/resolve-review` endpoint and UI for human-in-the-loop resolution
- Structured tracing via LangSmith (currently only structured logs)
- SSE-based real-time node progress updates (replacing 2s polling)
- Prompt versioning and per-prompt eval regression tracking

**v2.0 — Future**
- Support for additional document types (Certificate of Origin, Customs Declaration)
- User authentication and session isolation
- PDF export of exception report
- Sanctions / denied-party screening tool (requires external data source)
- HS code consistency validation

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Gemini returns malformed JSON for complex documents | Medium | High | `response_schema` constraints + Pydantic validation + 2 retries with corrective prompt |
| PyMuPDF fails on scanned/image-only PDFs | High | Medium | Detect image-only PDFs early and return 422 with specific error |
| Planner loops or picks wrong tools | Medium | Medium | Hard iteration cap (8), token budget (50k), time budget (25s). On exhaustion `compile_report` runs deterministic baseline — planner is an optimisation, baseline is the floor |
| Planner returns unregistered tool name (including via injection) | Low | Medium | Dispatcher rejects unknown names before execution. Failed call recorded; planner re-plans |
| Prompt injection via malicious PDF text | Medium | High | Untrusted text isolated via XML-style delimiters; `response_schema` prevents format rewriting; no dynamic tool names accepted |
| Extraction confidence is miscalibrated | Medium | High | Calibration measured explicitly in eval; low-confidence fields trigger re-extraction or `awaiting_review` rather than being silently trusted |
| MongoDB Atlas free tier storage limit hit | Low | Low | Each session is small (<20KB even with full trajectory) |
| Gemini API rate limits during demo | Low | Medium | Exponential backoff on Gemini calls; budget cap limits per-session token use |
| Extracted field names drift between docs and frontend | Medium | High | All field names canonicalised in `schemas/documents.py` — single source of truth |
