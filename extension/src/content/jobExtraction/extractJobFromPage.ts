import { extractByDomScoring } from "./domScoring";
import { extractJsonLdJobPosting, hasJsonLdJobPosting } from "./extractJsonLdJobPosting";
import { extractSelectedText } from "./extractSelectedText";
import { extractVisibleText, truncateText } from "./extractVisibleText";
import { runSiteSpecificExtractor } from "./siteExtractors";
import type { ExtractedJobPage, JobExtractionSource } from "./types";

const MIN_SELECTED_TEXT_LENGTH = 300;

function buildResult(
  partial: Partial<ExtractedJobPage>,
  source: JobExtractionSource,
  confidence: number,
  warnings: string[],
): ExtractedJobPage {
  const cleanedText = truncateText(partial.cleanedText ?? partial.rawText ?? "");

  return {
    url: window.location.href,
    pageTitle: document.title,
    source,
    confidence,
    extractedAt: new Date().toISOString(),
    detected: partial.detected ?? {},
    sections: partial.sections ?? { description: cleanedText },
    rawText: truncateText(partial.rawText ?? cleanedText),
    cleanedText,
    debug: {
      textLength: cleanedText.length,
      selectedTextLength: partial.debug?.selectedTextLength,
      jsonLdFound: partial.debug?.jsonLdFound ?? hasJsonLdJobPosting(),
      siteExtractor: partial.debug?.siteExtractor,
      candidateBlocks: partial.debug?.candidateBlocks,
      warnings: [...warnings, ...(partial.debug?.warnings ?? [])],
    },
  };
}

function hasGoodText(result: Partial<ExtractedJobPage> | null): result is Partial<ExtractedJobPage> {
  return Boolean(result?.cleanedText && result.cleanedText.length >= 300);
}

export async function extractJobFromPage(): Promise<ExtractedJobPage> {
  const warnings: string[] = [];
  const selectedText = extractSelectedText();

  if (selectedText.length >= MIN_SELECTED_TEXT_LENGTH) {
    return buildResult(
      {
        detected: {},
        sections: { description: selectedText },
        rawText: selectedText,
        cleanedText: selectedText,
        debug: {
          textLength: selectedText.length,
          selectedTextLength: selectedText.length,
          jsonLdFound: hasJsonLdJobPosting(),
          warnings: [],
        },
      },
      "selected_text",
      0.95,
      warnings,
    );
  }

  if (selectedText.length > 0) {
    warnings.push("Selected text was ignored because it is shorter than 300 characters.");
  }

  const jsonLdResult = extractJsonLdJobPosting();
  if (hasGoodText(jsonLdResult)) {
    return buildResult(jsonLdResult, "json_ld_job_posting", 0.9, warnings);
  }

  const siteResult = runSiteSpecificExtractor(new URL(window.location.href));
  if (hasGoodText(siteResult)) {
    return buildResult(siteResult, "site_specific", siteResult.confidence ?? 0.8, warnings);
  }

  const domResult = extractByDomScoring();
  if (hasGoodText(domResult)) {
    return buildResult(domResult, "dom_scoring", domResult.confidence ?? 0.6, warnings);
  }

  warnings.push("Used visible page text fallback because structured and scored extraction failed.");
  const visibleText = extractVisibleText();

  return buildResult(
    {
      detected: {
        jobTitle: document.querySelector("h1")?.textContent?.trim() || undefined,
      },
      sections: { description: visibleText },
      rawText: visibleText,
      cleanedText: visibleText,
      debug: {
        textLength: visibleText.length,
        selectedTextLength: selectedText.length || undefined,
        jsonLdFound: hasJsonLdJobPosting(),
        warnings: [],
      },
    },
    "visible_text_fallback",
    0.3,
    warnings,
  );
}
