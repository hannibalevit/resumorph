import "./popup.css";
import { generateResume } from "../shared/api";
import { clearBaseResume, getBaseResume } from "../shared/storage";
import type { ExtractedJobPage } from "../content/jobExtraction/types";
import type { GenerateResumeResponse } from "../shared/types";

const resumeStatus = getElement<HTMLParagraphElement>("resumeStatus");
const uploadPanel = getElement<HTMLElement>("uploadPanel");
const actionsPanel = getElement<HTMLElement>("actionsPanel");
const uploadButton = getElement<HTMLButtonElement>("uploadButton");
const scanButton = getElement<HTMLButtonElement>("scanButton");
const generateButton = getElement<HTMLButtonElement>("generateButton");
const replaceButton = getElement<HTMLButtonElement>("replaceButton");
const clearButton = getElement<HTMLButtonElement>("clearButton");
const loadingText = getElement<HTMLParagraphElement>("loadingText");
const scanLoadingText = getElement<HTMLParagraphElement>("scanLoadingText");
const errorBlock = getElement<HTMLParagraphElement>("errorBlock");
const successBlock = getElement<HTMLElement>("successBlock");
const downloadButton = getElement<HTMLButtonElement>("downloadButton");
const previewPanel = getElement<HTMLElement>("previewPanel");
const debugPanel = getElement<HTMLElement>("debugPanel");
const debugOutput = getElement<HTMLPreElement>("debugOutput");
const jobTitleText = getElement<HTMLElement>("jobTitleText");
const companyText = getElement<HTMLElement>("companyText");
const locationText = getElement<HTMLElement>("locationText");
const sourceText = getElement<HTMLElement>("sourceText");
const confidenceText = getElement<HTMLElement>("confidenceText");
const textLengthText = getElement<HTMLElement>("textLengthText");
const jobTextPreview = getElement<HTMLTextAreaElement>("jobTextPreview");
const editButton = getElement<HTMLButtonElement>("editButton");

let latestResponse: GenerateResumeResponse | null = null;
let latestExtraction: ExtractedJobPage | null = null;

function getElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Missing popup element: ${id}`);
  }
  return element as T;
}

function setHidden(element: HTMLElement, hidden: boolean): void {
  element.classList.toggle("hidden", hidden);
}

function setError(message: string | null): void {
  errorBlock.textContent = message ?? "";
  setHidden(errorBlock, !message);
}

function setLoading(isLoading: boolean): void {
  setHidden(loadingText, !isLoading);
  generateButton.disabled = isLoading;
  scanButton.disabled = isLoading;
  replaceButton.disabled = isLoading;
  clearButton.disabled = isLoading;
}

function setScanning(isScanning: boolean): void {
  setHidden(scanLoadingText, !isScanning);
  scanButton.disabled = isScanning;
  generateButton.disabled = isScanning || !latestExtraction;
}

function displayValue(value: string | undefined): string {
  return value?.trim() || "Unknown";
}

async function refreshResumeState(): Promise<void> {
  const baseResume = await getBaseResume();
  const hasResume = Boolean(baseResume);

  resumeStatus.textContent = hasResume ? "Resume uploaded" : "No resume uploaded";
  setHidden(uploadPanel, hasResume);
  setHidden(actionsPanel, !hasResume);
}

async function openUploadPage(): Promise<void> {
  await chrome.tabs.create({
    url: chrome.runtime.getURL("src/upload/upload.html"),
  });
}

async function getActiveTabId(): Promise<number> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  if (!tab?.id) {
    throw new Error("Could not find the active tab.");
  }

  if (!tab.url || !/^https?:\/\//.test(tab.url)) {
    throw new Error("Open a public job page in the active tab before generating.");
  }

  return tab.id;
}

async function scanVacancy(): Promise<ExtractedJobPage> {
  const tabId = await getActiveTabId();

  const [runnerCheck] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () =>
      typeof (window as unknown as { __resumeTailorRunExtraction?: unknown })
        .__resumeTailorRunExtraction === "function",
  });

  if (!runnerCheck.result) {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["assets/extractJob.js"],
    });
  }

  const [result] = await chrome.scripting.executeScript({
    target: { tabId },
    func: async () => {
      const extractionWindow = window as unknown as {
        __resumeTailorLastExtraction?: ExtractedJobPage;
        __resumeTailorExtractionError?: string;
        __resumeTailorExtractionPromise?: Promise<void>;
        __resumeTailorRunExtraction?: () => Promise<void>;
      };

      await extractionWindow.__resumeTailorRunExtraction?.();
      await extractionWindow.__resumeTailorExtractionPromise;

      return {
        extraction: extractionWindow.__resumeTailorLastExtraction,
        error: extractionWindow.__resumeTailorExtractionError,
      };
    },
  });

  if (result.result?.error) {
    throw new Error(result.result.error);
  }

  if (!result.result?.extraction?.cleanedText) {
    throw new Error("Could not extract job text from the current page.");
  }

  return result.result.extraction;
}

async function generateTailoredResume(): Promise<void> {
  const baseResume = await getBaseResume();
  if (!baseResume) {
    throw new Error("Upload your base resume first.");
  }

  if (!latestExtraction) {
    throw new Error("Scan the vacancy before generating.");
  }

  const editedText = jobTextPreview.value.trim();
  if (editedText.length < 300) {
    throw new Error("Extracted job text is too short. Scan again or paste the job description manually.");
  }

  latestResponse = await generateResume({
    baseResume,
    jobPage: {
      url: latestExtraction.url,
      title: latestExtraction.detected.jobTitle || latestExtraction.pageTitle,
      text: editedText.slice(0, 50_000),
      detected: {
        jobTitle: latestExtraction.detected.jobTitle,
        company: latestExtraction.detected.company,
        location: latestExtraction.detected.location,
      },
    },
    options: {
      targetFormat: "docx",
      language: "en",
    },
  });
}

function renderExtraction(extraction: ExtractedJobPage): void {
  latestExtraction = extraction;
  jobTitleText.textContent = displayValue(extraction.detected.jobTitle);
  companyText.textContent = displayValue(extraction.detected.company);
  locationText.textContent = displayValue(extraction.detected.location);
  sourceText.textContent = extraction.source;
  confidenceText.textContent = `${Math.round(extraction.confidence * 100)}%`;
  textLengthText.textContent = extraction.cleanedText.length.toLocaleString();
  jobTextPreview.value = extraction.cleanedText;
  jobTextPreview.disabled = true;
  editButton.textContent = "Edit extracted text";
  generateButton.disabled = false;
  setHidden(previewPanel, false);
  setHidden(debugPanel, false);
  debugOutput.textContent = JSON.stringify(
    {
      source: extraction.source,
      confidence: extraction.confidence,
      jsonLdFound: extraction.debug.jsonLdFound,
      siteExtractor: extraction.debug.siteExtractor,
      textLength: extraction.debug.textLength,
      warnings: extraction.debug.warnings,
      candidateBlocks: extraction.debug.candidateBlocks,
    },
    null,
    2,
  );
}

async function downloadLatestResume(): Promise<void> {
  if (!latestResponse) {
    return;
  }

  const dataUrl = `data:${latestResponse.mimeType};base64,${latestResponse.base64}`;
  await chrome.downloads.download({
    url: dataUrl,
    filename: latestResponse.fileName,
    saveAs: true,
  });
}

uploadButton.addEventListener("click", async () => {
  try {
    setError(null);
    await openUploadPage();
  } catch (error) {
    setError(error instanceof Error ? error.message : "Could not open upload page.");
  }
});

replaceButton.addEventListener("click", async () => {
  try {
    setError(null);
    await openUploadPage();
  } catch (error) {
    setError(error instanceof Error ? error.message : "Could not open upload page.");
  }
});

clearButton.addEventListener("click", async () => {
  setError(null);
  latestResponse = null;
  latestExtraction = null;
  setHidden(successBlock, true);
  setHidden(previewPanel, true);
  setHidden(debugPanel, true);
  generateButton.disabled = true;
  await clearBaseResume();
  await refreshResumeState();
});

scanButton.addEventListener("click", async () => {
  setError(null);
  setHidden(successBlock, true);
  setScanning(true);

  try {
    const extraction = await scanVacancy();
    renderExtraction(extraction);
  } catch (error) {
    setError(error instanceof Error ? error.message : "Could not scan the vacancy.");
  } finally {
    setScanning(false);
  }
});

editButton.addEventListener("click", () => {
  jobTextPreview.disabled = !jobTextPreview.disabled;
  editButton.textContent = jobTextPreview.disabled ? "Edit extracted text" : "Lock edited text";
  if (!jobTextPreview.disabled) {
    jobTextPreview.focus();
  }
});

generateButton.addEventListener("click", async () => {
  setError(null);
  setHidden(successBlock, true);
  setLoading(true);

  try {
    await generateTailoredResume();
    setHidden(successBlock, false);
  } catch (error) {
    setError(error instanceof Error ? error.message : "Could not generate the resume.");
  } finally {
    setLoading(false);
  }
});

downloadButton.addEventListener("click", async () => {
  try {
    setError(null);
    await downloadLatestResume();
  } catch (error) {
    setError(error instanceof Error ? error.message : "Could not start the download.");
  }
});

void refreshResumeState();
