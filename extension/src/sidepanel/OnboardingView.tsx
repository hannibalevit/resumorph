import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { api, type ProviderName, type ProviderSettings } from "../shared/apiClient";
import { DEFAULT_API_BASE_URL, getApiBaseUrl, normalizeApiBaseUrl, saveApiBaseUrl, saveOnboardingComplete } from "../shared/storage";
import { parseResumeFile } from "../shared/resumeParser";

const PROVIDERS: Array<{ id: ProviderName; label: string; placeholder: string }> = [
  { id: "openai", label: "OpenAI", placeholder: "sk-..." },
  { id: "gemini", label: "Gemini", placeholder: "AIza..." },
  { id: "claude", label: "Claude", placeholder: "sk-ant-api03-..." },
];

type OnboardingStep = "backend" | "llm" | "resume";

type OnboardingViewProps = {
  onComplete: () => void;
};

function providerLabel(provider: ProviderName): string {
  return PROVIDERS.find((item) => item.id === provider)?.label ?? provider;
}

function ButtonSpinner() {
  return <span className="button-spinner" aria-hidden="true" />;
}

function providerConnection(config: ProviderSettings["providers"][number] | undefined): { className: string; label: string } {
  if (config?.lastTestStatus === "success") return { className: "connected", label: "Connected" };
  if (config?.lastTestStatus === "failed") return { className: "failed", label: "Failed" };
  if (config?.isEnabled) return { className: "configured", label: "Needs test" };
  return { className: "idle", label: "Not connected" };
}

