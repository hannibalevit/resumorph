import { describe, expect, it, vi } from "vitest";
import { DEFAULT_API_BASE_URL, getDefaultCoverLetterFormat, getDefaultResumeFormat, normalizeApiBaseUrl, saveDefaultCoverLetterFormat, saveDefaultResumeFormat } from "../src/shared/storage";

describe("storage helpers", () => {
  it("normalizes API base URLs before saving or using them", () => {
    expect(normalizeApiBaseUrl("  http://localhost:8000/// ")).toBe("http://localhost:8000");
    expect(normalizeApiBaseUrl("https://api.example.com/v1/")).toBe("https://api.example.com/v1");
  });

  it("falls back to the local backend URL for blank input", () => {
    expect(normalizeApiBaseUrl("   ")).toBe(DEFAULT_API_BASE_URL);
  });

  it("defaults document formats to DOCX and persists explicit choices", async () => {
    const get = vi.fn(async () => ({}));
    const set = vi.fn(async () => undefined);
    vi.stubGlobal("chrome", { storage: { local: { get, set } } });

    expect(await getDefaultResumeFormat()).toBe("docx");
    expect(await getDefaultCoverLetterFormat()).toBe("docx");
    await saveDefaultResumeFormat("pdf");
    await saveDefaultCoverLetterFormat("pdf");
    expect(set).toHaveBeenNthCalledWith(1, { defaultResumeFormat: "pdf" });
    expect(set).toHaveBeenNthCalledWith(2, { defaultCoverLetterFormat: "pdf" });
  });
});
