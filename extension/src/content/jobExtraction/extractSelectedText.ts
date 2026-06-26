import { cleanWhitespace, truncateText } from "./extractVisibleText";

export function extractSelectedText(): string {
  return truncateText(cleanWhitespace(window.getSelection()?.toString() ?? ""));
}
