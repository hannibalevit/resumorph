import type { SiteExtractor } from "../types";
import { buildSiteResult } from "./generic";

export const linkedinExtractor: SiteExtractor = {
  name: "linkedin",
  matches: (url) => url.hostname.includes("linkedin."),
  extract: () =>
    buildSiteResult("linkedin", 0.85, {
      title: [
        ".job-details-jobs-unified-top-card__job-title",
        ".top-card-layout__title",
        "h1",
      ],
      company: [
        ".job-details-jobs-unified-top-card__company-name",
        ".topcard__org-name-link",
      ],
      location: [
        ".job-details-jobs-unified-top-card__tertiary-description-container",
        ".topcard__flavor--bullet",
      ],
      description: [".jobs-description-content__text", ".description__text", "main"],
    }),
};
