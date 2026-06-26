export type ExtractedJobPage = {
  url: string;
  title: string;
  text: string;
  detected?: {
    jobTitle?: string;
    company?: string;
    location?: string;
  };
};

export type GenerateResumeRequest = {
  baseResume: string;
  jobPage: ExtractedJobPage;
  options?: {
    targetFormat?: "docx";
    language?: "en" | "ru";
  };
};

export type GenerateResumeResponse = {
  fileName: string;
  mimeType: string;
  base64: string;
  notes: {
    detectedJobTitle?: string;
    detectedCompany?: string;
    keywordsUsed?: string[];
    missingRequirements?: string[];
  };
};
