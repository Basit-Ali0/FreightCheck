// frontend/src/types/index.ts — canonical TS interfaces mirrored from Data Models spec section 4.

export type SessionStatus = "processing" | "complete" | "failed" | "awaiting_review";
export type ExceptionSeverity = "critical" | "warning" | "info";
export type DocumentType = "bol" | "invoice" | "packing_list";
export type ToolCallStatus = "success" | "error";

export interface ExtractionConfidence {
  field: string;
  value: unknown;
  confidence: number;
  rationale: string | null;
}

export interface ToolCall {
  tool_call_id: string;
  iteration: number;
  tool_name: string;
  args: Record<string, unknown>;
  result: unknown;
  started_at: string;
  completed_at: string;
  duration_ms: number;
  status: ToolCallStatus;
  error: string | null;
}

export interface PlannerDecision {
  iteration: number;
  chosen_tools: string[];
  rationale: string;
  terminate: boolean;
  created_at: string;
}

export interface LineItem {
  description: string;
  quantity: number;
  unit_price: number | null;
  net_weight: number | null;
}

export interface BoLFields {
  bill_of_lading_number: string;
  shipper: string;
  consignee: string;
  vessel_name: string;
  port_of_loading: string;
  port_of_discharge: string;
  container_numbers: string[];
  description_of_goods: string;
  gross_weight: number;
  incoterm: string;
}

export interface InvoiceFields {
  invoice_number: string;
  seller: string;
  buyer: string;
  invoice_date: string;
  line_items: LineItem[];
  total_value: number;
  currency: string;
  incoterm: string;
}

export interface PackingListFields {
  total_packages: number;
  total_weight: number;
  container_numbers: string[];
  line_items: LineItem[];
}

export interface Evidence {
  doc_a: string;
  val_a: unknown;
  doc_b: string;
  val_b: unknown;
}

export interface ExceptionRecord {
  exception_id: string;
  severity: ExceptionSeverity;
  field: string;
  description: string;
  evidence: Evidence;
}

export interface AuditReport {
  critical_count: number;
  warning_count: number;
  info_count: number;
  passed_count: number;
  summary: string;
}

export interface AuditSession {
  session_id: string;
  status: SessionStatus;
  created_at: string;
  completed_at: string | null;
  error_message: string | null;

  extracted_fields: {
    bol?: BoLFields;
    invoice?: InvoiceFields;
    packing_list?: PackingListFields;
  };
  extraction_confidence: {
    bol?: Record<string, ExtractionConfidence>;
    invoice?: Record<string, ExtractionConfidence>;
    packing_list?: Record<string, ExtractionConfidence>;
  };

  exceptions: ExceptionRecord[];
  report: AuditReport | null;

  tool_calls: ToolCall[];
  planner_decisions: PlannerDecision[];
  iteration_count: number;
  needs_human_review: boolean;
  review_reasons: string[];

  tokens_used: number;
  elapsed_ms: number;
}

export interface SessionSummary {
  session_id: string;
  status: SessionStatus;
  created_at: string;
  completed_at: string | null;
  critical_count: number | null;
  warning_count: number | null;
  info_count: number | null;
  needs_human_review: boolean;
  iteration_count: number;
}

export interface SessionListResponse {
  sessions: SessionSummary[];
  total: number;
}

/** `POST /upload` */
export interface UploadResponse {
  session_id: string;
  message: string;
  documents_received: string[];
  raw_text_lengths: Record<string, number>;
}

/** `POST /audit` */
export interface AuditResponse {
  session_id: string;
  status: SessionStatus;
  message: string;
  created_at: string;
}

/** `GET /sessions/:id/trajectory` */
export interface TrajectoryResponse {
  session_id: string;
  status: SessionStatus;
  iteration_count: number;
  planner_decisions: PlannerDecision[];
  tool_calls: ToolCall[];
  tokens_used: number;
  elapsed_ms: number;
}
