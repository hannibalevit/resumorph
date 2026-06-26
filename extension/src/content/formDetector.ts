import type { DetectedFormField } from "../shared/sidepanelTypes";

const FIELD_SELECTOR = 'input[type="text"], input[type="email"], input[type="tel"], input[type="url"], textarea, select, [contenteditable="true"]';
const SENSITIVE = /password|credit.?card|card.?number|payment|ssn|social.?security|passport|national.?id|security.?question|medical|disability|gender|race|ethnicity|veteran/i;

function cssSelector(element: Element): string {
  if (element.id) return `#${CSS.escape(element.id)}`;
  const parts: string[] = [];
  let node: Element | null = element;
  while (node && parts.length < 5) {
    let part = node.tagName.toLowerCase();
    if (node.classList.length) part += `.${CSS.escape(node.classList[0])}`;
    const siblings = node.parentElement ? [...node.parentElement.children].filter((item) => item.tagName === node?.tagName) : [];
    if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(node) + 1})`;
    parts.unshift(part);
    node = node.parentElement;
  }
  return parts.join(" > ");
}

function labelFor(element: HTMLElement): string {
  const id = element.id;
  if (id) {
    const explicit = document.querySelector(`label[for="${CSS.escape(id)}"]`)?.textContent;
    if (explicit?.trim()) return explicit.trim();
  }
  const parentLabel = element.closest("label")?.textContent;
  if (parentLabel?.trim()) return parentLabel.trim();
  const aria = element.getAttribute("aria-label");
  if (aria) return aria;
  const labelledBy = element.getAttribute("aria-labelledby");
  if (labelledBy) {
    const text = labelledBy.split(/\s+/).map((fieldId) => document.getElementById(fieldId)?.textContent?.trim()).filter(Boolean).join(" ");
    if (text) return text;
  }
  const legend = element.closest("fieldset")?.querySelector("legend")?.textContent?.trim();
  if (legend) return legend;
  return element.getAttribute("placeholder") ?? element.previousElementSibling?.textContent?.trim() ?? "";
}

export function detectFormFields(): DetectedFormField[] {
  return [...document.querySelectorAll<HTMLElement>(FIELD_SELECTOR)].map((element, index) => {
    const input = element as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
    const label = labelFor(element).replace(/\s+/g, " ").trim().slice(0, 500);
    const nearbyText = element.parentElement?.innerText?.replace(/\s+/g, " ").trim().slice(0, 600) ?? "";
    const type = element.getAttribute("type") ?? element.tagName.toLowerCase();
    const haystack = `${label} ${nearbyText} ${element.getAttribute("name") ?? ""} ${element.id}`;
    const fieldId = element.dataset.resumeTailorFieldId ?? `resume-tailor-${index}-${Math.random().toString(36).slice(2, 8)}`;
    element.dataset.resumeTailorFieldId = fieldId;
    return {
      fieldId,
      tagName: element.tagName.toLowerCase(), type, name: element.getAttribute("name") ?? undefined, id: element.id || undefined,
      label: label || undefined, placeholder: element.getAttribute("placeholder") ?? undefined, ariaLabel: element.getAttribute("aria-label") ?? undefined,
      nearbyText: nearbyText || undefined, currentValue: "value" in input ? input.value : element.textContent ?? "", selector: cssSelector(element),
      isSensitive: SENSITIVE.test(haystack) || type === "password", isLikelyApplicationQuestion: Boolean(label || nearbyText),
    };
  });
}

export function findField(fieldId: string): HTMLElement | undefined {
  return [...document.querySelectorAll<HTMLElement>(FIELD_SELECTOR)].find((element) => element.dataset.resumeTailorFieldId === fieldId);
}
