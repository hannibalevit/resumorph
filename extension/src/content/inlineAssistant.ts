import { detectFormFields, findField } from "./formDetector";
import type { DetectedFormField } from "../shared/sidepanelTypes";

const BUTTON_CLASS = "resume-tailor-ai-button";
const BUTTON_ICON = chrome.runtime.getURL("icons/icon-32.png");
const BUTTON_INSET = 5;
const BUTTON_MAX_SIZE = 26;
const EXTENSION_ENABLED_STORAGE_KEY = "extensionEnabled";
const INVALIDATED_CONTEXT = /extension context invalidated|context invalidated/i;

async function isExtensionEnabled(): Promise<boolean> {
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

function styles(): void {
  if (document.getElementById("resume-tailor-ai-styles")) return;
  const style = document.createElement("style");
  style.id = "resume-tailor-ai-styles";
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
    if (!active.jobSessionId) throw new Error("Open Resume Tailor and scan or select a job first.");
    const response = await generateFieldAnswer(active.jobSessionId, field);
    if (!response.answer) throw new Error(response.warnings[0] ?? "No safe answer was generated.");
    const element = findField(field.fieldId);
    if (!element) throw new Error("The form field is no longer available. Refresh the page and try again.");
    insertValue(element, response.answer);
  } catch (error) {
    if (isInvalidatedContextError(error)) {
      removeAllInlineButtons();
      alert("Resume Tailor was reloaded. Refresh this browser tab, then try generating the answer again.");
    } else {
      alert(error instanceof Error ? error.message : "Could not generate an answer.");
    }
  } finally {
    if (!button.isConnected) return;
    button.disabled = false;
    button.setAttribute("aria-label", "Generate answer with Resume Tailor");
  }
}

export function mountInlineAssistant(): void {
  styles();
  removeAllInlineButtons();
  let enabled = false;
  const buttons = new Map<HTMLElement, HTMLButtonElement>();
  const reposition = () => buttons.forEach((button, element) => positionButton(element, button));
  const resizeObserver = new ResizeObserver(reposition);
  const visibilityObserver = new IntersectionObserver((entries) => entries.forEach((entry) => {
    const button = buttons.get(entry.target as HTMLElement);
    if (!button) return;
    // Do not leave an icon pinned to a viewport edge while its field scrolls away.
    if (!entry.isIntersecting || entry.intersectionRatio < 0.99) button.hidden = true;
    else positionButton(entry.target as HTMLElement, button);
  }), { threshold: [0, 0.99, 1] });

  const clearButtons = () => {
    buttons.forEach((button, element) => {
      resizeObserver.unobserve(element);
      visibilityObserver.unobserve(element);
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
      button.setAttribute("aria-label", "Generate answer with Resume Tailor");
      const icon = document.createElement("img");
      icon.src = BUTTON_ICON;
      icon.alt = "";
      button.append(icon);
      button.addEventListener("click", () => void ask(field, button));
      document.body.append(button);
      buttons.set(element, button);
      resizeObserver.observe(element);
      visibilityObserver.observe(element);
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
