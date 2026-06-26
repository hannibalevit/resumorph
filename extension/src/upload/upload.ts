import "./upload.css";
import { parseResumeFile } from "../shared/resumeParser";
import { saveBaseResume } from "../shared/storage";

const resumeFile = getElement<HTMLInputElement>("resumeFile");
const statusText = getElement<HTMLParagraphElement>("statusText");
const errorBlock = getElement<HTMLParagraphElement>("errorBlock");
const successBlock = getElement<HTMLElement>("successBlock");

function getElement<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Missing upload element: ${id}`);
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

function setSuccess(isVisible: boolean): void {
  setHidden(successBlock, !isVisible);
}

resumeFile.addEventListener("change", async () => {
  const file = resumeFile.files?.[0];
  if (!file) {
    return;
  }

  try {
    setError(null);
    setSuccess(false);
    statusText.textContent = `Reading ${file.name}…`;

    const text = await parseResumeFile(file);
    await saveBaseResume(text);

    statusText.textContent = `Saved ${file.name}. Extracted ${text.length.toLocaleString()} characters.`;
    setSuccess(true);
  } catch (error) {
    statusText.textContent = "Choose a resume file to store locally in Chrome.";
    setError(error instanceof Error ? error.message : "Could not upload resume.");
  } finally {
    resumeFile.value = "";
  }
});
