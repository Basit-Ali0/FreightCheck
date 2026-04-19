import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { POLL_TIMEOUT_CODE } from "@/api/client";
import { useToast } from "@/components/Toast";
import { ErrorDisplay } from "@/components/session/ErrorDisplay";
import { ProcessingView } from "@/components/session/ProcessingView";
import { ReportView } from "@/components/session/ReportView";
import { usePollSession } from "@/hooks/usePollSession";

const sessionPollToastKeys = new Set<string>();

function clearPollToastsForSession(sessionId: string) {
  for (const k of [...sessionPollToastKeys]) {
    if (k.startsWith(`${sessionId}:`)) {
      sessionPollToastKeys.delete(k);
    }
  }
}

export function SessionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { pushError } = useToast();
  const [refreshKey, setRefreshKey] = useState(0);
  const { session, trajectory, error, loading, notFound } = usePollSession(id, { refreshKey });

  useEffect(() => {
    if (!error || !id) return;
    const dedupeKey = `${id}:${error.code}:${error.detail}`;
    if (sessionPollToastKeys.has(dedupeKey)) return;
    sessionPollToastKeys.add(dedupeKey);

    if (error.code === POLL_TIMEOUT_CODE) {
      pushError(error.detail, {
        action: {
          label: "Refresh",
          onClick: () => {
            clearPollToastsForSession(id);
            setRefreshKey((k) => k + 1);
          },
        },
      });
      return;
    }
    pushError(error.detail);
  }, [error, id, pushError]);

  if (!id) {
    return (
      <ErrorDisplay
        variant="missing_session"
        message="No session id was provided in the URL."
      />
    );
  }

  if (notFound) {
    return <ErrorDisplay variant="not_found" />;
  }

  if (error && !session) {
    return (
      <ErrorDisplay
        variant="session_load_failed"
        error={error}
        onRetry={() => {
          clearPollToastsForSession(id);
          setRefreshKey((k) => k + 1);
        }}
      />
    );
  }

  if (loading && !session) {
    return (
      <div className="mx-auto max-w-xl py-16 text-center text-sm text-slate-600">
        Loading session…
      </div>
    );
  }

  if (!session) {
    return <ErrorDisplay variant="session_unavailable" />;
  }

  if (error) {
    return (
      <div className="space-y-4">
        <ErrorDisplay variant="polling_paused" error={error} />
        <p className="text-center text-sm text-slate-600">
          <Link to="/sessions" className="font-medium text-slate-900 underline">
            Back to sessions
          </Link>
        </p>
      </div>
    );
  }

  if (session.status === "failed") {
    return (
      <ErrorDisplay
        variant="failed_audit"
        message={session.error_message ?? "The audit ended with an error."}
        sessionId={session.session_id}
      />
    );
  }

  if (session.status === "processing") {
    return <ProcessingView session={session} trajectory={trajectory} />;
  }

  if (session.status === "awaiting_review") {
    return <ReportView session={session} showReviewBanner />;
  }

  return <ReportView session={session} />;
}
