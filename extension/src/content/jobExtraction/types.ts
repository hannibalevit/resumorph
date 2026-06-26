export type JobExtractionSource =
  | "selected_text"
  | "json_ld_job_posting"
  | "site_specific"
  | "dom_scoring"
  | "visible_text_fallback";

export type JobSections = {
  description?: string;
  responsibilities?: string;
  requirements?: string;
  qualifications?: string;
  benefits?: string;
  companyInfo?: string;
};

export type ExtractedJobPage = {
  url: string;
  pageTitle: string;
  source: JobExtractionSource;
  confidence: number;
  extractedAt: string;
  detected: {
    jobTitle?: string;
    company?: string;
    location?: string;
    employmentType?: string;
    salary?: string;
  };
  sections: JobSections;
  rawText: string;
  cleanedText: string;
  debug: {
    textLength: number;
    selectedTextLength?: number;
    jsonLdFound: boolean;
    siteExtractor?: string;
    candidateBlocks?: Array<{
      selector: string;
      score: number;
      textPreview: string;
    }>;
    warnings: string[];
  };
};

export type SiteExtractor = {
  name: string;
  matches: (url: URL) => boolean;
  extract: () => Partial<ExtractedJobPage> | null;
};

export type ExtractionCandidate = {
  element: Element;
  selector: string;
  score: number;
  text: string;
};
