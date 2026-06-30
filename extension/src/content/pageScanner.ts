import { extractByDomScoring } from "./jobExtraction/domScoring";
import { extractJsonLdJobPosting } from "./jobExtraction/extractJsonLdJobPosting";
import { extractSelectedText } from "./jobExtraction/extractSelectedText";
import { extractVisibleText, truncateText } from "./jobExtraction/extractVisibleText";
import { runSiteSpecificExtractor } from "./jobExtraction/siteExtractors";
import { detectFormFields } from "./formDetector";
import type { ExtractedJobPage, JobExtractionSource } from "./jobExtraction/types";
import type { PageSnapshot } from "../shared/sidepanelTypes";

const MIN_SELECTED_TEXT_LENGTH = 300;
const MAX_SNAPSHOT_TEXT_LENGTH = 80_000;

type PrimaryJobText = {
  text: string;
  source: JobExtractionSource;
  confidence: number;
  warnings: string[];
  candidateBlocks?: Array<{ selector: string; text: string; score: number }>;
};

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

function hasGoodText(result: Partial<ExtractedJobPage> | null): result is Partial<ExtractedJobPage> {
  return Boolean(result?.cleanedText && result.cleanedText.length >= MIN_SELECTED_TEXT_LENGTH);
}

function candidateBlocks(result: Partial<ExtractedJobPage> | null): Array<{ selector: string; text: string; score: number }> {
  return result?.debug?.candidateBlocks?.map((block) => ({ selector: block.selector, text: block.textPreview, score: block.score })) ?? [];
}

function getPrimaryJobText(selectedText: string): PrimaryJobText | null {
  const warnings: string[] = [];

  if (selectedText.length >= MIN_SELECTED_TEXT_LENGTH) {
    return {
      text: truncateText(selectedText, MAX_SNAPSHOT_TEXT_LENGTH),
      source: "selected_text",
      confidence: 0.95,
      warnings,
    };
  }

  if (selectedText.length > 0) {
    warnings.push("Selected text was ignored because it is shorter than 300 characters.");
  }

  const jsonLdResult = extractJsonLdJobPosting();
  if (hasGoodText(jsonLdResult)) {
    return {
      text: truncateText(jsonLdResult.cleanedText ?? "", MAX_SNAPSHOT_TEXT_LENGTH),
      source: "json_ld_job_posting",
      confidence: jsonLdResult.confidence ?? 0.9,
      warnings,
      candidateBlocks: candidateBlocks(jsonLdResult),
    };
  }

  const siteResult = runSiteSpecificExtractor(new URL(window.location.href));
  if (hasGoodText(siteResult)) {
    return {
      text: truncateText(siteResult.cleanedText ?? "", MAX_SNAPSHOT_TEXT_LENGTH),
      source: "site_specific",
      confidence: siteResult.confidence ?? 0.8,
      warnings,
      candidateBlocks: candidateBlocks(siteResult),
    };
  }

  const domResult = extractByDomScoring();
  if (hasGoodText(domResult)) {
    return {
      text: truncateText(domResult.cleanedText ?? "", MAX_SNAPSHOT_TEXT_LENGTH),
      source: "dom_scoring",
      confidence: domResult.confidence ?? 0.6,
      warnings,
      candidateBlocks: candidateBlocks(domResult),
    };
  }

  warnings.push("Structured and scored extraction did not find a reliable primary job block; using full visible page text only.");
  return warnings.length ? { text: "", source: "visible_text_fallback", confidence: 0.3, warnings } : null;
}

export function createPageSnapshot(): PageSnapshot {
  const selectedText = extractSelectedText();
  const primary = getPrimaryJobText(selectedText);
  const visibleText = extractVisibleText(MAX_SNAPSHOT_TEXT_LENGTH);
  const fields = detectFormFields();
  return {
    url: location.href, normalizedUrl: normalizeUrl(location.href), title: document.title, hostname: location.hostname, capturedAt: new Date().toISOString(),
    visibleText,
    selectedText: selectedText.length >= MIN_SELECTED_TEXT_LENGTH ? selectedText : undefined,
    primaryJobText: primary?.text || undefined,
    primaryJobSource: primary?.source,
    primaryJobConfidence: primary?.confidence,
    extractionWarnings: primary?.warnings ?? [],
    meta: { description: document.querySelector('meta[name="description"]')?.getAttribute("content") ?? undefined, ogTitle: document.querySelector('meta[property="og:title"]')?.getAttribute("content") ?? undefined, ogDescription: document.querySelector('meta[property="og:description"]')?.getAttribute("content") ?? undefined },
    jsonLd: jsonLd(), headings: [...document.querySelectorAll<HTMLElement>('h1,h2,h3,h4,h5,h6')].slice(0, 40).map((node) => ({ level: Number(node.tagName.slice(1)), text: (node.innerText || "").trim().slice(0, 500) })).filter((item) => item.text),
    links: [...document.querySelectorAll<HTMLAnchorElement>('a[href]')].slice(0, 100).map((node) => ({ text: (node.innerText || "").trim().slice(0, 300), href: node.href })).filter((item) => item.text),
    formFields: fields, domBlocks: primary?.candidateBlocks ?? [],
  };
}
