import { ChangeEvent, useEffect, useState } from "react";
import { api, type LlmTaskName, type ProviderConfig, type ProviderName, type ProviderSettings } from "../shared/apiClient";

const PROVIDERS: Array<{ id: ProviderName; label: string; placeholder: string; helpText?: string }> = [
  { id: "openai", label: "OpenAI", placeholder: "sk-..." },
  { id: "gemini", label: "Gemini", placeholder: "AIza..." },
  {
    id: "claude",
    label: "Claude",
    placeholder: "sk-ant-api03-... or sk-ant-oat01-...",
    helpText:
      "Paste either a regular Anthropic API key (sk-ant-api03-...) or a Claude Pro/Max subscription OAuth token (sk-ant-oat01-..., generated on your machine with `claude setup-token`). The backend detects which one you pasted automatically.",
  },
];

const TASKS: Array<{ id: LlmTaskName; label: string; description: string }> = [
  { id: "scan", label: "Page scanning", description: "Extracts the vacancy context from the current page." },
  { id: "resume", label: "Resume generation", description: "Creates or updates the tailored resume from saved vacancy context." },
  { id: "field_answer", label: "Application form answers", description: "Generates answers for textarea/application questions." },
];

type SettingsViewProps = {
  onResumeSaved?: () => void;
};

function ButtonSpinner() {
  return <span className="button-spinner" aria-hidden="true" />;
}

function providerConnection(config: ProviderConfig | undefined): { className: string; label: string } {
  if (config?.lastTestStatus === "success") return { className: "connected", label: "Connected" };
  if (config?.lastTestStatus === "failed") return { className: "failed", label: "Failed" };
  if (config?.isEnabled) return { className: "configured", label: "Needs test" };
  return { className: "idle", label: "Not connected" };
}

