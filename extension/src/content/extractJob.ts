import { extractJobFromPage } from "./jobExtraction/extractJobFromPage";
import type { ExtractedJobPage } from "./jobExtraction/types";

declare global {
  interface Window {
    __resumeTailorLastExtraction?: ExtractedJobPage;
    __resumeTailorExtractionError?: string;
    __resumeTailorExtractionPromise?: Promise<void>;
    __resumeTailorRunExtraction?: () => Promise<void>;
  }
}

window.__resumeTailorRunExtraction = () => {
  window.__resumeTailorExtractionPromise = extractJobFromPage()
    .then((extraction) => {
      window.__resumeTailorLastExtraction = extraction;
      window.__resumeTailorExtractionError = undefined;
    })
    .catch((error: unknown) => {
      window.__resumeTailorExtractionError =
        error instanceof Error ? error.message : "Could not extract job page.";
    });

  return window.__resumeTailorExtractionPromise;
};

void window.__resumeTailorRunExtraction();

export { extractJobFromPage };
export type { ExtractedJobPage };
