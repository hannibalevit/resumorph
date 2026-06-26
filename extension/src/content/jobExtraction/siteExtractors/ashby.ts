import type { SiteExtractor } from "../types";
import { buildSiteResult } from "./generic";

export const ashbyExtractor: SiteExtractor = {
  name: "ashby",
  matches: (url) => url.hostname.includes("ashbyhq.com"),
  extract: () =>
    buildSiteResult("ashby", 0.86, {
      title: ["[data-testid='job-title']", "h1"],
      company: ["[data-testid='company-name']", "header a"],
      location: ["[data-testid='job-location']", "[class*='location']"],
      description: ["[data-testid='job-description']", "[class*='job-posting']", "main"],
    }),
};
