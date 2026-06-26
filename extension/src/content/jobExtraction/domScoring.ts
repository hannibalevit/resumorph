import type { ExtractionCandidate, ExtractedJobPage } from "./types";
import { getVisibleText, truncateText } from "./extractVisibleText";

const POSITIVE_KEYWORDS = [
  "requirements",
  "responsibilities",
  "qualifications",
  "what you'll do",
  "what you will do",
  "about the role",
  "about this role",
  "job description",
  "experience",
  "skills",
  "benefits",
  "salary",
  "remote",
  "hybrid",
  "full-time",
  "part-time",
];

const NEGATIVE_KEYWORDS = [
  "cookie",
  "privacy policy",
  "similar jobs",
  "recommended jobs",
  "people also viewed",
  "sign in",
  "create alert",
  "newsletter",
  "terms of service",
];

const CANDIDATE_SELECTOR =
  "main,article,section,div,[role='main'],[data-testid],.job-description,.description,.posting,.content";

function selectorFor(element: Element): string {
  if (element.id) {
    return `#${element.id}`;
  }

  const className = [...element.classList].slice(0, 3).join(".");
  if (className) {
    return `${element.tagName.toLowerCase()}.${className}`;
  }

  const testId = element.getAttribute("data-testid");
  if (testId) {
    return `${element.tagName.toLowerCase()}[data-testid='${testId}']`;
  }

  return element.tagName.toLowerCase();
}

function linkRatio(element: Element, textLength: number): number {
  if (textLength === 0) {
    return 0;
  }

  const linkTextLength = [...element.querySelectorAll("a")]
    .map((link) => link.textContent?.length ?? 0)
    .reduce((sum, length) => sum + length, 0);

  return linkTextLength / textLength;
}

function scoreCandidate(element: Element, text: string): number {
  const lower = text.toLowerCase();
  let score = 0;
  const textLength = text.length;

  score += Math.min(textLength / 120, 35);
  score += POSITIVE_KEYWORDS.filter((keyword) => lower.includes(keyword)).length * 8;
  score -= NEGATIVE_KEYWORDS.filter((keyword) => lower.includes(keyword)).length * 12;
  score += (text.match(/(^|\n)\s*[-*•]/g) ?? []).length * 1.5;

  const lines = text.split("\n").filter((line) => line.trim().length > 0);
  const avgLineLength = textLength / Math.max(lines.length, 1);
  if (avgLineLength > 35 && avgLineLength < 220) {
    score += 8;
  }

  const ratio = linkRatio(element, textLength);
  if (ratio > 0.35) {
    score -= 25;
  }

  return Math.round(score * 100) / 100;
}

function collectCandidates(): ExtractionCandidate[] {
  const elements = [...document.querySelectorAll(CANDIDATE_SELECTOR)].slice(0, 450);
  const candidates: ExtractionCandidate[] = [];

  for (const element of elements) {
    const text = getVisibleText(element);
    if (text.length < 300) {
      continue;
    }

    candidates.push({
      element,
      selector: selectorFor(element),
      score: scoreCandidate(element, text),
      text,
    });
  }

  return candidates.sort((a, b) => b.score - a.score).slice(0, 8);
}

export function extractByDomScoring(): Partial<ExtractedJobPage> | null {
  const candidates = collectCandidates();
  const [best] = candidates;

  if (!best || best.score < 25) {
    return null;
  }

  const cleanedText = truncateText(best.text);

  return {
    source: "dom_scoring",
    confidence: Math.min(0.75, Math.max(0.5, best.score / 100)),
    detected: {
      jobTitle: document.querySelector("h1")?.textContent?.trim() || undefined,
    },
    sections: {
      description: cleanedText,
    },
    rawText: best.text,
    cleanedText,
    debug: {
      textLength: cleanedText.length,
      jsonLdFound: false,
      candidateBlocks: candidates.map((candidate) => ({
        selector: candidate.selector,
        score: candidate.score,
        textPreview: candidate.text.slice(0, 160),
      })),
      warnings: [],
    },
  };
}
