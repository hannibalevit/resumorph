/**
 * Timeout + cancellation primitive shared by the API client and the service
 * worker, which talks to the backend directly for `GENERATE_FIELD_ANSWER`.
 *
 * Every timeout sits above the matching backend timeout (`app/config.py`) on
 * purpose: the backend's own error is far more useful than "the request timed
 * out", so these only fire when the backend itself stops answering.
 */

/** Ordinary CRUD/settings calls — the local backend answers these in milliseconds. */
export const DEFAULT_TIMEOUT_MS = 30_000;
/** Health and model listing — backend `OLLAMA_CONNECT_TIMEOUT_SECONDS` is 10s. */
export const PROBE_TIMEOUT_MS = 15_000;
/** Connection test — cloud `test_connection` runs a tiny generation under `OPENAI_TIMEOUT_SECONDS` (60s). */
export const TEST_TIMEOUT_MS = 70_000;
/** Scan / resume / cover letter / field answer — backend `OLLAMA_TIMEOUT_SECONDS` is 300s. */
export const GENERATION_TIMEOUT_MS = 330_000;

export class RequestTimeoutError extends Error {
  constructor(timeoutMs: number) {
    super(`The backend did not respond within ${Math.round(timeoutMs / 1000)}s. It may still be working — check the local server, then try again.`);
    this.name = "RequestTimeoutError";
  }
}

export class RequestCancelledError extends Error {
  constructor() {
    super("Request cancelled.");
    this.name = "RequestCancelledError";
  }
}

export function isRequestCancelled(error: unknown): boolean {
  return error instanceof RequestCancelledError;
}

/**
 * Runs `send` under a combined signal: this timeout plus any caller signal (the
 * sidepanel Cancel button). `fetch` reports both as a bare `AbortError`, so the
 * two causes are re-thrown as distinct errors the UI can tell apart — a user
 * cancel is not an error worth showing, a timeout is.
 */
export async function withAbort<T>(
  timeoutMs: number,
  external: AbortSignal | null | undefined,
  send: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  if (external?.aborted) throw new RequestCancelledError();
  const controller = new AbortController();
  const forwardAbort = () => controller.abort();
  external?.addEventListener("abort", forwardAbort);
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    return await send(controller.signal);
  } catch (error) {
    // The user's intent wins over a timeout that landed in the same tick.
    if (external?.aborted) throw new RequestCancelledError();
    if (timedOut) throw new RequestTimeoutError(timeoutMs);
    throw error;
  } finally {
    clearTimeout(timer);
    external?.removeEventListener("abort", forwardAbort);
  }
}
