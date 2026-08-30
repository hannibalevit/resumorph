import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/shared/apiClient";
import { DEFAULT_API_BASE_URL } from "../src/shared/storage";

function jsonResponse(body: unknown = {}, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

async function lastRequestBody(): Promise<Record<string, unknown>> {
  const call = vi.mocked(fetch).mock.calls.at(-1);
  expect(call).toBeTruthy();
  return JSON.parse(String(call?.[1]?.body)) as Record<string, unknown>;
}

async function lastRequestUrl(): Promise<string> {
  const call = vi.mocked(fetch).mock.calls.at(-1);
  expect(call).toBeTruthy();
  return String(call?.[0]);
}

describe("apiClient provider payloads", () => {
  beforeEach(() => {
    vi.stubGlobal("chrome", {
      storage: {
        local: {
          get: vi.fn(async () => ({})),
        },
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          provider: "ollama",
          isEnabled: true,
          availableModels: [],
          lastTestStatus: "success",
        }),
      ),
    );
  });

  it("sends apiKey for cloud save and omits baseUrl when unset", async () => {
    await api.saveProvider("openai", {
      apiKey: "sk-test-key",
      defaultModel: "gpt-test",
      availableModels: ["gpt-test"],
      testAfterSave: true,
    });

    expect(await lastRequestUrl()).toBe(`${DEFAULT_API_BASE_URL}/api/settings/llm-providers/openai`);
    const body = await lastRequestBody();
    expect(body.apiKey).toBe("sk-test-key");
    expect(body.defaultModel).toBe("gpt-test");
    expect(body.testAfterSave).toBe(true);
    expect(Object.hasOwn(body, "baseUrl")).toBe(false);
  });

  it("sends baseUrl \"\" to clear a saved Ollama URL, without an apiKey", async () => {
    await api.saveProvider("ollama", {
      baseUrl: "",
      defaultModel: "llama3.2",
      availableModels: ["llama3.2"],
    });

    const body = await lastRequestBody();
    expect(body.baseUrl).toBe("");
    expect(Object.hasOwn(body, "apiKey")).toBe(false);
  });

  it("omits baseUrl when undefined so a saved Ollama URL is left untouched", async () => {
    await api.saveProvider("ollama", {
      defaultModel: "llama3.2",
      availableModels: ["llama3.2"],
    });

    const body = await lastRequestBody();
    expect(Object.hasOwn(body, "baseUrl")).toBe(false);
    expect(Object.hasOwn(body, "apiKey")).toBe(false);
  });

  it("passes typed baseUrl on Ollama test/models and refresh on model list", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({
        provider: "ollama",
        model: "llama3.2",
        status: "success",
        latencyMs: 12,
        message: "ok",
        rawTextPreview: "reachable",
      }),
    );
    await api.testProvider("ollama", {
      baseUrl: "http://192.168.0.50:11434",
      model: "llama3.2",
    });
    expect(await lastRequestUrl()).toBe(`${DEFAULT_API_BASE_URL}/api/settings/llm-providers/ollama/test`);
    expect(await lastRequestBody()).toEqual({
      baseUrl: "http://192.168.0.50:11434",
      model: "llama3.2",
    });

    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ provider: "ollama", models: ["llama3.2"] }),
    );
    await api.providerModels("ollama", {
      baseUrl: "http://192.168.0.50:11434",
      refresh: true,
    });
    expect(await lastRequestUrl()).toBe(`${DEFAULT_API_BASE_URL}/api/settings/llm-providers/ollama/models`);
    expect(await lastRequestBody()).toEqual({
      baseUrl: "http://192.168.0.50:11434",
      refresh: true,
    });
  });

  it("sends apiKey for cloud model listing and omits empty keys", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ provider: "claude", models: ["claude-test"] }),
    );
    await api.providerModels("claude", { apiKey: "sk-ant-test", refresh: false });
    expect(await lastRequestBody()).toEqual({
      apiKey: "sk-ant-test",
      refresh: false,
    });

    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ provider: "claude", models: ["claude-test"] }),
    );
    await api.providerModels("claude", { apiKey: "" });
    const body = await lastRequestBody();
    expect(Object.hasOwn(body, "apiKey")).toBe(false);
    expect(body.refresh).toBe(false);
  });
});

describe("apiClient document generation payloads", () => {
  beforeEach(() => {
    vi.stubGlobal("chrome", {
      storage: {
        local: {
          get: vi.fn(async () => ({})),
        },
      },
    });
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse()));
  });

  it("sends the selected output format for generated documents", async () => {
    await api.generateResume("job-1", "pdf");
    expect(await lastRequestUrl()).toBe(`${DEFAULT_API_BASE_URL}/api/job-sessions/job-1/generate-resume`);
    expect(await lastRequestBody()).toEqual({ targetFormat: "pdf" });

    await api.generateCoverLetter("job-1", "docx");
    expect(await lastRequestUrl()).toBe(`${DEFAULT_API_BASE_URL}/api/job-sessions/job-1/generate-cover-letter`);
    expect(await lastRequestBody()).toEqual({ targetFormat: "docx" });
  });

  it("converts a saved artifact to the selected output format", async () => {
    await api.convertArtifact("artifact-1", "pdf");
    expect(await lastRequestUrl()).toBe(`${DEFAULT_API_BASE_URL}/api/artifacts/artifact-1/convert`);
    expect(await lastRequestBody()).toEqual({ targetFormat: "pdf" });
  });
});
