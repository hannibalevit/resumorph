import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/shared/apiClient";
import {
  GENERATION_TIMEOUT_MS,
  PROBE_TIMEOUT_MS,
  RequestCancelledError,
  RequestTimeoutError,
  isRequestCancelled,
  withAbort,
} from "../src/shared/requestTimeout";
import type { PageSnapshot } from "../src/shared/sidepanelTypes";

/** Never settles on its own — only the caller's abort ends it, like a hung backend. */
function hangingFetch() {
  return vi.fn((_url: string, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("The operation was aborted.", "AbortError")));
  }));
}

const SNAPSHOT = { url: "https://example.test/job", title: "Role" } as unknown as PageSnapshot;

describe("withAbort", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("throws RequestTimeoutError once the window elapses", async () => {
    const promise = withAbort(1_000, null, (signal) => new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    }));
    // Attach the assertion before advancing: the timer rejects while we await.
    const rejects = expect(promise).rejects.toBeInstanceOf(RequestTimeoutError);
    await vi.advanceTimersByTimeAsync(1_000);
    await rejects;
  });

  it("throws RequestCancelledError when the caller's signal aborts", async () => {
    const controller = new AbortController();
    const promise = withAbort(60_000, controller.signal, (signal) => new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    }));
    controller.abort();
    await expect(promise).rejects.toBeInstanceOf(RequestCancelledError);
  });

  it("rejects an already-aborted signal without running the request", async () => {
    const controller = new AbortController();
    controller.abort();
    const send = vi.fn(async () => "unreachable");
    await expect(withAbort(60_000, controller.signal, send)).rejects.toBeInstanceOf(RequestCancelledError);
    expect(send).not.toHaveBeenCalled();
  });

  it("clears the timer so a resolved call cannot time out later", async () => {
    await expect(withAbort(1_000, null, async () => "done")).resolves.toBe("done");
    await vi.advanceTimersByTimeAsync(5_000);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("only treats RequestCancelledError as a cancellation", () => {
    expect(isRequestCancelled(new RequestCancelledError())).toBe(true);
    expect(isRequestCancelled(new RequestTimeoutError(1_000))).toBe(false);
    expect(isRequestCancelled(new Error("Backend returned 500"))).toBe(false);
  });
});

describe("apiClient timeouts", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("chrome", { storage: { local: { get: vi.fn(async () => ({})) } } });
    vi.stubGlobal("fetch", hangingFetch());
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("gives probes a short window so a hung backend does not spin forever", async () => {
    const promise = api.providerModels("ollama", { baseUrl: "http://192.168.0.50:11434" });
    const rejects = expect(promise).rejects.toBeInstanceOf(RequestTimeoutError);
    await vi.advanceTimersByTimeAsync(PROBE_TIMEOUT_MS);
    await rejects;
  });

  it("keeps generation running well past the probe window", async () => {
    const settled = vi.fn();
    const promise = api.scan(SNAPSHOT).catch(settled);
    await vi.advanceTimersByTimeAsync(PROBE_TIMEOUT_MS * 2);
    expect(settled).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(GENERATION_TIMEOUT_MS);
    await promise;
    expect(settled).toHaveBeenCalledWith(expect.any(RequestTimeoutError));
  });

  it("aborts the underlying fetch when a generation is cancelled", async () => {
    const controller = new AbortController();
    const promise = api.generateResume("job-1", "pdf", { signal: controller.signal });
    await vi.advanceTimersByTimeAsync(0);

    const init = vi.mocked(fetch).mock.calls.at(-1)?.[1];
    expect(init?.signal?.aborted).toBe(false);
    controller.abort();
    expect(init?.signal?.aborted).toBe(true);
    await expect(promise).rejects.toBeInstanceOf(RequestCancelledError);
  });
});
