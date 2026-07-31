import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { api, type ProviderName, type ProviderSettings } from "../shared/apiClient";
import { isLocalUrlProvider, PROVIDERS, providerLabel } from "../shared/llmProviders";
import { DEFAULT_API_BASE_URL, getApiBaseUrl, normalizeApiBaseUrl, saveApiBaseUrl, saveOnboardingComplete } from "../shared/storage";
import { parseResumeFile } from "../shared/resumeParser";

type OnboardingStep = "backend" | "llm" | "resume";

type OnboardingViewProps = {
  onComplete: () => void;
};

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
  const [baseUrls, setBaseUrls] = useState<Record<string, string>>({});
  const [models, setModels] = useState<Record<string, string>>({});
  const [availableModels, setAvailableModels] = useState<Record<string, string[]>>({});
  const [loadingModels, setLoadingModels] = useState<Record<string, boolean>>({});
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
    setBaseUrls(Object.fromEntries(value.providers.map((item) => [item.provider, item.baseUrl ?? ""])));
    return value;
  };

  const loadModels = async (provider: ProviderName, apiKey?: string, baseUrl?: string) => {
    setLoadingModels((current) => ({ ...current, [provider]: true }));
    try {
      const result = await api.providerModels(provider, {
        apiKey: isLocalUrlProvider(provider) ? undefined : apiKey,
        baseUrl: isLocalUrlProvider(provider) ? baseUrl || undefined : undefined,
      });
      setAvailableModels((current) => ({ ...current, [provider]: result.models }));
    } catch {
      // Key/URL may still be incomplete or invalid; "Verify and save" surfaces the real error.
    } finally {
      setLoadingModels((current) => ({ ...current, [provider]: false }));
    }
  };

  useEffect(() => {
    const pending = PROVIDERS.filter(({ id, kind }) => kind === "apiKey" && (keys[id] ?? "").trim().length >= 8);
    if (!pending.length) return;
    const timer = window.setTimeout(() => {
      pending.forEach(({ id }) => void loadModels(id, keys[id].trim()));
    }, 500);
    return () => window.clearTimeout(timer);
  }, [keys]);

  useEffect(() => {
    const pending = PROVIDERS.filter(({ id, kind }) => {
      if (kind !== "localUrl") return false;
      const typed = (baseUrls[id] ?? "").trim();
      const saved = (settings?.providers.find((item) => item.provider === id)?.baseUrl ?? "").trim();
      return typed !== saved;
    });
    if (!pending.length) return;
    const timer = window.setTimeout(() => {
      pending.forEach(({ id }) => void loadModels(id, undefined, (baseUrls[id] ?? "").trim()));
    }, 500);
    return () => window.clearTimeout(timer);
  }, [baseUrls, settings]);

  const updateKey = (provider: ProviderName, apiKey: string) => {
    setKeys((current) => ({ ...current, [provider]: apiKey }));
    setAvailableModels((current) => {
      const next = { ...current };
      delete next[provider];
      return next;
    });
  };

  const updateBaseUrl = (provider: ProviderName, baseUrl: string) => {
    setBaseUrls((current) => ({ ...current, [provider]: baseUrl }));
    setAvailableModels((current) => {
      const next = { ...current };
      delete next[provider];
      return next;
    });
  };

  const advanceAfterBackend = async () => {
    const value = await loadProviderSettings();
    if (!value.providers.some((item) => item.isEnabled)) {
      setStep("llm");
      setMessage("Add and verify at least one LLM provider.");
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
    const local = isLocalUrlProvider(provider);
    const apiKey = (keys[provider] ?? "").trim();
    const baseUrl = (baseUrls[provider] ?? "").trim();
    if (!local && !apiKey) {
      setMessage(`Enter a ${providerLabel(provider)} key.`);
      return;
    }

    setBusy(`provider-${provider}`);
    setMessage(`Checking ${providerLabel(provider)}...`);
    try {
      const test = await api.testProvider(provider, {
        apiKey: local ? undefined : apiKey,
        baseUrl: local ? baseUrl || undefined : undefined,
        model: models[provider],
      });
      if (test.status !== "success") {
        throw new Error(test.details || test.message || "LLM connection failed.");
      }

      let modelList = availableModels[provider] ?? [];
      try {
        modelList = (await api.providerModels(provider, {
          apiKey: local ? undefined : apiKey,
          baseUrl: local ? baseUrl || undefined : undefined,
          refresh: true,
        })).models;
      } catch {
        modelList = test.model ? [test.model] : modelList;
      }

      const model = test.model || models[provider] || modelList[0] || "";
      await api.saveProvider(provider, {
        apiKey: local ? undefined : apiKey,
        baseUrl: local ? baseUrl : undefined,
        defaultModel: model,
        availableModels: modelList,
        testAfterSave: true,
      });
      await api.setDefaultProvider(provider, model);
      if (!local) setKeys((current) => ({ ...current, [provider]: "" }));
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
      setMessage("Connect at least one LLM provider.");
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
        <h2>Set up an LLM</h2>
        <p>At least one working provider is required. ResuMorph verifies the connection before moving on. Cloud keys are listed first; local Ollama is optional.</p>
        {PROVIDERS.map((provider) => {
          const config = settings?.providers.find((item) => item.provider === provider.id);
          const connection = providerConnection(config);
          const local = provider.kind === "localUrl";
          return <section className="onboarding-provider" key={provider.id}>
            <div>
              <strong>{local ? "Local (Ollama), no API key needed" : provider.label}</strong>
              <span className={`provider-connection ${connection.className}`} title={connection.label}><span className="provider-lamp" />{connection.label}</span>
            </div>
            {local ? <>
              <small>{config?.isEnabled
                ? (config.baseUrl ? `Saved URL: ${config.baseUrl}` : "Using env / default URL")
                : "Optional — fully local generation"}</small>
              <input
                type="url"
                value={baseUrls[provider.id] ?? ""}
                placeholder={provider.placeholder}
                onChange={(event) => updateBaseUrl(provider.id, event.target.value)}
                disabled={busy !== null}
                aria-label="Ollama base URL"
              />
              {config?.effectiveBaseUrl && <small className="muted">Requests go to {config.effectiveBaseUrl}</small>}
              <p className="muted">Local model quality is usually lower than cloud providers, especially on smaller models. Leave blank to use the backend default.</p>
            </> : <>
              <small>{config?.isEnabled ? config.keyMask : "No key saved"}</small>
              <input type="password" value={keys[provider.id] ?? ""} placeholder={provider.placeholder} onChange={(event) => updateKey(provider.id, event.target.value)} disabled={busy !== null} />
            </>}
            {loadingModels[provider.id] ? <p className="muted">Loading available models...</p> : availableModels[provider.id]?.length ? <select value={models[provider.id] ?? ""} onChange={(event) => setModels((current) => ({ ...current, [provider.id]: event.target.value }))} disabled={busy !== null}>
              <option value="">Choose model (default)</option>
              {availableModels[provider.id].map((model) => <option key={model} value={model}>{model}</option>)}
            </select> : <input value={models[provider.id] ?? ""} placeholder="Model, optional" onChange={(event) => setModels((current) => ({ ...current, [provider.id]: event.target.value }))} disabled={busy !== null} />}
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
