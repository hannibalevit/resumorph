const BASE_RESUME_KEY = "baseResume";
const API_BASE_URL_STORAGE_KEY = "apiBaseUrl";
const ONBOARDING_COMPLETE_STORAGE_KEY = "onboardingComplete";
const OPEN_JOB_SESSION_IDS_KEY = "openJobSessionIds";
export const DEFAULT_API_BASE_URL = "http://localhost:8000";
export const EXTENSION_ENABLED_STORAGE_KEY = "extensionEnabled";
export const BACKEND_CONNECTED_STORAGE_KEY = "backendConnected";
export const MAX_OPEN_JOB_TABS = 5;

type ResumeStorageShape = {
  [BASE_RESUME_KEY]?: string;
  [API_BASE_URL_STORAGE_KEY]?: string;
  [ONBOARDING_COMPLETE_STORAGE_KEY]?: boolean;
  [EXTENSION_ENABLED_STORAGE_KEY]?: boolean;
  [OPEN_JOB_SESSION_IDS_KEY]?: string[];
};

export async function getBaseResume(): Promise<string | null> {
  const result = await chrome.storage.local.get(BASE_RESUME_KEY) as ResumeStorageShape;
  return result[BASE_RESUME_KEY] ?? null;
}

export async function saveBaseResume(baseResume: string): Promise<void> {
  await chrome.storage.local.set({ [BASE_RESUME_KEY]: baseResume });
}

export async function clearBaseResume(): Promise<void> {
  await chrome.storage.local.remove(BASE_RESUME_KEY);
}

export function normalizeApiBaseUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, "");
  return trimmed || DEFAULT_API_BASE_URL;
}

export async function getApiBaseUrl(): Promise<string> {
  const result = await chrome.storage.local.get(API_BASE_URL_STORAGE_KEY) as ResumeStorageShape;
  return normalizeApiBaseUrl(result[API_BASE_URL_STORAGE_KEY] ?? DEFAULT_API_BASE_URL);
}

export async function saveApiBaseUrl(apiBaseUrl: string): Promise<string> {
  const normalized = normalizeApiBaseUrl(apiBaseUrl);
  await chrome.storage.local.set({ [API_BASE_URL_STORAGE_KEY]: normalized });
  return normalized;
}

export async function isOnboardingComplete(): Promise<boolean> {
  const result = await chrome.storage.local.get(ONBOARDING_COMPLETE_STORAGE_KEY) as ResumeStorageShape;
  return result[ONBOARDING_COMPLETE_STORAGE_KEY] === true;
}

export async function saveOnboardingComplete(): Promise<void> {
  await chrome.storage.local.set({ [ONBOARDING_COMPLETE_STORAGE_KEY]: true });
}

export async function isExtensionEnabled(): Promise<boolean> {
  const result = await chrome.storage.local.get(EXTENSION_ENABLED_STORAGE_KEY) as ResumeStorageShape;
  return result[EXTENSION_ENABLED_STORAGE_KEY] !== false;
}

export async function saveExtensionEnabled(enabled: boolean): Promise<void> {
  await chrome.storage.local.set({ [EXTENSION_ENABLED_STORAGE_KEY]: enabled });
}

export async function getOpenJobSessionIds(): Promise<string[]> {
  const result = await chrome.storage.local.get(OPEN_JOB_SESSION_IDS_KEY) as ResumeStorageShape;
  return result[OPEN_JOB_SESSION_IDS_KEY] ?? [];
}

export async function setOpenJobSessionIds(ids: string[]): Promise<void> {
  await chrome.storage.local.set({ [OPEN_JOB_SESSION_IDS_KEY]: ids });
}
