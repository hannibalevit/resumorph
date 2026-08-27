import type { ApiError, JobSession, JobSessionSummary, PageSnapshot } from "./sidepanelTypes";
import { DEFAULT_TIMEOUT_MS, GENERATION_TIMEOUT_MS, PROBE_TIMEOUT_MS, TEST_TIMEOUT_MS, withAbort } from "./requestTimeout";
import { getApiBaseUrl } from "./storage";

/** Passed by callers that expose a Cancel affordance for long generation calls. */
export type CallOptions = { signal?: AbortSignal };

type ApiRequestInit = RequestInit & { timeoutMs?: number };

async function readError(response: Response): Promise<Error> {
  const body = await response.json().catch(() => ({})) as ApiError;
  return new Error(body.error?.message ?? `Backend returned ${response.status}`);
}

async function request<T>(path: string, options?: ApiRequestInit): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal, headers, ...init } = options ?? {};
  const apiBaseUrl = await getApiBaseUrl();
  return withAbort(timeoutMs, signal, async (requestSignal) => {
    const response = await fetch(`${apiBaseUrl}${path}`, { ...init, signal: requestSignal, headers: { "Content-Type": "application/json", ...headers } });
    if (!response.ok) throw await readError(response);
    if (response.status === 204) return undefined as T;
    return await response.json() as T;
  });
}

async function upload<T>(path: string, file: File, options?: ApiRequestInit): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal } = options ?? {};
  const apiBaseUrl = await getApiBaseUrl();
  const data = new FormData();
  data.append("file", file);
  return withAbort(timeoutMs, signal, async (requestSignal) => {
    const response = await fetch(`${apiBaseUrl}${path}`, { method: "POST", body: data, signal: requestSignal });
    if (!response.ok) throw await readError(response);
    return await response.json() as T;
  });
}

export const api = {
  health: () => request<{ status: string }>("/health", { timeoutMs: PROBE_TIMEOUT_MS }),
  sessions: () => request<JobSessionSummary[]>("/api/job-sessions"),
  session: (id: string) => request<JobSession>(`/api/job-sessions/${id}`),
  scan: (pageSnapshot: PageSnapshot, options: CallOptions = {}) => request<JobSession>("/api/job-sessions/scan", { method: "POST", body: JSON.stringify({ pageSnapshot }), timeoutMs: GENERATION_TIMEOUT_MS, signal: options.signal }),
  match: (url: string, title: string) => request<{ matched: boolean; jobSessionId?: string }>("/api/job-sessions/match-current-page", { method: "POST", body: JSON.stringify({ url, title, visibleTextPreview: "" }) }),
  extractResumeText: (file: File) => upload<{ text: string }>("/api/extract-resume-text", file),
  getResume: () => request<{ text: string }>("/api/profile/base-resume"),
  saveResume: (text: string) => request<{ text: string }>("/api/profile/base-resume", { method: "POST", body: JSON.stringify({ text }) }),
  deleteSession: (id: string) => request<void>(`/api/job-sessions/${id}`, { method: "DELETE" }),
  clearSessions: () => request<void>("/api/job-sessions", { method: "DELETE" }),
  generateResume: (id: string, targetFormat: DocumentFormat, options: CallOptions = {}) => request<GeneratedFile>(`/api/job-sessions/${id}/generate-resume`, { method: "POST", body: JSON.stringify({ targetFormat }), timeoutMs: GENERATION_TIMEOUT_MS, signal: options.signal }),
  generateCoverLetter: (id: string, targetFormat: DocumentFormat, options: CallOptions = {}) => request<GeneratedFile>(`/api/job-sessions/${id}/generate-cover-letter`, { method: "POST", body: JSON.stringify({ targetFormat }), timeoutMs: GENERATION_TIMEOUT_MS, signal: options.signal }),
  convertArtifact: (id: string, targetFormat: DocumentFormat, options: CallOptions = {}) => request<GeneratedFile>(`/api/artifacts/${id}/convert`, { method: "POST", body: JSON.stringify({ targetFormat }), timeoutMs: GENERATION_TIMEOUT_MS, signal: options.signal }),
  providers: () => request<ProviderSettings>("/api/settings/llm-providers"),
  saveProvider: (provider: ProviderName, input: SaveProviderInput) =>
    request<ProviderConfig>(`/api/settings/llm-providers/${provider}`, {
      method: "POST",
      body: JSON.stringify({
        apiKey: input.apiKey || undefined,
        baseUrl: input.baseUrl,
        defaultModel: input.defaultModel ?? "",
        availableModels: input.availableModels ?? [],
        testAfterSave: input.testAfterSave ?? false,
      }),
    }),
  saveProviderModel: (provider: ProviderName, defaultModel: string, availableModels: string[]) =>
    request<ProviderConfig>(`/api/settings/llm-providers/${provider}/default-model`, {
      method: "POST",
      body: JSON.stringify({ defaultModel, availableModels }),
    }),
  testProvider: (provider: ProviderName, input: TestProviderInput = {}) =>
    request<ProviderTest>(`/api/settings/llm-providers/${provider}/test`, {
      method: "POST",
      timeoutMs: TEST_TIMEOUT_MS,
      body: JSON.stringify({
        apiKey: input.apiKey || undefined,
        baseUrl: input.baseUrl,
        model: input.model || undefined,
      }),
    }),
  providerModels: (provider: ProviderName, input: ProviderModelsInput = {}) =>
    request<{ provider: ProviderName; models: string[] }>(`/api/settings/llm-providers/${provider}/models`, {
      method: "POST",
      timeoutMs: PROBE_TIMEOUT_MS,
      body: JSON.stringify({
        apiKey: input.apiKey || undefined,
        baseUrl: input.baseUrl,
        refresh: input.refresh ?? false,
      }),
    }),
  deleteProvider: (provider: ProviderName) => request<void>(`/api/settings/llm-providers/${provider}`, { method: "DELETE" }),
  setDefaultProvider: (provider: ProviderName, model: string) => request<ProviderSettings>("/api/settings/default-llm", { method: "POST", body: JSON.stringify({ provider, model }) }),
  setTaskProvider: (task: LlmTaskName, provider: ProviderName, model: string) => request<ProviderSettings>("/api/settings/task-llm", { method: "POST", body: JSON.stringify({ task, provider, model }) }),
  clearTaskProvider: (task: LlmTaskName) => request<ProviderSettings>(`/api/settings/task-llm/${task}`, { method: "DELETE" }),
  adminSessions: (search = "", provider = "", limit = 50, offset = 0) => request<AdminJobList>(`/api/admin/job-sessions?search=${encodeURIComponent(search)}&provider=${encodeURIComponent(provider)}&limit=${limit}&offset=${offset}`),
  adminSession: (id: string) => request<AdminJobDetail>(`/api/admin/job-sessions/${id}`),
  adminArtifacts: (id: string) => request<ArtifactDetail[]>(`/api/admin/job-sessions/${id}/artifacts`),
  artifact: (id: string) => request<ArtifactDetail>(`/api/artifacts/${id}`),
};

