import type { ApiError } from "@/api/client";
import { isRetryableClientError } from "@/api/client";

type Base = { className?: string };

export type ErrorDisplayProps =
  | (Base & {
      variant: "missing_session";
      message: string;
    })
  | (Base & { variant: "not_found" })
  | (Base & {
      variant: "session_load_failed";
      error: ApiError;
      onRetry?: () => void;
    })
  | (Base & {
      variant: "polling_paused";
      error: ApiError;
    })
  | (Base & {
      variant: "failed_audit";
      message: string;
      sessionId: string;
    })
  | (Base & { variant: "session_unavailable" });

const shell =
  "mx-auto max-w-xl rounded-lg border px-6 py-8 text-center shadow-sm";

function tone(variant: ErrorDisplayProps["variant"]): string {
  switch (variant) {
    case "not_found":
      return "border-slate-300 bg-slate-50 text-slate-900";
    case "missing_session":
    case "session_unavailable":
      return "border-amber-200 bg-amber-50 text-amber-950";
    case "session_load_failed":
      return "border-red-200 bg-red-50 text-red-900";
    case "polling_paused":
      return "border-amber-200 bg-amber-50 text-amber-950";
    case "failed_audit":
      return "border-red-200 bg-red-50 text-red-900";
    default:
      return "border-slate-200 bg-white text-slate-900";
  }
}

export function ErrorDisplay(props: ErrorDisplayProps) {
  const c = `${shell} ${tone(props.variant)} ${props.className ?? ""}`.trim();

  switch (props.variant) {
    case "missing_session":
      return (
        <div className={c}>
          <h1 className="text-lg font-semibold">Missing session</h1>
          <p className="mt-3 text-sm opacity-90">{props.message}</p>
        </div>
      );
    case "not_found":
      return (
        <div className={c}>
          <h1 className="text-lg font-semibold">Session not found</h1>
          <p className="mt-3 text-sm opacity-90">
            This session id does not exist or has been removed.
          </p>
          <p className="mt-2 font-mono text-xs opacity-70">HTTP 404</p>
        </div>
      );
    case "session_load_failed": {
      const retryable = isRetryableClientError(props.error);
      return (
        <div className={c}>
          <h1 className="text-lg font-semibold">Could not load session</h1>
          <p className="mt-2 font-mono text-xs opacity-80">{props.error.code}</p>
          <p className="mt-3 text-sm opacity-90">{props.error.detail}</p>
          {retryable && props.onRetry ? (
            <button
              type="button"
              className="mt-4 rounded-md border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-900 hover:bg-red-100"
              onClick={props.onRetry}
            >
              Retry
            </button>
          ) : null}
        </div>
      );
    }
    case "polling_paused":
      return (
        <div className={c}>
          <h1 className="text-lg font-semibold">Live updates paused</h1>
          <p className="mt-2 font-mono text-xs opacity-80">{props.error.code}</p>
          <p className="mt-3 text-sm opacity-90">{props.error.detail}</p>
        </div>
      );
    case "failed_audit":
      return (
        <div className={c}>
          <h1 className="text-lg font-semibold">Audit failed</h1>
          <p className="mt-2 font-mono text-xs opacity-80">{props.sessionId}</p>
          <p className="mt-3 text-sm opacity-90">{props.message}</p>
        </div>
      );
    case "session_unavailable":
      return (
        <div className={c}>
          <h1 className="text-lg font-semibold">Session unavailable</h1>
          <p className="mt-3 text-sm opacity-90">Unable to display this session.</p>
        </div>
      );
  }
}
