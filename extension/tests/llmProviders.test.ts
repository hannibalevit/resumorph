import { describe, expect, it } from "vitest";
import type { ProviderName } from "../src/shared/apiClient";
import { isLocalUrlProvider, PROVIDERS, providerLabel } from "../src/shared/llmProviders";

describe("llmProviders", () => {
  it("lists cloud providers before Ollama", () => {
    expect(PROVIDERS.map((item) => item.id)).toEqual(["openai", "gemini", "claude", "ollama"]);
    expect(PROVIDERS.at(-1)?.kind).toBe("localUrl");
    expect(PROVIDERS.filter((item) => item.kind === "apiKey").map((item) => item.id)).toEqual([
      "openai",
      "gemini",
      "claude",
    ]);
  });

  it("labels known providers and falls back to the raw id for unknown ones", () => {
    expect(providerLabel("ollama")).toBe("Ollama (local)");
    expect(providerLabel("openai")).toBe("OpenAI");
    // Backend can return a provider before the UI catalog knows about it.
    expect(providerLabel("mystery" as ProviderName)).toBe("mystery");
  });

  it("detects localUrl providers via kind", () => {
    expect(isLocalUrlProvider("ollama")).toBe(true);
    expect(isLocalUrlProvider("claude")).toBe(false);
    expect(isLocalUrlProvider("mystery" as ProviderName)).toBe(false);
  });
});