export type GeneratedFile = { artifactId: string; fileName: string; mimeType: string; base64: string; notes: { keywordsUsed: string[]; missingRequirements: string[]; warnings: string[] } };
export type DocumentFormat = "docx" | "pdf";
export type ProviderName = "openai" | "gemini" | "claude" | "ollama";
export type LlmTaskName = "scan" | "resume" | "field_answer";
/** baseUrl = saved value only (nullable). effectiveBaseUrl = resolved for display. */
export type ProviderConfig = {
  provider: ProviderName;
  isEnabled: boolean;
  keyMask?: string;
  baseUrl?: string | null;
  effectiveBaseUrl?: string | null;
  defaultModel?: string;
  availableModels: string[];
  modelsUpdatedAt?: string;
  lastTestStatus: string;
  lastTestError?: string;
  lastTestedAt?: string;
};
export type SaveProviderInput = {
  apiKey?: string;
  /** Omit to leave saved URL unchanged; "" clears saved URL so env/default apply. */
  baseUrl?: string | null;
  defaultModel?: string;
  availableModels?: string[];
  testAfterSave?: boolean;
};
export type TestProviderInput = { apiKey?: string; baseUrl?: string | null; model?: string };
export type ProviderModelsInput = { apiKey?: string; baseUrl?: string | null; refresh?: boolean };
export type TaskLlmSetting = { task: LlmTaskName; provider: ProviderName; model: string; isCustom: boolean };
export type ProviderSettings = { providers: ProviderConfig[]; defaultProvider?: ProviderName; defaultModel?: string; taskSettings: Record<LlmTaskName, TaskLlmSetting> };
export type ProviderTest = { provider: ProviderName; model: string; status: "success" | "failed"; latencyMs: number; message: string; rawTextPreview?: string; errorCode?: string; details?: string };
export type AdminJob = { id: string; title: string; companyName?: string; positionTitle?: string; location?: string; sourceUrl: string; hostname: string; status: { scanned: boolean; resumeGenerated: boolean; coverLetterGenerated: boolean; fieldAnswersGenerated: boolean }; llmProviderUsed?: string; llmModelUsed?: string; createdAt: string; updatedAt: string };
export type AdminJobList = { items: AdminJob[]; total: number };
export type AdminJobDetail = JobSession & { relatedLinks: Array<{ id: string; url: string; normalizedUrl: string; linkType: string; title?: string; createdAt: string }> };
export type ArtifactDetail = { id: string; artifactType: string; title: string; fileName?: string; createdAt: string; llmProvider?: string; llmModel?: string; contentJson: Record<string, unknown>; mimeType?: string; base64File?: string };
