/**
 * Single fetch boundary for the FreightCheck UI. Pages and components must not
 * call `fetch` directly — use `requestJson` / `requestFormData` or endpoint modules.
 */

export const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly detail: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Client-side polling wall-clock exceeded (not an HTTP status from the server). */
export const POLL_TIMEOUT_CODE = "PollTimeout";

/** Maps non-`ApiError` failures from the poll loop into a stable `ApiError`. */
export const POLL_CLIENT_ERROR_CODE = "PollClientError";

export function createPollTimeoutError(overallTimeoutMs: number): ApiError {
  const sec = Math.round(overallTimeoutMs / 1000);
  const detail = `This audit is taking longer than expected (${sec}s). Please refresh or try again.`;
  return new ApiError(detail, 408, POLL_TIMEOUT_CODE, detail);
}

export function toPollApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  if (e instanceof Error) {
    return new ApiError(e.message, 0, POLL_CLIENT_ERROR_CODE, e.message);
  }
  return new ApiError("Request failed.", 0, POLL_CLIENT_ERROR_CODE, "Request failed.");
}

export function isRetryableClientError(e: ApiError): boolean {
  return e.status === 0 || e.status >= 500;
}

type BackendErrorBody = {
  error?: string;
  detail?: string;
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

export function mapBackendError(status: number, body: unknown): ApiError {
  const rec = isRecord(body) ? body : {};
  const be = rec as BackendErrorBody;
  const code = typeof be.error === "string" ? be.error : "HttpError";
  const detail =
    typeof be.detail === "string"
      ? be.detail
      : typeof body === "string"
        ? body
        : `HTTP ${status}`;
  return new ApiError(detail, status, code, detail);
}

async function parseBody(res: Response): Promise<unknown> {
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    try {
      return await res.json();
    } catch {
      return null;
    }
  }
  return await res.text();
}

export async function handleResponse<T>(res: Response): Promise<T> {
  const body = await parseBody(res);
  if (!res.ok) {
    throw mapBackendError(res.status, body);
  }
  return body as T;
}

export async function requestJson<T>(
  path: string,
  init?: Omit<RequestInit, "body"> & { body?: unknown },
): Promise<T> {
  const { body, headers, ...rest } = init ?? {};
  const res = await fetch(`${BASE_URL}${path}`, {
    ...rest,
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return handleResponse<T>(res);
}

export async function requestFormData<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    body: formData,
  });
  return handleResponse<T>(res);
}
