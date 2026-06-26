export type DetectedFormField = {
  fieldId: string;
  tagName: string;
  type?: string;
  name?: string;
  id?: string;
  label?: string;
  placeholder?: string;
  ariaLabel?: string;
  nearbyText?: string;
  currentValue?: string;
  selector: string;
  isSensitive: boolean;
  isLikelyApplicationQuestion: boolean;
};

export type PageSnapshot = {
  url: string;
  normalizedUrl: string;
  title: string;
  hostname: string;
  capturedAt: string;
  visibleText: string;
  selectedText?: string;
  meta: Record<string, string | undefined>;
  jsonLd: unknown[];
  headings: Array<{ level: number; text: string }>;
  links: Array<{ text: string; href: string }>;
  formFields: DetectedFormField[];
  domBlocks: Array<{ selector: string; text: string; score: number }>;
};

export type JobContext = {
  companyName?: string | null;
  positionTitle?: string | null;
  location?: string | null;
  employmentType?: string | null;
  remotePolicy?: string | null;
  jobDescription?: string | null;
  responsibilities: string[];
  requirements: string[];
  niceToHave: string[];
  benefits: string[];
  keywords: string[];
  confidence: number;
  warnings: string[];
};

export type ArtifactSummary = {
  id: string;
  artifactType: string;
  title: string;
  fileName?: string | null;
  createdAt: string;
  llmProvider?: string | null;
  llmModel?: string | null;
};
export type JobSessionSummary = {
  id: string; canonicalJobKey: string; sourceUrl: string; companyName?: string | null;
  positionTitle?: string | null; location?: string | null; extractionConfidence: number; updatedAt: string; artifacts: ArtifactSummary[];
};
export type JobSession = JobSessionSummary & {
  normalizedUrl: string; hostname: string; jobContext: JobContext; rawPageSnapshot: PageSnapshot;
  createdAt: string; lastUsedAt: string;
};

export type ApiError = { error?: { code?: string; message?: string } };
