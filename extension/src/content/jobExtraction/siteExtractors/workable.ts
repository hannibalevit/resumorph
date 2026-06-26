import type { SiteExtractor } from "../types";
import { buildSiteResult } from "./generic";

export const workableExtractor: SiteExtractor = {
  name: "workable",
  matches: (url) => url.hostname.includes("workable.com"),
  extract: () =>
    buildSiteResult("workable", 0.84, {
      title: ["[data-ui='job-title']", "h1"],
      company: ["[data-ui='company-name']", "[class*='company']"],
      location: ["[data-ui='job-location']", "[class*='location']"],
      description: ["[data-ui='job-description']", "[class*='job-description']", "main"],
    }),
};