export function OnboardingView({ onComplete }: OnboardingViewProps) {
  const [step, setStep] = useState<OnboardingStep>("backend");
  const [apiBaseUrl, setApiBaseUrl] = useState(DEFAULT_API_BASE_URL);
  const [settings, setSettings] = useState<ProviderSettings | null>(null);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [models, setModels] = useState<Record<string, string>>({});
  const [availableModels, setAvailableModels] = useState<Record<string, string[]>>({});
  const [resumeText, setResumeText] = useState("");
  const [message, setMessage] = useState("Checking the local backend...");
  const [busy, setBusy] = useState<string | null>("initial");

  const enabledProviders = useMemo(() => settings?.providers.filter((item) => item.isEnabled) ?? [], [settings]);
  const completedSteps = { backend: step !== "backend", llm: step === "resume", resume: false };

  const finish = async () => {
    await saveOnboardingComplete();
    onComplete();
  };

  const loadProviderSettings = async (): Promise<ProviderSettings> => {
    const value = await api.providers();
    setSettings(value);
    setModels(Object.fromEntries(value.providers.map((item) => [item.provider, item.defaultModel ?? ""])));
    setAvailableModels(Object.fromEntries(value.providers.map((item) => [item.provider, item.availableModels])));
    return value;
  };

  const advanceAfterBackend = async () => {
    const value = await loadProviderSettings();
    if (!value.providers.some((item) => item.isEnabled)) {
      setStep("llm");
      setMessage("Add and verify at least one LLM key.");
      return;
    }

    try {
      const resume = await api.getResume();
      setResumeText(resume.text);
      await finish();
    } catch {
      setStep("resume");
      setMessage("Add a base resume so ResuMorph can create tailored versions.");
    }
  };

  useEffect(() => {
    void (async () => {
      const savedUrl = await getApiBaseUrl();
      setApiBaseUrl(savedUrl);
      setBusy("backend");
      try {
        await api.health();
        setMessage("Backend connected.");
        await advanceAfterBackend();
      } catch {
        setStep("backend");
        setMessage("Backend is not responding. Start the server or enter another connection address.");
      } finally {
        setBusy(null);
      }
    })();
  }, []);

  const testBackend = async () => {
    setBusy("backend");
    setMessage("Checking backend...");
    try {
      const normalized = normalizeApiBaseUrl(apiBaseUrl);
      const parsed = new URL(normalized);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        throw new Error("Enter an HTTP or HTTPS address.");
      }
      const savedUrl = await saveApiBaseUrl(normalized);
      setApiBaseUrl(savedUrl);
      await api.health();
      setMessage("Backend connected.");
      await advanceAfterBackend();
    } catch (error) {
      setStep("backend");
      setMessage(error instanceof Error ? error.message : "Could not connect to the backend.");
    } finally {
      setBusy(null);
    }
  };

  const saveAndTestProvider = async (provider: ProviderName) => {
    const apiKey = (keys[provider] ?? "").trim();
    if (!apiKey) {
      setMessage(`Enter a ${providerLabel(provider)} key.`);
      return;
    }

    setBusy(`provider-${provider}`);
    setMessage(`Checking ${providerLabel(provider)}...`);
    try {
      const test = await api.testProvider(provider, apiKey, models[provider]);
      if (test.status !== "success") {
        throw new Error(test.details || test.message || "LLM connection failed.");
      }

      let modelList = availableModels[provider] ?? [];
      try {
        modelList = (await api.providerModels(provider, apiKey, true)).models;
      } catch {
        modelList = test.model ? [test.model] : modelList;
      }

      const model = test.model || models[provider] || modelList[0] || "";
      await api.saveProvider(provider, apiKey, model, modelList, true);
      await api.setDefaultProvider(provider, model);
      setKeys((current) => ({ ...current, [provider]: "" }));
      setMessage(`${providerLabel(provider)} connected.`);
      await loadProviderSettings();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Could not verify ${providerLabel(provider)}.`);
    } finally {
      setBusy(null);
    }
  };

  const continueToResume = async () => {
    if (!enabledProviders.length) {
      setMessage("Connect at least one LLM key.");
      return;
    }

    setBusy("resume-check");
    try {
      await api.getResume();
      await finish();
    } catch {
      setStep("resume");
      setMessage("Add a base resume.");
    } finally {
      setBusy(null);
    }
  };

  const uploadResume = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setBusy("resume");
    setMessage(`Reading ${file.name}...`);
    try {
      const text = await parseResumeFile(file);
      await api.saveResume(text);
      setResumeText(text);
      setMessage("Base resume saved.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save the resume.");
    } finally {
      setBusy(null);
      event.target.value = "";
    }
  };

  const completeResumeStep = async () => {
    if (!resumeText.trim()) {
      setMessage("Add a base resume first.");
      return;
    }
    await finish();
  };

  return <main className="panel onboarding-shell">
    <section className="onboarding-card" aria-label="First setup">
      <div className="onboarding-brand">
        <img src="/icons/icon-48.png" alt="" />
        <div>
          <p>ResuMorph</p>
          <h1>{step === "backend" ? "Extension setup" : step === "llm" ? "Connect an LLM" : "Base resume"}</h1>
        </div>
      </div>

      <nav className="onboarding-steps" aria-label="Setup progress">
        <span className={step === "backend" ? "active" : completedSteps.backend ? "done" : ""}>1</span>
        <span className={step === "llm" ? "active" : completedSteps.llm ? "done" : ""}>2</span>
        <span className={step === "resume" ? "active" : ""}>3</span>
      </nav>

      {step === "backend" && <section className="onboarding-step">
        <h2>Checking the backend</h2>
        <p>ResuMorph connects to the local server at the default address. If your server runs somewhere else, enter that address here.</p>
        <label>
          Backend URL
          <input value={apiBaseUrl} onChange={(event) => setApiBaseUrl(event.target.value)} placeholder={DEFAULT_API_BASE_URL} disabled={busy !== null} />
        </label>
        <div className="onboarding-actions">
          <button className="primary" onClick={() => void testBackend()} disabled={busy !== null}>{(busy === "backend" || busy === "initial") && <ButtonSpinner />}{busy === "backend" || busy === "initial" ? "Checking..." : "Connect"}</button>
        </div>
      </section>}

      {step === "llm" && <section className="onboarding-step">
        <h2>Set up an LLM key</h2>
        <p>At least one working key is required. ResuMorph verifies the connection before moving on.</p>
        {PROVIDERS.map((provider) => {
          const config = settings?.providers.find((item) => item.provider === provider.id);
          const connection = providerConnection(config);
          return <section className="onboarding-provider" key={provider.id}>
            <div>
              <strong>{provider.label}</strong>
              <span className={`provider-connection ${connection.className}`} title={connection.label}><span className="provider-lamp" />{connection.label}</span>
            </div>
            <small>{config?.isEnabled ? config.keyMask : "No key saved"}</small>
            <input type="password" value={keys[provider.id] ?? ""} placeholder={provider.placeholder} onChange={(event) => setKeys((current) => ({ ...current, [provider.id]: event.target.value }))} disabled={busy !== null} />
            <input value={models[provider.id] ?? ""} placeholder="Model, optional" onChange={(event) => setModels((current) => ({ ...current, [provider.id]: event.target.value }))} disabled={busy !== null} />
            <button className="secondary" onClick={() => void saveAndTestProvider(provider.id)} disabled={busy !== null}>{busy === `provider-${provider.id}` && <ButtonSpinner />}{busy === `provider-${provider.id}` ? "Checking..." : "Verify and save"}</button>
          </section>;
        })}
        <div className="onboarding-actions">
          <button className="primary" onClick={() => void continueToResume()} disabled={busy !== null || !enabledProviders.length}>{busy === "resume-check" && <ButtonSpinner />}{busy === "resume-check" ? "Checking..." : "Continue"}</button>
        </div>
      </section>}

      {step === "resume" && <section className="onboarding-step">
        <h2>Add your base resume</h2>
        <p>This is the source version used to create tailored resumes for specific jobs.</p>
        <label className={`secondary upload-control ${busy === "resume" ? "disabled" : ""}`}>
          {busy === "resume" && <ButtonSpinner />}{busy === "resume" ? "Uploading..." : resumeText ? "Replace resume" : "Choose file"}
          <input type="file" accept=".txt,.md,.pdf,.doc,.docx" onChange={(event) => void uploadResume(event)} disabled={busy !== null} />
        </label>
        {resumeText && <textarea className="resume-preview onboarding-resume-preview" readOnly value={resumeText} aria-label="Base resume preview" />}
        <div className="onboarding-actions">
          <button className="primary" onClick={() => void completeResumeStep()} disabled={busy !== null || !resumeText.trim()}>Finish setup</button>
        </div>
      </section>}

      <p className="status" role="status">{message}</p>
    </section>
  </main>;
}
