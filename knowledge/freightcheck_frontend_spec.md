# FreightCheck — Frontend Spec

**Version**: 1.0
**Status**: Draft
**Author**: Basit Ali
**Last Updated**: 2026-04-18

---

## Purpose

Every page, component, hook, and API call the frontend needs. This doc prevents the coding agent from making arbitrary UI decisions that drift from the backend contract or each other.

Stack is fixed in **Implementation Rules §4**: React 18 + Vite + TypeScript (strict) + Tailwind + Zustand + React Router. No React Query. All types from `src/types/index.ts`.

---

## 1. Information Architecture

### 1.1 Pages (Routes)

| Route | Component | Purpose |
|---|---|---|
| `/` | `UploadPage` | Three upload slots + Run Audit button. Entry point |
| `/sessions` | `SessionsPage` | List of all past audits |
| `/sessions/:id` | `SessionDetailPage` | Processing view OR report view OR error view — dispatches by status |

No other routes. Deep linking to `/sessions/:id` is the canonical way to share a specific audit.

### 1.2 Navigation

A thin header visible on every page:
- Logo / wordmark on the left (`FreightCheck`) — clicking returns to `/`
- Link to `Sessions` on the right

No hamburger menu. No settings page. No user account.

### 1.3 Visual Tone

- Professional / utilitarian. Not playful. This is an auditing tool.
- Monospace for all IDs (session_id, container numbers, BoL numbers).
- Clear semantic colour for severity and confidence. See §6.
- Generous whitespace. Mobile is explicitly non-goal per PRD — target 1280px+ desktop.

---

## 2. Pages

### 2.1 `UploadPage`

**Route**: `/`
**File**: `src/pages/UploadPage.tsx`

**Layout** (top to bottom):
1. Header
2. H1: "Audit Shipping Documents"
3. Subheading paragraph explaining the three documents needed
4. Three `UploadSlot` components side by side (equal width, 1fr each)
5. `RunAuditButton` centred below the slots
6. (Below) A small text link: "View past sessions →" → `/sessions`

**State** (Zustand store, `src/state/uploadState.ts`):
```ts
interface UploadState {
  bol: File | null;
  invoice: File | null;
  packingList: File | null;
  isUploading: boolean;
  isAuditing: boolean;
  error: string | null;

  setFile(slot: DocumentType, file: File | null): void;
  clear(): void;
  submit(): Promise<string>;  // returns session_id, navigates to /sessions/:id on success
}
```

**Submit flow**:
1. Validate all three slots are filled client-side. If not, show inline error.
2. Call `POST /upload` with FormData (via `api/upload.ts`). On error, show the server's `detail` string.
3. Call `POST /audit` with the returned `session_id`. On error, show the server's `detail`.
4. Navigate to `/sessions/:id`.

**Edge cases**:
- If a user clicks Run Audit twice: disable the button while `isUploading || isAuditing`. Also disable individual slots during upload.
- If a file is dragged over a wrong slot: the slot still accepts it (slot role is by labelling, not by file content detection).

### 2.2 `SessionsPage`

**Route**: `/sessions`
**File**: `src/pages/SessionsPage.tsx`

**Layout**:
1. Header
2. H1: "Past Sessions"
3. If sessions list is empty: centered empty-state with a link back to `/`
4. Otherwise: a table of `SessionListRow` components, one per session, ordered newest first

**Data fetching**: one call to `GET /sessions` on mount. No polling. A "Refresh" button in the top-right re-fetches.

**Row click** → navigates to `/sessions/:id`.

**Columns in the table**:

| Column | Source | Formatting |
|---|---|---|
| Created | `created_at` | Relative time ("2 minutes ago") with absolute on hover |
| Session ID | `session_id` | First 8 chars, monospace, full ID on hover |
| Status | `status` | Colour-coded badge (see §6.2) |
| Findings | `critical_count`, `warning_count`, `info_count` | Three inline pills, `—` if not complete |
| Review | `needs_human_review` | Amber icon if true, empty otherwise |
| Iterations | `iteration_count` | Plain number |

### 2.3 `SessionDetailPage`

**Route**: `/sessions/:id`
**File**: `src/pages/SessionDetailPage.tsx`

