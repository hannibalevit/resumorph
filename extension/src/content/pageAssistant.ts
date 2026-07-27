import { mountInlineAssistant } from "./inlineAssistant";
import { createPageSnapshot } from "./pageScanner";
import { detectFormFields } from "./formDetector";
import { isBlockedUrl } from "./blockedSites";

const EXTENSION_ENABLED_STORAGE_KEY = "extensionEnabled";
const siteBlocked = isBlockedUrl(window.location.href);

async function isExtensionEnabled(): Promise<boolean> {
  if (siteBlocked) return false;
  const result = await chrome.storage.local.get(EXTENSION_ENABLED_STORAGE_KEY) as { [EXTENSION_ENABLED_STORAGE_KEY]?: boolean };
  return result[EXTENSION_ENABLED_STORAGE_KEY] !== false;
}

// Job boards (e.g. Greenhouse) often render the actual application form inside a
// cross-origin iframe, so this script runs in every frame (see manifest.json's
// all_frames). Page-level concerns (scanning, action icon theme) must only run
// once per tab, so they stay gated to the top frame; the inline "AI" button is a
// per-field concern and needs to mount in whichever frame the field actually lives in.
if (window.top === window) {
  const colorScheme = window.matchMedia("(prefers-color-scheme: dark)");
  const syncActionTheme = () => chrome.runtime.sendMessage({ type: "COLOR_SCHEME_CHANGED", isDark: colorScheme.matches }).catch(() => undefined);

  syncActionTheme();
  colorScheme.addEventListener("change", syncActionTheme);

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message.type === "SCAN_PAGE") {
      if (siteBlocked) { sendResponse({ error: "This site isn't related to job search, so scanning is disabled here." }); return true; }
      void isExtensionEnabled().then((enabled) => sendResponse(enabled ? { snapshot: createPageSnapshot() } : { error: "ResuMorph is disabled." }));
      return true;
    }
    if (message.type === "GET_FORM_FIELDS") {
      void isExtensionEnabled().then((enabled) => sendResponse({ fields: enabled ? detectFormFields() : [] }));
      return true;
    }
  });
}

if (!siteBlocked) mountInlineAssistant();
