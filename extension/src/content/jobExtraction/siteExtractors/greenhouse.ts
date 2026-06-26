import type { SiteExtractor } from "../types";
import { buildSiteResult } from "./generic";

export const greenhouseExtractor: SiteExtractor = {
  name: "greenhouse",
  matches: (url) => url.hostname.includes("greenhouse.io") || url.hostname.includes("greenhouse.com"),
  extract: () =>
    buildSiteResult("greenhouse", 0.88, {
      title: [".app-title", ".job__title", "h1"],
      company: [".company-name", ".header-company-name"],
      location: [".location", ".job__location"],
      description: ["#content", ".content", ".job__description", "main"],
    }),
};