**Behaviour**: this page is a dispatcher based on `session.status`:

| Status | Renders |
|---|---|
| `processing` | `ProcessingView` (see §3.3) — polls `/sessions/:id/trajectory` every 2s |
| `complete` | `ReportView` + `TrajectoryTimeline` (two tabs) |
| `awaiting_review` | `ReportView` with `ReviewBanner` on top + `TrajectoryTimeline` tab |
| `failed` | `ErrorDisplay` with `error_message` |

**Initial load**: single fetch of `GET /sessions/:id`. If status is `processing`, start polling.

**Polling**: the `usePollSession` hook polls `/sessions/:id/trajectory` (cheaper) every 2s. When a terminal status appears, re-fetches the full `/sessions/:id` once and stops polling. See `src/hooks/usePollSession.ts`.

**Timeout**: if still `processing` after 60 seconds of polling, stop and show a timeout toast with a "Refresh" action.

---

## 3. Components

All components live in `src/components/`. Each takes typed props from `src/types/`.

### 3.1 `UploadSlot`

**Props**: `{ slot: DocumentType; label: string; file: File | null; onChange(file: File | null): void; disabled?: boolean }`

**Visual states**:
- **Empty** — dashed border, centered icon, "Drop or click to upload" text, slot label below
- **File selected** — filled border, filename + size, small "Replace" button, "×" remove button
- **Invalid (non-PDF)** — red border, error message: "Must be a PDF"
- **Disabled** (during upload) — reduced opacity, no interactions

**Behaviour**:
- Accepts click to open file picker and drag-drop
- `accept="application/pdf"` on the hidden input
- Files > `MAX_FILE_SIZE_MB` (10) are rejected client-side with an inline error

### 3.2 `RunAuditButton`

**Props**: `{ ready: boolean; loading: boolean; onClick(): void }`

- `ready = false` → disabled, muted colour, label "Upload all three documents"
- `ready = true && loading = false` → primary colour, label "Run Audit"
- `loading = true` → disabled, spinner, label "Starting audit..."

### 3.3 `ProcessingView`

**Props**: `{ trajectory: TrajectoryResponse }`

**Layout**:
1. A prominent progress indicator (not a percent — an indeterminate spinner with text)
2. Current iteration count: "Iteration 2 of up to 8"
3. Live timeline: as planner decisions and tool calls arrive, they appear at the bottom of the list in real time
4. Tokens used: "18,420 / 50,000 tokens"
5. Elapsed: "14.2s"

The timeline uses `TrajectoryTimeline` in "live" mode (it auto-scrolls to bottom as items append). Old items remain visible so the user can read what happened.

### 3.4 `ReportView`

**Props**: `{ session: AuditSession }`

**Layout**:
1. `ReviewBanner` (only if `status === "awaiting_review"`)
2. Summary header: 4 stat cards (critical, warning, info, passed)
3. Report summary sentence (from `report.summary`) in large text
4. A row of tabs: **Findings** (default) | **Documents** | **Trajectory**
5. Each tab renders its respective content area below

**Findings tab**: a vertical list of `ExceptionCard` components, grouped by severity (critical first). Below, a collapsed section "Passed validations ({passed_count})" that expands on click.

**Documents tab**: three columns (BoL, Invoice, Packing List). Each column lists extracted fields with their confidence pill. Low-confidence fields are highlighted; hovering a confidence pill shows the rationale.

**Trajectory tab**: `TrajectoryTimeline` in "static" mode (the full, final trajectory).

### 3.5 `ExceptionCard`

**Props**: `{ exception: ExceptionRecord }`

**Layout**:
- Top row: severity badge + field name (monospace)
- Description paragraph
- "Evidence" sub-section showing a two-column comparison:
  - Left: `doc_a` label + `val_a` value
  - Right: `doc_b` label + `val_b` value
- For list-type values: render each item on its own line for readability

### 3.6 `ConfidencePill`

**Props**: `{ confidence: number; rationale?: string | null }`

**Visual**:
- `≥ 0.9` → green pill with "high"
- `0.7–0.89` → amber pill with "medium"
- `0.5–0.69` → orange pill with "low"
- `< 0.5` → red pill with "very low"

