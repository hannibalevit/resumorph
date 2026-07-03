import { describe, expect, it } from "vitest";
import { DEFAULT_API_BASE_URL, normalizeApiBaseUrl } from "../src/shared/storage";

describe("storage helpers", () => {
  it("normalizes API base URLs before saving or using them", () => {
    expect(normalizeApiBaseUrl("  http://localhost:8000/// ")).toBe("http://localhost:8000");
    expect(normalizeApiBaseUrl("https://api.example.com/v1/")).toBe("https://api.example.com/v1");
  });

  it("falls back to the local backend URL for blank input", () => {
    expect(normalizeApiBaseUrl("   ")).toBe(DEFAULT_API_BASE_URL);
  });
});
