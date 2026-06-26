import type { SiteExtractor } from "../types";
import { buildSiteResult } from "./generic";

export const leverExtractor: SiteExtractor = {
  name: "lever",
  matches: (url) => url.hostname.includes("lever.co"),
  extract: () =>
    buildSiteResult("lever", 0.88, {
      title: [".posting-headline h2", ".posting-headline h1", "h1"],
      company: [".main-header-logo img[alt]", ".company"],
      location: [".posting-categories .location", ".sort-by-location"],
      description: [".section-wrapper", ".posting-page", ".posting", "main"],
    }),
};
