import type { SiteExtractor } from "../types";
import { buildSiteResult } from "./generic";

export const indeedExtractor: SiteExtractor = {
  name: "indeed",
  matches: (url) => url.hostname.includes("indeed."),
  extract: () =>
    buildSiteResult("indeed", 0.82, {
      title: ["[data-testid='jobsearch-JobInfoHeader-title']", "h1"],
      company: ["[data-testid='inlineHeader-companyName']", "[data-company-name='true']"],
      location: ["[data-testid='job-location']", "[data-testid='inlineHeader-companyLocation']"],
      description: ["#jobDescriptionText", "[data-testid='jobsearch-JobComponent-description']", "main"],
    }),
};