On hover: tooltip showing the exact confidence number (`0.42`) and the rationale string.

### 3.7 `ReviewBanner`

**Props**: `{ reasons: string[] }`

**Visual**: amber background banner at the top of the report view. Heading "Human review required". Below, a bulleted list of `reasons`. Stays visible until dismissed (dismiss button in the top-right of the banner) — dismissal is local UI state, does not mutate the session.

### 3.8 `TrajectoryTimeline`

**Props**: `{ plannerDecisions: PlannerDecision[]; toolCalls: ToolCall[]; mode: "live" | "static" }`

**Layout**: a vertical timeline with items in chronological order (merge decisions and tool calls by `iteration` then by time). Each item is:
- A `PlannerDecisionCard` for a decision
- A `ToolCallRow` for a tool call

`live` mode: auto-scrolls to the bottom when new items are appended.
`static` mode: renders everything, no auto-scroll.

Decisions and tool calls are visually distinct — decisions are wider cards with the rationale in italic; tool calls are compact rows.

### 3.9 `PlannerDecisionCard`

**Props**: `{ decision: PlannerDecision }`

**Visual**: a card with "Iteration N" badge, the `rationale` text in italic, a list of chosen tool names as chips, and a `terminate` indicator if true.

### 3.10 `ToolCallRow`

**Props**: `{ call: ToolCall }`

**Visual** (single row):
- Tool name (monospace)
- Args (truncated, expandable)
- Result or error (colour-coded by `status`)
- Duration (right-aligned, "20ms")

Click row to expand for full args and result JSON.

### 3.11 `SessionListRow`

**Props**: `{ session: SessionSummary }`

Renders a single table row for `SessionsPage` with the columns defined in §2.2.

### 3.12 `ErrorDisplay`

**Props**: `{ errorMessage: string; onRetry?(): void }`

Used for:
- Session status = `failed` — shows `error_message`, offers "Start new audit" link to `/`
- Network errors — shows the `ApiError.detail`, offers "Retry" button
- 404 / not-found — shows "Session not found" with link back to `/sessions`

---

## 4. Hooks

### 4.1 `usePollSession`

**Signature**:
```ts
function usePollSession(sessionId: string): {
  session: AuditSession | null;
  trajectory: TrajectoryResponse | null;
  error: ApiError | null;
  isPolling: boolean;
}
```

**Behaviour**:
1. On mount, fetch `GET /sessions/:id`. If terminal status, set `session` and don't poll.
2. If status is `processing`, start polling `GET /sessions/:id/trajectory` every 2s.
3. When polled trajectory shows a terminal status (`complete` / `awaiting_review` / `failed`), fetch `GET /sessions/:id` once and stop polling.
4. On 60s timeout while still `processing`, stop polling and set `error` to a timeout `ApiError`.
5. Cleanup: clear interval on unmount or session_id change.

**Rules**:
- Use `setInterval` + `clearInterval`, not recursion or `setTimeout` chains.
- Store the interval ID in a ref so React 18 Strict Mode double-effects don't leak intervals.
- Do not retry on transient network errors — one polling failure sets `error` and stops polling. The user can refresh.

### 4.2 `usePollTrajectory`

Low-level hook used by `usePollSession`. Only fetches the trajectory endpoint. Exposed as a separate hook so the eval-dashboard view (future) can reuse it.

---

## 5. State Management

### 5.1 Zustand Store — `uploadState`

Only one Zustand store in MVP, for the upload flow (which spans `UploadPage` and persists across a brief navigation to `/sessions/:id`).

```ts
// src/state/uploadState.ts
import { create } from "zustand";
import { DocumentType } from "@/types";
import { uploadFiles } from "@/api/upload";
import { startAudit } from "@/api/audit";

interface UploadState {
  bol: File | null;
  invoice: File | null;
  packingList: File | null;
  isUploading: boolean;
  isAuditing: boolean;
  error: string | null;
  setFile(slot: DocumentType, file: File | null): void;
  clear(): void;
  submit(): Promise<string>;
}

export const useUploadStore = create<UploadState>((set, get) => ({
  // ... implementation
}));
```

### 5.2 Everything Else

