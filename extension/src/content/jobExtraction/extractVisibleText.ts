const BLOCKED_SELECTOR = "script,style,noscript,nav,footer,header,aside";
const MAX_TEXT_LENGTH = 50_000;

export function cleanWhitespace(text: string): string {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function dedupeLines(text: string): string {
  const seen = new Set<string>();
  const lines = text.split("\n");
  const result: string[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    const key = trimmed.toLowerCase();

    if (!trimmed) {
      if (result.at(-1) !== "") {
        result.push("");
      }
      continue;
    }

    if (!seen.has(key)) {
      seen.add(key);
      result.push(line);
    }
  }

  return result.join("\n").trim();
}

export function stripHtml(html: string): string {
  const template = document.createElement("template");
  template.innerHTML = html;
  return cleanWhitespace(template.content.textContent ?? "");
}

export function truncateText(text: string, maxLength = MAX_TEXT_LENGTH): string {
  const cleaned = cleanWhitespace(text);
  if (cleaned.length <= maxLength) {
    return cleaned;
  }

  return `${cleaned.slice(0, maxLength).trim()}...`;
}

export function isElementVisible(element: Element): boolean {
  if (!(element instanceof HTMLElement)) {
    return false;
  }

  if (element.matches(BLOCKED_SELECTOR)) {
    return false;
  }

  if (element.closest(BLOCKED_SELECTOR)) {
    return false;
  }

  const style = window.getComputedStyle(element);
  if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) {
    return false;
  }

  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

export function getVisibleText(element: Element): string {
  if (!isElementVisible(element)) {
    return "";
  }

  const clone = element.cloneNode(true) as Element;
  clone.querySelectorAll(BLOCKED_SELECTOR).forEach((blocked) => blocked.remove());
  clone
    .querySelectorAll("[aria-hidden='true'], [hidden], .cookie, .cookie-banner, .modal, .newsletter")
    .forEach((blocked) => blocked.remove());

  return cleanWhitespace((clone as HTMLElement).innerText || clone.textContent || "");
}

export function extractVisibleText(maxLength = MAX_TEXT_LENGTH): string {
  const body = document.body;
  if (!body) {
    return "";
  }

  return truncateText(dedupeLines(getVisibleText(body)), maxLength);
}
