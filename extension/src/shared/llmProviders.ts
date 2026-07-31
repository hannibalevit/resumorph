import type { ProviderName } from "./apiClient";

export type ProviderKind = "apiKey" | "localUrl";

export type ProviderOption = {
  id: ProviderName;
  label: string;
  kind: ProviderKind;
  placeholder: string;
};

/** Cloud keys first; Ollama last so it is never the first-impression default. */
export const PROVIDERS: ProviderOption[] = [
  { id: "openai", label: "OpenAI", kind: "apiKey", placeholder: "sk-..." },
  { id: "gemini", label: "Gemini", kind: "apiKey", placeholder: "AIza..." },
  { id: "claude", label: "Claude", kind: "apiKey", placeholder: "sk-ant-api03-..." },
  { id: "ollama", label: "Ollama (local)", kind: "localUrl", placeholder: "http://localhost:11434" },
];

export function providerLabel(provider: ProviderName): string {
  return PROVIDERS.find((item) => item.id === provider)?.label ?? provider;
}

export function isLocalUrlProvider(provider: ProviderName): boolean {
  return PROVIDERS.find((item) => item.id === provider)?.kind === "localUrl";
}
