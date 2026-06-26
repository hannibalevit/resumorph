import type { ExtractedJobPage, SiteExtractor } from "../types";
import { linkedinExtractor } from "./linkedin";
import { greenhouseExtractor } from "./greenhouse";
import { leverExtractor } from "./lever";
import { ashbyExtractor } from "./ashby";
import { workableExtractor } from "./workable";
import { indeedExtractor } from "./indeed";
import { smartRecruitersExtractor } from "./smartRecruiters";

export const siteExtractors: SiteExtractor[] = [
  linkedinExtractor,
  greenhouseExtractor,
  leverExtractor,
  ashbyExtractor,
  workableExtractor,
  indeedExtractor,
  smartRecruitersExtractor,
];

export function runSiteSpecificExtractor(url: URL): Partial<ExtractedJobPage> | null {
  const extractor = siteExtractors.find((candidate) => candidate.matches(url));
  if (!extractor) {
    return null;
  }

  try {
    return extractor.extract();
  } catch {
    return null;
  }
}
