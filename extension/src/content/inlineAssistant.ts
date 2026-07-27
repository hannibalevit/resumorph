import { detectFormFields, findField } from "./formDetector";
import type { DetectedFormField } from "../shared/sidepanelTypes";
import { isBlockedUrl } from "./blockedSites";

const BUTTON_CLASS = "resumorph-ai-button";
const BUTTON_ICON = chrome.runtime.getURL("icons/icon-32.png");
const BUTTON_INSET = 5;
const BUTTON_MAX_SIZE = 26;
const EXTENSION_ENABLED_STORAGE_KEY = "extensionEnabled";
const INVALIDATED_CONTEXT = /extension context invalidated|context invalidated/i;

async function isExtensionEnabled(): Promise<boolean> {
  if (isBlockedUrl(window.location.href)) return false;
  const result = await chrome.storage.local.get(EXTENSION_ENABLED_STORAGE_KEY) as { [EXTENSION_ENABLED_STORAGE_KEY]?: boolean };
  return result[EXTENSION_ENABLED_STORAGE_KEY] !== false;
}

async function generateFieldAnswer(jobSessionId: string, field: DetectedFormField): Promise<{ answer: string; warnings: string[] }> {
  const payload = await chrome.runtime.sendMessage({ type: "GENERATE_FIELD_ANSWER", jobSessionId, field }) as { answer?: string; warnings?: string[]; error?: string };
  if (payload.error) throw new Error(payload.error);
  return { answer: payload.answer ?? "", warnings: payload.warnings ?? [] };
}

function isInvalidatedContextError(error: unknown): boolean {
  return error instanceof Error && INVALIDATED_CONTEXT.test(error.message);
}

function removeAllInlineButtons(): void {
  document.querySelectorAll<HTMLButtonElement>(`.${BUTTON_CLASS}`).forEach((element) => element.remove());
}

