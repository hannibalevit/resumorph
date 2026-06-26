import type { SiteExtractor } from "../types";
import { buildSiteResult } from "./generic";

export const smartRecruitersExtractor: SiteExtractor = {
  name: "smartRecruiters",
  matches: (url) => url.hostname.includes("smartrecruiters.com"),
  extract: () =>
    buildSiteResult("smartRecruiters", 0.84, {
      title: ["[data-testid='job-title']", ".job-title", "h1"],
      company: [".company-name", "[data-testid='company-name']"],
      location: [".job-location", "[data-testid='job-location']", "[class*='location']"],
      description: [".job-description", "[data-testid='job-description']", "article", "main"],
    }),
};
