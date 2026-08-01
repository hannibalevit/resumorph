import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { KEEPALIVE_INTERVAL_MS, MAX_ACTIVITY_MS, keepAliveHolders, withKeepAlive } from "../src/background/keepAlive";

describe("withKeepAlive", () => {
  let getPlatformInfo: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    getPlatformInfo = vi.fn(async () => ({ os: "linux" }));
    vi.stubGlobal("chrome", { runtime: { getPlatformInfo } });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("beats an extension API while the work runs, then stops", async () => {
    let finish: () => void = () => undefined;
    const promise = withKeepAlive(() => new Promise<void>((resolve) => { finish = resolve; }));

    await vi.advanceTimersByTimeAsync(KEEPALIVE_INTERVAL_MS * 3);
    expect(getPlatformInfo).toHaveBeenCalledTimes(3);

    finish();
    await promise;

    expect(keepAliveHolders()).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(KEEPALIVE_INTERVAL_MS * 3);
    expect(getPlatformInfo).toHaveBeenCalledTimes(3);
  });

  it("shares one heartbeat across concurrent work until the last one finishes", async () => {
    let finishFirst: () => void = () => undefined;
    let finishSecond: () => void = () => undefined;
    const first = withKeepAlive(() => new Promise<void>((resolve) => { finishFirst = resolve; }));
    const second = withKeepAlive(() => new Promise<void>((resolve) => { finishSecond = resolve; }));
    expect(keepAliveHolders()).toBe(2);

    await vi.advanceTimersByTimeAsync(KEEPALIVE_INTERVAL_MS);
    expect(getPlatformInfo).toHaveBeenCalledTimes(1);

    finishFirst();
    await first;
    expect(keepAliveHolders()).toBe(1);

    // Still beating: one field answer finishing must not suspend the worker
    // while another is mid-generation.
    await vi.advanceTimersByTimeAsync(KEEPALIVE_INTERVAL_MS);
    expect(getPlatformInfo).toHaveBeenCalledTimes(2);

    finishSecond();
    await second;
    expect(vi.getTimerCount()).toBe(0);
  });

  it("stops the heartbeat when the work throws", async () => {
    await expect(withKeepAlive(async () => { throw new Error("boom"); })).rejects.toThrow("boom");
    expect(keepAliveHolders()).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("beats well inside the 30s idle timeout and caps under the 5-minute activity limit", () => {
    expect(KEEPALIVE_INTERVAL_MS).toBeLessThan(30_000);
    expect(MAX_ACTIVITY_MS).toBeLessThan(5 * 60_000);
  });
});
