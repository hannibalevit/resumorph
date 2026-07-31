import { describe, expect, it } from "vitest";
import { isLocalUrlProvider, PROVIDERS, providerLabel } from "../src/shared/llmProviders";

describe("llmProviders", () => {
  it("lists cloud providers before Ollama", () => {
    expect(PROVIDERS.map((item) => item.id)).toEqual(["openai", "gemini", "claude", "ollama"]);
    expect(PROVIDERS.at(-1)?.kind).toBe("localUrl");
  });

  it("labels unknown providers with the raw id", () => {
    expect(providerLabel("ollama")).toBe("Ollama (local)");
    expect(providerLabel("openai")).toBe("OpenAI");
  });

  it("detects localUrl providers via kind", () => {
    expect(isLocalUrlProvider("ollama")).toBe(true);
    expect(isLocalUrlProvider("claude")).toBe(false);
  });
});
