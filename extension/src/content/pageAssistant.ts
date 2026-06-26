import { mountInlineAssistant } from "./inlineAssistant";
import { createPageSnapshot } from "./pageScanner";
import { detectFormFields } from "./formDetector";

const EXTENSION_ENABLED_STORAGE_KEY = "extensionEnabled";

async function isExtensionEnabled(): Promise<boolean> {
  const result = await chrome.storage.local.get(EXTENSION_ENABLED_STORAGE_KEY) as { [EXTENSION_ENABLED_STORAGE_KEY]?: boolean };
  return result[EXTENSION_ENABLED_STORAGE_KEY] !== false;
}

const colorScheme = window.matchMedia("(prefers-color-scheme: dark)");
const syncActionTheme = () => chrome.runtime.sendMessage({ type: "COLOR_SCHEME_CHANGED", isDark: colorScheme.matches }).catch(() => undefined);

syncActionTheme();
colorScheme.addEventListener("change", syncActionTheme);

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "SCAN_PAGE") {
    void isExtensionEnabled().then((enabled) => sendResponse(enabled ? { snapshot: createPageSnapshot() } : { error: "Resume Tailor is disabled." }));
    return true;
  }
  if (message.type === "GET_FORM_FIELDS") {
    void isExtensionEnabled().then((enabled) => sendResponse({ fields: enabled ? detectFormFields() : [] }));
    return true;
  }
});

mountInlineAssistant();
