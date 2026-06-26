import { extractByDomScoring } from "./jobExtraction/domScoring";
import { extractJsonLdJobPosting } from "./jobExtraction/extractJsonLdJobPosting";
import { extractSelectedText } from "./jobExtraction/extractSelectedText";
import { extractVisibleText, truncateText } from "./jobExtraction/extractVisibleText";
import { detectFormFields } from "./formDetector";
import type { PageSnapshot } from "../shared/sidepanelTypes";

function normalizeUrl(url: string): string {
  const value = new URL(url);
  ["ref", "source", "trk", "trackingId", "utm_source", "utm_medium", "utm_campaign"].forEach((key) => value.searchParams.delete(key));
  value.hash = "";
  value.pathname = value.pathname.replace(/\/$/, "") || "/";
  return value.toString();
}

function jsonLd(): unknown[] {
  return [...document.querySelectorAll('script[type="application/ld+json"]')].flatMap((node) => {
    try { return [JSON.parse(node.textContent ?? "")]; } catch { return []; }
  }).slice(0, 10);
}

export function createPageSnapshot(): PageSnapshot {
  const legacy = extractJsonLdJobPosting() ?? extractByDomScoring();
  const visibleText = truncateText(legacy?.cleanedText || extractVisibleText(), 80_000);
  const blocks = legacy?.debug?.candidateBlocks?.map((block) => ({ selector: block.selector, text: block.textPreview, score: block.score })) ?? [];
  const fields = detectFormFields();
  return {
    url: location.href, normalizedUrl: normalizeUrl(location.href), title: document.title, hostname: location.hostname, capturedAt: new Date().toISOString(),
    visibleText, selectedText: extractSelectedText() || undefined,
    meta: { description: document.querySelector('meta[name="description"]')?.getAttribute("content") ?? undefined, ogTitle: document.querySelector('meta[property="og:title"]')?.getAttribute("content") ?? undefined, ogDescription: document.querySelector('meta[property="og:description"]')?.getAttribute("content") ?? undefined },
    jsonLd: jsonLd(), headings: [...document.querySelectorAll<HTMLElement>('h1,h2,h3,h4,h5,h6')].slice(0, 40).map((node) => ({ level: Number(node.tagName.slice(1)), text: (node.innerText || "").trim().slice(0, 500) })).filter((item) => item.text),
    links: [...document.querySelectorAll<HTMLAnchorElement>('a[href]')].slice(0, 100).map((node) => ({ text: (node.innerText || "").trim().slice(0, 300), href: node.href })).filter((item) => item.text),
    formFields: fields, domBlocks: blocks,
  };
}
