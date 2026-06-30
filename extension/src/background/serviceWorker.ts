import { EXTENSION_ENABLED_STORAGE_KEY, getApiBaseUrl, isExtensionEnabled } from "../shared/storage";
import { isBlockedUrl } from "../shared/blockedSites";

// chrome.action.setIcon fetches each path itself; relative paths resolve
// inconsistently from a module-type service worker and intermittently fail with
// "Failed to fetch". Resolving to an absolute chrome-extension:// URL avoids that.
const ACTION_ICON_PATHS = {
  light: {
    16: chrome.runtime.getURL("icons/action-black-16.png"),
    32: chrome.runtime.getURL("icons/action-black-32.png"),
    48: chrome.runtime.getURL("icons/action-black-48.png"),
    128: chrome.runtime.getURL("icons/action-black-128.png"),
  },
  dark: {
    16: chrome.runtime.getURL("icons/action-white-16.png"),
    32: chrome.runtime.getURL("icons/action-white-32.png"),
    48: chrome.runtime.getURL("icons/action-white-48.png"),
    128: chrome.runtime.getURL("icons/action-white-128.png"),
  },
};

async function setActionTheme(isDark: boolean): Promise<void> {
  await chrome.action.setIcon({ path: isDark ? ACTION_ICON_PATHS.dark : ACTION_ICON_PATHS.light });
  await chrome.storage.local.set({ actionIconIsDark: isDark });
}

async function restoreActionTheme(): Promise<void> {
  const value = await chrome.storage.local.get("actionIconIsDark");
  await setActionTheme(Boolean(value.actionIconIsDark));
}

async function updateEnabledBadge(enabled?: boolean): Promise<void> {
  const isEnabled = enabled ?? await isExtensionEnabled();
  await chrome.action.setBadgeText({ text: isEnabled ? "" : "OFF" });
  await chrome.action.setBadgeBackgroundColor({ color: "#667085" });
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
  void updateEnabledBadge();
});
chrome.runtime.onStartup.addListener(() => {
  void restoreActionTheme();
  void updateEnabledBadge();
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") return;
  const change = changes[EXTENSION_ENABLED_STORAGE_KEY];
  if (change) void updateEnabledBadge(change.newValue !== false);
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