// Some job-board embeds (e.g. Greenhouse's Remix-based application form) hydrate their whole
// `document` client-side rather than a single mount div. If we insert anything before that
// finishes, React sees DOM it didn't render, treats it as a hydration mismatch, and discards +
// rebuilds the affected subtree - wiping out anything we just added. Wait for mutations to go
// quiet before touching the DOM the first time, so we land after hydration instead of during it.
function whenDomSettled(callback: () => void, quietMs = 400, maxWaitMs = 4000): void {
  const deadline = Date.now() + maxWaitMs;
  let timer: number;
  const finish = () => { observer.disconnect(); clearTimeout(timer); callback(); };
  const observer = new MutationObserver(() => {
    if (Date.now() >= deadline) { finish(); return; }
    clearTimeout(timer);
    timer = window.setTimeout(finish, quietMs);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  timer = window.setTimeout(finish, quietMs);
}

function styles(): void {
  if (document.getElementById("resumorph-ai-styles")) return;
  const style = document.createElement("style");
  style.id = "resumorph-ai-styles";
  style.textContent = `.${BUTTON_CLASS}{position:fixed;z-index:2147483646;display:grid;place-items:center;margin:0;padding:0;border:0;border-radius:0;background:transparent;box-shadow:none;cursor:pointer;overflow:hidden;box-sizing:border-box}.${BUTTON_CLASS}[hidden]{display:none!important}.${BUTTON_CLASS}:focus-visible{outline:2px solid #0a66c2;outline-offset:2px}.${BUTTON_CLASS}:disabled{cursor:wait;opacity:.7}.${BUTTON_CLASS} img{display:block;width:100%;height:100%;object-fit:contain;pointer-events:none}`;
  document.documentElement.append(style);
}

function positionButton(element: HTMLElement, button: HTMLButtonElement): void {
  const rect = element.getBoundingClientRect();
  const maximum = Math.min(BUTTON_MAX_SIZE, rect.width - BUTTON_INSET * 2, rect.height - BUTTON_INSET * 2);
  if (maximum < 14 || rect.bottom <= 0 || rect.right <= 0 || rect.top >= innerHeight || rect.left >= innerWidth) {
    button.hidden = true;
    return;
  }
  const size = Math.floor(maximum);
  button.hidden = false;
  button.style.width = `${size}px`;
  button.style.height = `${size}px`;
  button.style.left = `${Math.max(rect.left + BUTTON_INSET, rect.right - BUTTON_INSET - size)}px`;
  button.style.top = `${Math.max(rect.top + BUTTON_INSET, rect.bottom - BUTTON_INSET - size)}px`;
}

function insertValue(element: HTMLElement, value: string): void {
  if (element.isContentEditable) element.textContent = value;
  else if (element instanceof HTMLTextAreaElement) {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
    setter?.call(element, value);
  } else if (element instanceof HTMLInputElement) {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(element, value);
  } else if (element instanceof HTMLSelectElement) {
    const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")?.set;
    setter?.call(element, value);
  }
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

async function ask(field: DetectedFormField, button: HTMLButtonElement): Promise<void> {
  button.disabled = true;
  button.setAttribute("aria-label", "Generating answer");
  try {
    const active = await chrome.runtime.sendMessage({ type: "GET_ACTIVE_JOB_SESSION" }) as { jobSessionId?: string };
    if (!active.jobSessionId) throw new Error("Open ResuMorph and scan or select a job first.");
    const response = await generateFieldAnswer(active.jobSessionId, field);
    if (!response.answer) throw new Error(response.warnings[0] ?? "No safe answer was generated.");
    const element = findField(field.fieldId);
    if (!element) throw new Error("The form field is no longer available. Refresh the page and try again.");
    insertValue(element, response.answer);
  } catch (error) {
    if (isInvalidatedContextError(error)) {
      removeAllInlineButtons();
      alert("ResuMorph was reloaded. Refresh this browser tab, then try generating the answer again.");
    } else {
      alert(error instanceof Error ? error.message : "Could not generate an answer.");
    }
  } finally {
    if (!button.isConnected) return;
    button.disabled = false;
    button.setAttribute("aria-label", "Generate answer with ResuMorph");
  }
}

export function mountInlineAssistant(): void {
  whenDomSettled(() => mountInlineAssistantAfterSettle());
}

function mountInlineAssistantAfterSettle(): void {
  styles();
  removeAllInlineButtons();
  let enabled = false;
  const buttons = new Map<HTMLElement, HTMLButtonElement>();
  const reposition = () => buttons.forEach((button, element) => positionButton(element, button));
  const resizeObserver = new ResizeObserver(reposition);
  // `position: fixed` only tracks the real browser viewport in the top frame; inside a nested
  // frame (e.g. a Greenhouse application form embedded in an iframe) it's anchored to that
  // frame's own layout box instead, so a field scrolling out of view is already clipped by the
  // browser with no JS help needed - and IntersectionObserver's ratio precision is unreliable
  // across a cross-origin frame boundary in the first place, so only use it in the top frame,
  // where its one job is to stop the icon staying pinned to a screen edge while its field scrolls away.
  const visibilityObserver = window.top === window ? new IntersectionObserver((entries) => entries.forEach((entry) => {
    const button = buttons.get(entry.target as HTMLElement);
    if (!button) return;
    if (!entry.isIntersecting || entry.intersectionRatio < 0.5) button.hidden = true;
    else positionButton(entry.target as HTMLElement, button);
  }), { threshold: [0, 0.5, 1] }) : null;

  const clearButtons = () => {
    buttons.forEach((button, element) => {
      resizeObserver.unobserve(element);
      visibilityObserver?.unobserve(element);
      button.remove();
    });
    buttons.clear();
  };

  const addButtons = () => {
    if (!enabled) return;
    detectFormFields().forEach((field) => {
      const element = findField(field.fieldId);
      const isTextarea = element instanceof HTMLTextAreaElement;
      if (field.isSensitive || (!field.isLikelyApplicationQuestion && !isTextarea) || document.querySelector(`button[data-field-id="${CSS.escape(field.fieldId)}"]`)) return;
      if (!element) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = BUTTON_CLASS;
      button.dataset.fieldId = field.fieldId;
      button.setAttribute("aria-label", "Generate answer with ResuMorph");
      const icon = document.createElement("img");
      icon.src = BUTTON_ICON;
      icon.alt = "";
      button.append(icon);
      button.addEventListener("click", () => void ask(field, button));
      document.body.append(button);
      buttons.set(element, button);
      resizeObserver.observe(element);
      visibilityObserver?.observe(element);
      positionButton(element, button);
    });
  };

  const setEnabled = (next: boolean) => {
    enabled = next;
    if (!enabled) {
      clearButtons();
      return;
    }
    addButtons();
    reposition();
  };

  void isExtensionEnabled().then(setEnabled).catch(() => setEnabled(true));
  new MutationObserver(() => { addButtons(); reposition(); }).observe(document.documentElement, { childList: true, subtree: true });
  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== "local") return;
    const change = changes[EXTENSION_ENABLED_STORAGE_KEY];
    if (change) setEnabled(change.newValue !== false);
  });
  addEventListener("scroll", reposition, true);
  addEventListener("resize", reposition);
}
