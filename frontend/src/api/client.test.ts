import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  createPollTimeoutError,
  handleResponse,
  isRetryableClientError,
  mapBackendError,
  POLL_TIMEOUT_CODE,
  requestFormData,
  requestJson,
  toPollApiError,
} from "@/api/client";

describe("createPollTimeoutError", () => {
  it("uses stable PollTimeout code", () => {
    const e = createPollTimeoutError(60_000);
    expect(e.code).toBe(POLL_TIMEOUT_CODE);
    expect(e.status).toBe(408);
    expect(e.detail).toContain("60s");
  });
});

describe("toPollApiError", () => {
  it("passes ApiError through", () => {
    const inner = new ApiError("x", 400, "Bad", "bad");
    expect(toPollApiError(inner)).toBe(inner);
  });

  it("wraps generic errors", () => {
    const e = toPollApiError(new Error("offline"));
    expect(e.detail).toBe("offline");
    expect(e.status).toBe(0);
  });

  it("wraps unknown values", () => {
    const e = toPollApiError(123);
    expect(e.detail).toBe("Request failed.");
  });
});

describe("isRetryableClientError", () => {
  it("treats status 0 and 5xx as retryable", () => {
    expect(isRetryableClientError(new ApiError("a", 0, "c", "d"))).toBe(true);
    expect(isRetryableClientError(new ApiError("a", 503, "c", "d"))).toBe(true);
    expect(isRetryableClientError(new ApiError("a", 400, "c", "d"))).toBe(false);
  });
});

describe("mapBackendError", () => {
  it("maps JSON error and detail", () => {
    const e = mapBackendError(400, { error: "BadRequest", detail: "Invalid payload" });
    expect(e).toBeInstanceOf(ApiError);
    expect(e.status).toBe(400);
    expect(e.code).toBe("BadRequest");
    expect(e.detail).toBe("Invalid payload");
  });

  it("falls back when detail missing", () => {
    const e = mapBackendError(502, { error: "Err" });
    expect(e.detail).toBe("HTTP 502");
  });

  it("maps string body", () => {
    const e = mapBackendError(500, "plain");
    expect(e.detail).toBe("plain");
  });
});

describe("handleResponse", () => {
  it("parses JSON on happy path", async () => {
    const res = new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
    await expect(handleResponse<{ ok: boolean }>(res)).resolves.toEqual({ ok: true });
  });

  it("throws ApiError on 4xx/5xx", async () => {
    const res = new Response(JSON.stringify({ error: "NotFound", detail: "missing" }), {
      status: 404,
      headers: { "Content-Type": "application/json" },
    });
    await expect(handleResponse(res)).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      detail: "missing",
    });
  });

  it("parses text bodies on success", async () => {
    const res = new Response("hello", {
      status: 200,
      headers: { "Content-Type": "text/plain" },
    });
    await expect(handleResponse<string>(res)).resolves.toBe("hello");
  });

  it("handles invalid JSON body gracefully on error", async () => {
    const res = new Response("{", {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
    await expect(handleResponse(res)).rejects.toBeInstanceOf(ApiError);
  });
});

describe("requestJson", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("returns parsed JSON", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ hello: "world" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(requestJson<{ hello: string }>("/x")).resolves.toEqual({ hello: "world" });
  });

  it("propagates network failure", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(requestJson("/x")).rejects.toThrow("Failed to fetch");
  });

  it("sends JSON body on POST", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await requestJson("/z", { method: "POST", body: { a: 1 } });
    expect(globalThis.fetch).toHaveBeenCalled();
    const init = vi.mocked(globalThis.fetch).mock.calls[0][1] as RequestInit;
    expect(init.body).toBe(JSON.stringify({ a: 1 }));
  });
});

describe("requestFormData", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("posts multipart and parses JSON", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ session_id: "s" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const fd = new FormData();
    await expect(requestFormData<{ session_id: string }>("/upload", fd)).resolves.toEqual({
      session_id: "s",
    });
  });

  it("maps error responses", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: "Bad", detail: "no" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(requestFormData("/upload", new FormData())).rejects.toMatchObject({
      detail: "no",
    });
  });
});
