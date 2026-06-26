import mammoth from "mammoth/mammoth.browser";
import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
import pdfWorkerUrl from "pdfjs-dist/legacy/build/pdf.worker.mjs?url";
import { getApiBaseUrl } from "./storage";

const MIN_RESUME_LENGTH = 100;

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

type SupportedResumeExtension = "txt" | "md" | "pdf" | "doc" | "docx";

function normalizeText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function getExtension(fileName: string): SupportedResumeExtension | null {
  const extension = fileName.toLowerCase().split(".").pop();

  if (
    extension === "txt" ||
    extension === "md" ||
    extension === "pdf" ||
    extension === "doc" ||
    extension === "docx"
  ) {
    return extension;
  }

  return null;
}

function assertUsefulResumeText(text: string): string {
  const normalizedText = normalizeText(text);

  if (normalizedText.length < MIN_RESUME_LENGTH) {
    throw new Error(
      "Could not extract enough resume text from this file. Please try another file or export it as .txt.",
    );
  }

  return normalizedText;
}

async function parsePdfInBrowser(file: File): Promise<string> {
  const arrayBuffer = await file.arrayBuffer();
  const pdf = await pdfjs.getDocument({ data: arrayBuffer }).promise;
  const pageTexts: string[] = [];

  for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
    const page = await pdf.getPage(pageNumber);
    const textContent = await page.getTextContent();
    const text = textContent.items
      .map((item) => ("str" in item ? item.str : ""))
      .join(" ");

    pageTexts.push(text);
  }

  return assertUsefulResumeText(pageTexts.join("\n"));
}

async function parseDocxInBrowser(file: File): Promise<string> {
  const arrayBuffer = await file.arrayBuffer();
  const result = await mammoth.extractRawText({ arrayBuffer });
  return assertUsefulResumeText(result.value);
}

async function parseWithBackend(file: File): Promise<string> {
  const formData = new FormData();
  formData.append("file", file, file.name);
  const apiBaseUrl = await getApiBaseUrl();

  const response = await fetch(`${apiBaseUrl}/api/extract-resume-text`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let message = `Backend parser returned ${response.status}`;

    try {
      const body = await response.json() as { detail?: unknown };
      if (typeof body.detail === "string") {
        message = body.detail;
      }
    } catch {
      // Keep the status-based error if the response is not JSON.
    }

    throw new Error(message);
  }

  const body = await response.json() as { text?: unknown };
  if (typeof body.text !== "string") {
    throw new Error("Backend parser returned an invalid response.");
  }

  return assertUsefulResumeText(body.text);
}

export async function parseResumeFile(file: File): Promise<string> {
  const extension = getExtension(file.name);

  if (!extension) {
    throw new Error("Please upload a .txt, .md, .pdf, .doc, or .docx resume file.");
  }

  if (extension === "txt" || extension === "md") {
    return assertUsefulResumeText(await file.text());
  }

  if (extension === "pdf") {
    try {
      return await parsePdfInBrowser(file);
    } catch {
      return await parseWithBackend(file);
    }
  }

  if (extension === "docx") {
    try {
      return await parseDocxInBrowser(file);
    } catch {
      return await parseWithBackend(file);
    }
  }

  return await parseWithBackend(file);
}
