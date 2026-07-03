import type { ExtractedJobPage } from "../types";
import { getVisibleText, truncateText } from "../extractVisibleText";

type SiteResult = Partial<ExtractedJobPage>;

export function firstText(selectors: string[]): string | undefined {
  for (const selector of selectors) {
    const element = document.querySelector(selector);
    // Company logos commonly carry alt text like "Acme logo" / "Acme Inc. logo".
    const imageAlt = element instanceof HTMLImageElement
      ? element.alt.trim().replace(/\s+logo$/i, "").trim()
      : "";
    const text = element ? imageAlt || getVisibleText(element) || element.textContent?.trim() : "";
    if (text) {
      return text.trim();
    }
  }

  return undefined;
}

export function combinedText(selectors: string[]): string {
  const parts: string[] = [];

  for (const selector of selectors) {
    document.querySelectorAll(selector).forEach((element) => {
      const text = getVisibleText(element);
      if (text.length > 80) {
        parts.push(text);
      }
    });
  }

  return truncateText(parts.join("\n\n"));
}

export function buildSiteResult(
  extractorName: string,
  confidence: number,
  selectors: {
    title: string[];
    company: string[];
    location: string[];
    description: string[];
  },
): SiteResult | null {
  const cleanedText = combinedText(selectors.description);
  if (cleanedText.length < 300) {
    return null;
  }

  return {
    source: "site_specific",
    confidence,
    detected: {
      jobTitle: firstText(selectors.title),
      company: firstText(selectors.company),
      location: firstText(selectors.location),
    },
    sections: {
      description: cleanedText,
    },
    rawText: cleanedText,
    cleanedText,
    debug: {
      textLength: cleanedText.length,
      jsonLdFound: false,
      siteExtractor: extractorName,
      warnings: [],
    },
  };
}
