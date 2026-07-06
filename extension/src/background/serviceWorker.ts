import { BACKEND_CONNECTED_STORAGE_KEY, EXTENSION_ENABLED_STORAGE_KEY, getApiBaseUrl, isExtensionEnabled } from "../shared/storage";
import { isBlockedUrl } from "../shared/blockedSites";

const HEALTH_CHECK_ALARM = "healthCheck";
type IconVariant = "black" | "white" | "gray" | "red";

// chrome.action.setIcon fetches each path itself; relative paths resolve
// inconsistently from a module-type service worker and intermittently fail with
// "Failed to fetch". Resolving to an absolute chrome-extension:// URL avoids that.
function iconPaths(variant: IconVariant): Record<16 | 32 | 48 | 128, string> {
  return {
    16: chrome.runtime.getURL(`icons/action-${variant}-16.png`),
    32: chrome.runtime.getURL(`icons/action-${variant}-32.png`),
    48: chrome.runtime.getURL(`icons/action-${variant}-48.png`),
    128: chrome.runtime.getURL(`icons/action-${variant}-128.png`),
  };
}

// Precedence: an explicitly disabled extension always shows gray, an unreachable
// backend shows red, otherwise the icon follows the sidepanel's light/dark theme.
async function applyIconState(): Promise<void> {
  const stored = await chrome.storage.local.get(["actionIconIsDark", BACKEND_CONNECTED_STORAGE_KEY]);
  const enabled = await isExtensionEnabled();
  const variant: IconVariant = !enabled
    ? "gray"
    : stored[BACKEND_CONNECTED_STORAGE_KEY] === false
      ? "red"
      : stored.actionIconIsDark
        ? "white"
        : "black";
  await chrome.action.setIcon({ path: iconPaths(variant) });
}

async function setActionTheme(isDark: boolean): Promise<void> {
  await chrome.storage.local.set({ actionIconIsDark: isDark });
  await applyIconState();
}

async function checkBackendHealth(): Promise<void> {
  let connected = false;
  try {
    const apiBaseUrl = await getApiBaseUrl();
    const response = await fetch(`${apiBaseUrl}/health`);
    connected = response.ok;
  } catch {
    connected = false;
  }
  await chrome.storage.local.set({ [BACKEND_CONNECTED_STORAGE_KEY]: connected });
  await applyIconState();
}

async function updateActionTitle(enabled?: boolean): Promise<void> {
  const isEnabled = enabled ?? await isExtensionEnabled();
  await chrome.action.setBadgeText({ text: "" });
  await chrome.action.setTitle({ title: isEnabled ? "Resume Tailor" : "Resume Tailor is off" });
}

async function notifyActiveTab(tabId?: number): Promise<void> {
  if (!tabId) return;
  const tab = await chrome.tabs.get(tabId);
  chrome.runtime.sendMessage({ type: "ACTIVE_TAB_CHANGED", tab: { id: tab.id, url: tab.url, title: tab.title } }).catch(() => undefined);
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => undefined);
  void setActionTheme(false);
});

// MV3 terminates and respawns this service worker constantly (idle timeout, a manual
// "Reload" of the unpacked extension, etc.), and neither onInstalled nor onStartup
// reliably fires for most of those respawns. This top-level code runs every time the
// worker's module is evaluated — i.e. on every respawn for any reason — so the badge,
// icon, and connectivity state never sit stale waiting for a lifecycle event that may
// never come.
chrome.alarms.create(HEALTH_CHECK_ALARM, { periodInMinutes: 1 });
void checkBackendHealth();
void applyIconState();
void updateActionTitle();

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === HEALTH_CHECK_ALARM) void checkBackendHealth();
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") return;
  const change = changes[EXTENSION_ENABLED_STORAGE_KEY];
  if (change) {
    void updateActionTitle(change.newValue !== false);
    void applyIconState();
  }
});

chrome.tabs.onActivated.addListener(({ tabId }) => void notifyActiveTab(tabId));
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "complete" || changeInfo.url) void notifyActiveTab(tabId);
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "COLOR_SCHEME_CHANGED") {
    void setActionTheme(Boolean(message.isDark)).then(() => sendResponse({ ok: true }));
    return true;
  }
  if (message.type === "BACKEND_STATUS_CHANGED") {
    void chrome.storage.local.set({ [BACKEND_CONNECTED_STORAGE_KEY]: Boolean(message.connected) })
      .then(() => applyIconState())
      .then(() => sendResponse({ ok: true }));
    return true;
  }
  if (message.type === "SET_ACTIVE_JOB_SESSION") {
    void chrome.storage.local.set({ activeJobSessionId: message.jobSessionId }).then(() => sendResponse({ ok: true }));
    return true;
  }
  if (message.type === "GET_ACTIVE_JOB_SESSION") {
    void chrome.storage.local.get("activeJobSessionId").then((value) => sendResponse({ jobSessionId: value.activeJobSessionId }));
    return true;
  }
  if (message.type === "GENERATE_FIELD_ANSWER") {
    void (async () => {
      try {
        if (isBlockedUrl(sender.tab?.url)) throw new Error("This site isn't related to job search, so Resume Tailor is disabled here.");
        if (!await isExtensionEnabled()) throw new Error("Resume Tailor is disabled.");
        const apiBaseUrl = await getApiBaseUrl();
        const response = await fetch(`${apiBaseUrl}/api/job-sessions/${message.jobSessionId}/generate-field-answer`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ field: message.field, tone: "professional", maxLength: 1200 }),
        });
        const payload = await response.json().catch(() => ({})) as { answer?: string; warnings?: string[]; error?: { message?: string } };
        if (!response.ok) throw new Error(payload.error?.message ?? `Backend returned ${response.status}`);
        sendResponse({ answer: payload.answer ?? "", warnings: payload.warnings ?? [] });
      } catch (error) {
        sendResponse({ error: error instanceof Error ? error.message : "Could not reach the Resume Tailor backend." });
      }
    })();
    return true;
  }
  return false;
});
