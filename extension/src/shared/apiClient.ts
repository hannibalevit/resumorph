import type { ApiError, DetectedFormField, JobSession, JobSessionSummary, PageSnapshot } from "./sidepanelTypes";
import { DEFAULT_API_BASE_URL, getApiBaseUrl } from "./storage";

export const API_BASE_URL = DEFAULT_API_BASE_URL;

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const apiBaseUrl = await getApiBaseUrl();
  const response = await fetch(`${apiBaseUrl}${path}`, { ...options, headers: { "Content-Type": "application/json", ...options?.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as ApiError;
    throw new Error(body.error?.message ?? `Backend returned ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

async function upload<T>(path: string, file: File): Promise<T> {
  const apiBaseUrl = await getApiBaseUrl();
  const data = new FormData();
  data.append("file", file);
  const response = await fetch(`${apiBaseUrl}${path}`, { method: "POST", body: data });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as ApiError;
    throw new Error(body.error?.message ?? `Backend returned ${response.status}`);
  }
  return await response.json() as T;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  sessions: () => request<JobSessionSummary[]>("/api/job-sessions"),
  session: (id: string) => request<JobSession>(`/api/job-sessions/${id}`),
  scan: (pageSnapshot: PageSnapshot) => request<JobSession>("/api/job-sessions/scan", { method: "POST", body: JSON.stringify({ pageSnapshot }) }),
  match: (url: string, title: string) => request<{ matched: boolean; jobSessionId?: string }>("/api/job-sessions/match-current-page", { method: "POST", body: JSON.stringify({ url, title, visibleTextPreview: "" }) }),
  extractResumeText: (file: File) => upload<{ text: string }>("/api/extract-resume-text", file),
  getResume: () => request<{ text: string }>("/api/profile/base-resume"),
  saveResume: (text: string) => request<{ text: string }>("/api/profile/base-resume", { method: "POST", body: JSON.stringify({ text }) }),
  deleteSession: (id: string) => request<void>(`/api/job-sessions/${id}`, { method: "DELETE" }),
  clearSessions: () => request<void>("/api/job-sessions", { method: "DELETE" }),
  generateResume: (id: string) => request<GeneratedFile>(`/api/job-sessions/${id}/generate-resume`, { method: "POST" }),
  generateCoverLetter: (id: string) => request<GeneratedFile>(`/api/job-sessions/${id}/generate-cover-letter`, { method: "POST" }),
  fieldAnswer: (id: string, field: DetectedFormField) => request<FieldAnswer>(`/api/job-sessions/${id}/generate-field-answer`, { method: "POST", body: JSON.stringify({ field, tone: "professional", maxLength: 1200 }) }),
  providers: () => request<ProviderSettings>("/api/settings/llm-providers"),
  saveProvider: (provider: ProviderName, apiKey: string, defaultModel: string, availableModels: string[], testAfterSave = false) => request<ProviderConfig>(`/api/settings/llm-providers/${provider}`, { method: "POST", body: JSON.stringify({ apiKey, defaultModel, availableModels, testAfterSave }) }),
  saveProviderModel: (provider: ProviderName, defaultModel: string, availableModels: string[]) => request<ProviderConfig>(`/api/settings/llm-providers/${provider}/default-model`, { method: "POST", body: JSON.stringify({ defaultModel, availableModels }) }),
  testProvider: (provider: ProviderName, apiKey?: string, model?: string) => request<ProviderTest>(`/api/settings/llm-providers/${provider}/test`, { method: "POST", body: JSON.stringify({ apiKey: apiKey || undefined, model: model || undefined }) }),
  providerModels: (provider: ProviderName, apiKey?: string, refresh = false) => request<{ provider: ProviderName; models: string[] }>(`/api/settings/llm-providers/${provider}/models`, { method: "POST", body: JSON.stringify({ apiKey: apiKey || undefined, refresh }) }),
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
export type FieldAnswer = { answer: string; confidence: number; needsUserReview: boolean; warnings: string[] };
export type ProviderName = "openai" | "gemini" | "claude";
export type LlmTaskName = "scan" | "resume" | "field_answer";
export type ProviderConfig = { provider: ProviderName; isEnabled: boolean; keyMask?: string; defaultModel?: string; availableModels: string[]; modelsUpdatedAt?: string; lastTestStatus: string; lastTestError?: string; lastTestedAt?: string };
export type TaskLlmSetting = { task: LlmTaskName; provider: ProviderName; model: string; isCustom: boolean };
export type ProviderSettings = { providers: ProviderConfig[]; defaultProvider?: ProviderName; defaultModel?: string; taskSettings: Record<LlmTaskName, TaskLlmSetting> };
export type ProviderTest = { provider: ProviderName; model: string; status: "success" | "failed"; latencyMs: number; message: string; rawTextPreview?: string; errorCode?: string; details?: string };
export type AdminJob = { id: string; title: string; companyName?: string; positionTitle?: string; location?: string; sourceUrl: string; hostname: string; status: { scanned: boolean; resumeGenerated: boolean; coverLetterGenerated: boolean; fieldAnswersGenerated: boolean }; llmProviderUsed?: string; llmModelUsed?: string; createdAt: string; updatedAt: string };
export type AdminJobList = { items: AdminJob[]; total: number };
export type AdminJobDetail = JobSession & { relatedLinks: Array<{ id: string; url: string; normalizedUrl: string; linkType: string; title?: string; createdAt: string }> };
export type ArtifactDetail = { id: string; artifactType: string; title: string; fileName?: string; createdAt: string; llmProvider?: string; llmModel?: string; contentJson: Record<string, unknown>; mimeType?: string; base64File?: string };