export function SettingsView({ onResumeSaved }: SettingsViewProps) {
  const [activeTab, setActiveTab] = useState<"resume" | "llm" | "tasks">("resume");
  const [settings, setSettings] = useState<ProviderSettings | null>(null);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [models, setModels] = useState<Record<string, string>>({});
  const [availableModels, setAvailableModels] = useState<Record<string, string[]>>({});
  const [loadingModels, setLoadingModels] = useState<Record<string, boolean>>({});
  const [resumePresent, setResumePresent] = useState(false);
  const [resumeText, setResumeText] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const load = async () => {
    try {
      const value = await api.providers();
      setSettings(value);
      // Test connection works on a key the user hasn't saved yet, so the
      // backend has no persisted config (and no availableModels/defaultModel)
      // to return for it — keep whatever was already fetched client-side
      // (e.g. via the live-typing model lookup) instead of clobbering it.
      setModels((prev) => Object.fromEntries(value.providers.map((item) => [item.provider, item.defaultModel ?? prev[item.provider] ?? ""])));
      setAvailableModels((prev) => Object.fromEntries(value.providers.map((item) => [item.provider, item.availableModels.length ? item.availableModels : (prev[item.provider] ?? [])])));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load settings.");
    }
  };

  const loadResumeState = async () => {
    try {
      const resume = await api.getResume();
      setResumePresent(true);
      setResumeText(resume.text);
    } catch {
      setResumePresent(false);
      setResumeText("");
    }
  };

  useEffect(() => {
    void load();
    void loadResumeState();
  }, []);

  const config = (provider: ProviderName): ProviderConfig | undefined => settings?.providers.find((item) => item.provider === provider);

  const loadModels = async (provider: ProviderName, apiKey?: string, refresh = false) => {
    if (!apiKey && !config(provider)?.isEnabled) return;
    setLoadingModels((value) => ({ ...value, [provider]: true }));
    try {
      const result = await api.providerModels(provider, apiKey, refresh);
      setAvailableModels((value) => ({ ...value, [provider]: result.models }));
      setMessage(`${result.models.length} text-generation models loaded for ${provider}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load models.");
    } finally {
      setLoadingModels((value) => ({ ...value, [provider]: false }));
    }
  };

  useEffect(() => {
    const pending = PROVIDERS.filter(({ id }) => (keys[id] ?? "").trim().length >= 8);
    if (!pending.length) return;
    const timer = window.setTimeout(() => {
      pending.forEach(({ id }) => void loadModels(id, keys[id].trim()));
    }, 500);
    return () => window.clearTimeout(timer);
  }, [keys]);

  const updateKey = (provider: ProviderName, apiKey: string) => {
    setKeys((value) => ({ ...value, [provider]: apiKey }));
    setAvailableModels((value) => {
      const next = { ...value };
      delete next[provider];
      return next;
    });
  };

  const uploadResume = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy("resume");
    setMessage("Reading base resume…");
    try {
      let text: string;
      if (/\.(txt|md)$/i.test(file.name)) text = await file.text();
      else {
        text = (await api.extractResumeText(file)).text;
      }
      await api.saveResume(text);
      setResumePresent(true);
      setResumeText(text);
      onResumeSaved?.();
      setMessage("Base resume saved securely on the local backend.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not upload the base resume.");
    } finally {
      setBusy(null);
      event.target.value = "";
    }
  };

  const save = async (provider: ProviderName) => {
    if (!keys[provider]) {
      setMessage("Enter an API key before saving.");
      return;
    }
    setBusy(`save-${provider}`);
    try {
      const saved = await api.saveProvider(provider, keys[provider], models[provider] || "", availableModels[provider] ?? [], true);
      setKeys((value) => ({ ...value, [provider]: "" }));
      setMessage(saved.lastTestStatus === "failed"
        ? `${provider} key saved, but the connection test failed${saved.lastTestError ? `: ${saved.lastTestError}` : "."}`
        : `${provider} key saved and connection verified.`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save provider.");
    } finally {
      setBusy(null);
    }
  };

  const saveModel = async (provider: ProviderName) => {
    const model = (models[provider] ?? "").trim();
    if (!model) {
      setMessage("Choose or enter a model before saving.");
      return;
    }
    setBusy(`model-${provider}`);
    try {
      await api.saveProviderModel(provider, model, availableModels[provider] ?? []);
      setMessage(`${provider} model saved.`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save model.");
    } finally {
      setBusy(null);
    }
  };

  const changeModel = async (provider: ProviderName, model: string) => {
    setModels((value) => ({ ...value, [provider]: model }));
    if (!config(provider)?.isEnabled || !model.trim()) return;
    setBusy(`model-${provider}`);
    try {
      await api.saveProviderModel(provider, model.trim(), availableModels[provider] ?? []);
      setMessage(`${provider} model changed to ${model.trim()}.`);
      const value = await api.providers();
      setSettings(value);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save model.");
    } finally {
      setBusy(null);
    }
  };

  const test = async (provider: ProviderName) => {
    setBusy(`test-${provider}`);
    try {
      const result = await api.testProvider(provider, keys[provider], models[provider]);
      setMessage(`${provider}: ${result.message} (${result.latencyMs} ms)${result.details ? ` — ${result.details}` : ""}`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Connection test failed.");
    } finally {
      setBusy(null);
    }
  };

  const enabledProviders = settings?.providers.filter((item) => item.isEnabled) ?? [];
  const defaultProvider = settings?.defaultProvider;
  const defaultModels = defaultProvider ? availableModels[defaultProvider] ?? [] : [];
  const saveDefault = async () => {
    if (!defaultProvider || !settings?.defaultModel) return;
    setBusy("default-model");
    try {
      const value = await api.setDefaultProvider(defaultProvider, settings.defaultModel);
      setSettings(value);
      setMessage("Default LLM updated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not set default.");
    } finally {
      setBusy(null);
    }
  };

  const changeDefaultModel = async (model: string) => {
    if (!defaultProvider || !model) {
      setSettings((current) => current ? { ...current, defaultModel: model } : current);
      return;
    }
    setSettings((current) => current ? { ...current, defaultModel: model } : current);
    setBusy("default-model");
    try {
      const value = await api.setDefaultProvider(defaultProvider, model);
      setSettings(value);
      setMessage(`Default LLM changed to ${defaultProvider} / ${model}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not set default.");
    } finally {
      setBusy(null);
    }
  };

  const providerLabel = (provider: ProviderName): string => PROVIDERS.find((item) => item.id === provider)?.label ?? provider;

  const setTaskProvider = async (task: LlmTaskName, provider: ProviderName) => {
    const model = availableModels[provider]?.includes(settings?.taskSettings?.[task]?.model ?? "")
      ? settings?.taskSettings?.[task]?.model
      : config(provider)?.defaultModel || availableModels[provider]?.[0] || "";
    if (!model) {
      setMessage(`Choose a model for ${providerLabel(provider)} first.`);
      return;
    }
    setBusy(`task-${task}`);
    try {
      const value = await api.setTaskProvider(task, provider, model);
      setSettings(value);
      setMessage(`${TASKS.find((item) => item.id === task)?.label} now uses ${providerLabel(provider)} / ${model}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update task LLM.");
    } finally {
      setBusy(null);
    }
  };

  const setTaskModel = async (task: LlmTaskName, model: string) => {
    const provider = settings?.taskSettings?.[task]?.provider;
    if (!provider || !model) return;
    setBusy(`task-${task}`);
    try {
      const value = await api.setTaskProvider(task, provider, model);
      setSettings(value);
      setMessage(`${TASKS.find((item) => item.id === task)?.label} model changed to ${model}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update task model.");
    } finally {
      setBusy(null);
    }
  };

  const clearTaskProvider = async (task: LlmTaskName) => {
    setBusy(`task-${task}`);
    try {
      const value = await api.clearTaskProvider(task);
      setSettings(value);
      setMessage(`${TASKS.find((item) => item.id === task)?.label} now uses the default LLM.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not reset task LLM.");
    } finally {
      setBusy(null);
    }
  };

  const deleteProvider = async (provider: ProviderName) => {
    setBusy(`delete-${provider}`);
    try {
      await api.deleteProvider(provider);
      await load();
      setMessage(`${providerLabel(provider)} key cleared.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not clear provider key.");
    } finally {
      setBusy(null);
    }
  };

  return <section className="settings-view">
    <div className="view-heading"><h2>Settings</h2></div>
    <nav className="settings-tabs" aria-label="Settings sections">
      <button className={activeTab === "resume" ? "active" : ""} onClick={() => setActiveTab("resume")}>Base resume</button>
      <button className={activeTab === "llm" ? "active" : ""} onClick={() => setActiveTab("llm")}>LLM models</button>
      <button className={activeTab === "tasks" ? "active" : ""} onClick={() => setActiveTab("tasks")}>Task routing</button>
    </nav>

    {activeTab === "resume" ? <section className="settings-panel">
      <h3>Base resume</h3>
      <p className="muted">{resumePresent ? "A base resume is saved on the local backend." : "No base resume is saved yet."}</p>
      <label className={`secondary upload-control ${busy === "resume" ? "disabled" : ""}`}>
        {busy === "resume" && <ButtonSpinner />}{busy === "resume" ? "Uploading..." : resumePresent ? "Replace base resume" : "Upload base resume"}
        <input type="file" accept=".txt,.md,.pdf,.doc,.docx" onChange={(event) => void uploadResume(event)} disabled={busy !== null} />
      </label>
      {resumeText && <textarea className="resume-preview" readOnly value={resumeText} aria-label="Base resume text" />}
    </section> : activeTab === "llm" ? <section className="settings-panel">
      <p className="muted">Keys are encrypted on the local backend. They are never stored in this extension.</p>

      {PROVIDERS.map((provider) => {
        const providerConfig = config(provider.id);
        const connection = providerConnection(providerConfig);
        return <section className="provider-card" key={provider.id}>
        <div className="provider-heading">
          <h3>{provider.label}</h3>
          <span className={`provider-connection ${connection.className}`} title={connection.label}><span className="provider-lamp" />{connection.label}</span>
        </div>
        <small>
          {providerConfig?.keyMask ?? "No key saved"}
          {providerConfig?.authMode === "subscription" ? " · Claude subscription (OAuth)" : providerConfig?.authMode === "api_key" ? " · API key" : ""}
        </small>
        {provider.helpText && <p className="muted provider-help">{provider.helpText}</p>}
        <input type="password" placeholder={provider.placeholder} value={keys[provider.id] ?? ""} onChange={(event) => updateKey(provider.id, event.target.value)} />
        {loadingModels[provider.id] ? <p className="muted">Loading available models…</p> : availableModels[provider.id]?.length ? <select value={models[provider.id] ?? ""} onChange={(event) => void changeModel(provider.id, event.target.value)} disabled={busy !== null}>
          <option value="">Choose model</option>
          {availableModels[provider.id].map((model) => <option key={model} value={model}>{model}</option>)}
        </select> : <input placeholder="Model" value={models[provider.id] ?? ""} onChange={(event) => setModels((value) => ({ ...value, [provider.id]: event.target.value }))} />}
        <div className="actions">
          <button className="primary" onClick={() => void save(provider.id)} disabled={busy !== null}>{busy === `save-${provider.id}` && <ButtonSpinner />}{busy === `save-${provider.id}` ? "Saving..." : "Save key"}</button>
          {providerConfig?.isEnabled && <button className="secondary" onClick={() => void saveModel(provider.id)} disabled={busy !== null || !(models[provider.id] ?? "").trim()}>{busy === `model-${provider.id}` && <ButtonSpinner />}{busy === `model-${provider.id}` ? "Saving..." : "Save model"}</button>}
          <button className="secondary" onClick={() => void test(provider.id)} disabled={busy !== null}>{busy === `test-${provider.id}` && <ButtonSpinner />}{busy === `test-${provider.id}` ? "Testing..." : "Test connection"}</button>
          {providerConfig?.isEnabled && <button className="secondary" onClick={() => void loadModels(provider.id, undefined, true)} disabled={busy !== null || loadingModels[provider.id]}>{loadingModels[provider.id] && <ButtonSpinner />}{loadingModels[provider.id] ? "Loading..." : "Reload models"}</button>}
          {providerConfig?.isEnabled && <button className="danger" onClick={() => void deleteProvider(provider.id)} disabled={busy !== null}>{busy === `delete-${provider.id}` && <ButtonSpinner />}{busy === `delete-${provider.id}` ? "Clearing..." : "Clear key"}</button>}
        </div>
      </section>;
      })}

      <section className="provider-card">
        <h3>Default LLM</h3>
        <select value={defaultProvider ?? ""} onChange={(event) => setSettings((current) => current ? { ...current, defaultProvider: event.target.value as ProviderName, defaultModel: "" } : current)}>
          <option value="">Choose provider</option>
          {enabledProviders.map((item) => <option key={item.provider} value={item.provider}>{PROVIDERS.find((provider) => provider.id === item.provider)?.label}</option>)}
        </select>
        <select value={settings?.defaultModel ?? ""} disabled={!defaultProvider || !defaultModels.length || busy !== null} onChange={(event) => void changeDefaultModel(event.target.value)}>
          <option value="">{defaultProvider && !defaultModels.length ? "No cached models — use Reload models" : "Choose model"}</option>
          {defaultModels.map((model) => <option key={model} value={model}>{model}</option>)}
        </select>
        <button className="primary" disabled={!defaultProvider || !settings?.defaultModel || busy !== null} onClick={() => void saveDefault()}>{busy === "default-model" && <ButtonSpinner />}{busy === "default-model" ? "Saving..." : "Save default"}</button>
      </section>
    </section> : <section className="settings-panel">
      <p className="muted">Each task uses the default LLM until you choose a custom configured provider and model here. Vacancy context is saved after scanning, so resume generation can switch providers later without losing context.</p>
      {TASKS.map((task) => {
        const taskSetting = settings?.taskSettings?.[task.id];
        const provider = taskSetting?.provider;
        const modelsForProvider = provider ? availableModels[provider] ?? [] : [];
        return <section className="provider-card" key={task.id}>
          <div className="provider-heading">
            <h3>{task.label}</h3>
            <span className="provider-status success">{taskSetting?.isCustom ? "custom" : "default"}</span>
          </div>
          <p className="muted">{task.description}</p>
          <select value={provider ?? ""} disabled={busy !== null || enabledProviders.length === 0} onChange={(event) => void setTaskProvider(task.id, event.target.value as ProviderName)}>
            <option value="">{enabledProviders.length ? "Choose configured LLM" : "No configured LLM keys"}</option>
            {enabledProviders.map((item) => <option key={item.provider} value={item.provider}>{providerLabel(item.provider)}</option>)}
          </select>
          <select value={taskSetting?.model ?? ""} disabled={busy !== null || !provider || modelsForProvider.length === 0} onChange={(event) => void setTaskModel(task.id, event.target.value)}>
            <option value="">{provider && !modelsForProvider.length ? "No cached models — reload in LLM models" : "Choose model"}</option>
            {modelsForProvider.map((model) => <option key={model} value={model}>{model}</option>)}
          </select>
          {taskSetting?.isCustom && <button className="secondary compact" disabled={busy !== null} onClick={() => void clearTaskProvider(task.id)}>{busy === `task-${task.id}` && <ButtonSpinner />}{busy === `task-${task.id}` ? "Saving..." : "Use default"}</button>}
          {taskSetting && <small>{providerLabel(taskSetting.provider)} · {taskSetting.model}</small>}
        </section>;
      })}
    </section>}

    <p className="status">{message}</p>
  </section>;
}
