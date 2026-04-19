import { useEffect, useRef, useState } from "react";

import {
  ApiError,
  createPollTimeoutError,
  toPollApiError,
} from "@/api/client";
import { getSession, getTrajectory } from "@/api/sessions";
import type { AuditSession, SessionStatus, TrajectoryResponse } from "@/types";

const DEFAULT_POLL_MS = 2000;
const DEFAULT_TIMEOUT_MS = 60_000;

function isTerminal(status: SessionStatus): boolean {
  return status !== "processing";
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Polls `GET /sessions/:id/trajectory` every 2s while `enabled`.
 * Stops on first fetch error (no silent retry).
 */
export function usePollTrajectory(
  sessionId: string | undefined,
  options: { enabled: boolean; pollIntervalMs?: number },
): {
  trajectory: TrajectoryResponse | null;
  error: ApiError | null;
} {
  const [trajectory, setTrajectory] = useState<TrajectoryResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const pollMs = options.pollIntervalMs ?? DEFAULT_POLL_MS;

  useEffect(() => {
    if (!sessionId || !options.enabled) {
      setTrajectory(null);
      setError(null);
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    let cancelled = false;

    const tick = async () => {
      try {
        const t = await getTrajectory(sessionId);
        if (cancelled) return;
        setTrajectory(t);
        setError(null);
      } catch (e) {
        if (cancelled) return;
        setError(toPollApiError(e));
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    };

    void tick();
    intervalRef.current = setInterval(() => void tick(), pollMs);

    return () => {
      cancelled = true;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [sessionId, options.enabled, pollMs]);

  return { trajectory, error };
}

export type UsePollSessionOptions = {
  /** Defaults to 2000. Intended for tests only. */
  pollIntervalMs?: number;
  /** Defaults to 60_000. Intended for tests only. */
  overallTimeoutMs?: number;
  /** Increment to restart load + polling (e.g. after a user refresh). */
  refreshKey?: number;
};

export function usePollSession(
  sessionId: string | undefined,
  options: UsePollSessionOptions = {},
): {
  session: AuditSession | null;
  trajectory: TrajectoryResponse | null;
  error: ApiError | null;
  loading: boolean;
  notFound: boolean;
} {
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_MS;
  const overallTimeoutMs = options.overallTimeoutMs ?? DEFAULT_TIMEOUT_MS;
  const refreshKey = options.refreshKey ?? 0;

  const [session, setSession] = useState<AuditSession | null>(null);
  const [trajectory, setTrajectory] = useState<TrajectoryResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!sessionId) {
      setSession(null);
      setTrajectory(null);
      setError(null);
      setNotFound(false);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    setNotFound(false);

    let cancelled = false;
    const deadline = Date.now() + overallTimeoutMs;

    (async () => {
      try {
        const initial = await getSession(sessionId);
        if (cancelled) return;
        setSession(initial);
        setLoading(false);

        if (isTerminal(initial.status)) {
          try {
            const t = await getTrajectory(sessionId);
            if (!cancelled) setTrajectory(t);
          } catch {
            /* optional */
          }
          return;
        }

        while (!cancelled) {
          if (Date.now() > deadline) {
            if (!cancelled) setError(createPollTimeoutError(overallTimeoutMs));
            return;
          }
          try {
            const t = await getTrajectory(sessionId);
            if (cancelled) return;
            setTrajectory(t);
            if (isTerminal(t.status)) {
              const s2 = await getSession(sessionId);
              if (!cancelled) setSession(s2);
              return;
            }
          } catch (e) {
            if (!cancelled) setError(toPollApiError(e));
            return;
          }
          await delay(pollIntervalMs);
        }
      } catch (e) {
        if (!cancelled) {
          if (e instanceof ApiError && e.status === 404) {
            setNotFound(true);
            setError(null);
          } else {
            setError(toPollApiError(e));
          }
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [sessionId, pollIntervalMs, overallTimeoutMs, refreshKey]);

  return { session, trajectory, error, loading, notFound };
}
