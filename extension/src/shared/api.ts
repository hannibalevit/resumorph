import type { GenerateResumeRequest, GenerateResumeResponse } from "./types";
import { getApiBaseUrl } from "./storage";

export async function generateResume(
  payload: GenerateResumeRequest,
): Promise<GenerateResumeResponse> {
  const apiBaseUrl = await getApiBaseUrl();
  const response = await fetch(`${apiBaseUrl}/api/generate-resume`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let message = `Backend returned ${response.status}`;

    try {
      const errorBody = await response.json() as { detail?: unknown };
      if (typeof errorBody.detail === "string") {
        message = errorBody.detail;
      }
    } catch {
      // Keep the status-based error if the response is not JSON.
    }

    throw new Error(message);
  }

  return await response.json() as GenerateResumeResponse;
}
