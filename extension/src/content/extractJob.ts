import { extractJobFromPage } from "./jobExtraction/extractJobFromPage";
import type { ExtractedJobPage } from "./jobExtraction/types";

declare global {
  interface Window {
    __resumorphLastExtraction?: ExtractedJobPage;
    __resumorphExtractionError?: string;
    __resumorphExtractionPromise?: Promise<void>;
    __resumorphRunExtraction?: () => Promise<void>;
  }
}

window.__resumorphRunExtraction = () => {
  window.__resumorphExtractionPromise = extractJobFromPage()
    .then((extraction) => {
      window.__resumorphLastExtraction = extraction;
      window.__resumorphExtractionError = undefined;
    })
    .catch((error: unknown) => {
      window.__resumorphExtractionError =
        error instanceof Error ? error.message : "Could not extract job page.";
    });

  return window.__resumorphExtractionPromise;
};

void window.__resumorphRunExtraction();

export { extractJobFromPage };
export type { ExtractedJobPage };