All other state is local: `useState`, `useReducer`, or derived from `usePollSession`. No global state beyond `uploadState`.

---

## 6. Visual Language

### 6.1 Colour Palette

Defined in `tailwind.config.js`:

| Token | Purpose | Suggested hex |
|---|---|---|
| `severity-critical` | Critical badges, banners | `#dc2626` (red-600) |
| `severity-warning` | Warning badges | `#d97706` (amber-600) |
| `severity-info` | Info badges | `#2563eb` (blue-600) |
| `severity-passed` | Passed validations | `#16a34a` (green-600) |
| `confidence-high` | Confidence ≥ 0.9 | `#16a34a` (green-600) |
| `confidence-medium` | Confidence 0.7–0.89 | `#d97706` (amber-600) |
| `confidence-low` | Confidence 0.5–0.69 | `#ea580c` (orange-600) |
| `confidence-very-low` | Confidence < 0.5 | `#dc2626` (red-600) |
| `status-processing` | Processing | `#2563eb` (blue-600) |
| `status-complete` | Complete | `#16a34a` (green-600) |
| `status-failed` | Failed | `#4b5563` (gray-600) |
| `status-awaiting-review` | Awaiting review | `#d97706` (amber-600) |

Background: near-white (`slate-50`) or dark (`slate-900`) — pick one and commit. Recommendation: light mode for MVP, dark mode out of scope.

### 6.2 Status Badge

A small uppercase pill used in the sessions list and session detail header:

```
processing → "PROCESSING" on blue-100 background, blue-700 text
complete → "COMPLETE" on green-100 background, green-700 text
failed → "FAILED" on gray-100 background, gray-700 text
awaiting_review → "REVIEW" on amber-100 background, amber-700 text
```

### 6.3 Typography

- Body: system font stack (Tailwind default).
- IDs, numbers, container numbers: monospace (`font-mono`).
- H1: 2rem, bold. H2: 1.5rem, semibold.
- No custom web fonts in MVP.

---

## 7. Error Handling (UI)

Every API error produces a user-visible message. Never show raw stack traces or JSON.

| Scenario | UX |
|---|---|
| Non-PDF upload | Inline in the specific `UploadSlot` |
| File too large | Inline in the specific `UploadSlot` |
| Upload 5xx | Toast: "Upload failed. {detail}. Try again." |
| Audit 4xx (SessionNotFound / DuplicateAudit) | Toast |
| Audit 5xx | Toast |
| Polling timeout | Toast with "Refresh" button |
| Session 404 | `ErrorDisplay` with link back to `/sessions` |
| Session failed status | `ErrorDisplay` showing `error_message` |
| Generic network error | Toast: "Couldn't reach the server" |

Toast implementation: a minimal in-house component at `components/Toast.tsx`. Do not add a third-party toast library.

---

## 8. Accessibility

MVP bar: no worse than a well-structured React app.

- Semantic HTML (`<button>`, `<header>`, `<main>`, `<table>`, `<label>`).
- Every icon button has an `aria-label`.
- Focus visible on all interactive elements (Tailwind `focus:ring` utilities).
- Every upload slot is a labelled drop zone (keyboard-accessible via file input fallback).
- Colour is never the only signal — severity has both colour and text.

Not in MVP: full screen reader pass, high-contrast theme, keyboard-first navigation flow tests.

---

## 9. Build & Configuration

### 9.1 `vite.config.ts`

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: { port: 5173 },
});
```

### 9.2 `tsconfig.json` (key settings)

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noImplicitReturns": true,
    "jsx": "react-jsx",
    "paths": { "@/*": ["./src/*"] }
  }
}
```

### 9.3 `package.json` scripts

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "lint": "eslint src --max-warnings 0",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```

---

## 10. Explicit Non-Goals (Frontend)

These are intentionally excluded from MVP. If the coding agent is tempted to add any of these, it should stop.

- Authentication UI (no login, no account menu)
- Dark mode
- Mobile responsive (target 1280px+ desktop only)
- i18n
- Settings page
- PDF viewer / preview
- Real-time collaboration
- Notifications (email, push)
- Analytics instrumentation
- A11y beyond the MVP bar in §8
- Any charting library (no graphs in MVP)
