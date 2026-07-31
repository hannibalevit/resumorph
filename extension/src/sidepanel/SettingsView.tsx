import { ChangeEvent, useEffect, useState } from "react";
import { api, type LlmTaskName, type ProviderConfig, type ProviderName, type ProviderSettings } from "../shared/apiClient";
import { isLocalUrlProvider, PROVIDERS, providerLabel } from "../shared/llmProviders";
import { getThemePreference, isDebugInfoEnabled, saveDebugInfoEnabled, saveThemePreference, type ThemePreference } from "../shared/storage";

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
  const [activeTab, setActiveTab] = useState<"resume" | "llm" | "tasks" | "general">("general");
  const [theme, setTheme] = useState<ThemePreference>("light");
  const [debugInfoEnabled, setDebugInfoEnabled] = useState(false);
  const [settings, setSettings] = useState<ProviderSettings | null>(null);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [baseUrls, setBaseUrls] = useState<Record<string, string>>({});
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
      // Saved baseUrl only — never put effectiveBaseUrl in the input (that would bake env into the DB on save).
      setBaseUrls((prev) => Object.fromEntries(value.providers.map((item) => [item.provider, item.baseUrl ?? prev[item.provider] ?? ""])));
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
    void getThemePreference().then(setTheme).catch(() => undefined);
    void isDebugInfoEnabled().then(setDebugInfoEnabled).catch(() => undefined);
  }, []);

  const changeTheme = async (next: ThemePreference) => {
    setTheme(next);
    await saveThemePreference(next);
  };

  const changeDebugInfoEnabled = async (enabled: boolean) => {
    setDebugInfoEnabled(enabled);
    await saveDebugInfoEnabled(enabled);
  };

  const config = (provider: ProviderName): ProviderConfig | undefined => settings?.providers.find((item) => item.provider === provider);

  const typedBaseUrl = (provider: ProviderName): string | undefined => {
    const value = (baseUrls[provider] ?? "").trim();
    return value || undefined;
  };

  const loadModels = async (provider: ProviderName, apiKey?: string, refresh = false) => {
    const local = isLocalUrlProvider(provider);
    if (!local && !apiKey && !config(provider)?.isEnabled) return;
    setLoadingModels((value) => ({ ...value, [provider]: true }));
    try {
      const result = await api.providerModels(provider, {
        apiKey: local ? undefined : apiKey,
        baseUrl: local ? typedBaseUrl(provider) : undefined,
        refresh,
      });
      setAvailableModels((value) => ({ ...value, [provider]: result.models }));
      setMessage(`${result.models.length} text-generation models loaded for ${providerLabel(provider)}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load models.");
    } finally {
      setLoadingModels((value) => ({ ...value, [provider]: false }));
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
    // Only probe when the user is editing a local URL (not when load() mirrors saved values).
    const pending = PROVIDERS.filter(({ id, kind }) => {
      if (kind !== "localUrl") return false;
      const typed = (baseUrls[id] ?? "").trim();
      const saved = (settings?.providers.find((item) => item.provider === id)?.baseUrl ?? "").trim();
      return typed !== saved;
    });
    if (!pending.length) return;
    const timer = window.setTimeout(() => {
      pending.forEach(({ id }) => void loadModels(id));
    }, 500);
    return () => window.clearTimeout(timer);
  }, [baseUrls, settings]);

  const updateKey = (provider: ProviderName, apiKey: string) => {
    setKeys((value) => ({ ...value, [provider]: apiKey }));
    setAvailableModels((value) => {
      const next = { ...value };
      delete next[provider];
      return next;
    });
  };

  const updateBaseUrl = (provider: ProviderName, baseUrl: string) => {
    setBaseUrls((value) => ({ ...value, [provider]: baseUrl }));
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
    const local = isLocalUrlProvider(provider);
    if (!local && !keys[provider]) {
      setMessage("Enter an API key before saving.");
      return;
    }
    setBusy(`save-${provider}`);
    try {
      const saved = await api.saveProvider(provider, {
        apiKey: local ? undefined : keys[provider],
        // Always send for localUrl so "" clears a previously saved URL.
        baseUrl: local ? (baseUrls[provider] ?? "").trim() : undefined,
        defaultModel: models[provider] || "",
        availableModels: availableModels[provider] ?? [],
        testAfterSave: true,
      });
      if (!local) setKeys((value) => ({ ...value, [provider]: "" }));
      setMessage(saved.lastTestStatus === "failed"
        ? `${providerLabel(provider)} saved, but the connection test failed${saved.lastTestError ? `: ${saved.lastTestError}` : "."}`
        : `${providerLabel(provider)} saved and connection verified.`);
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
      setMessage(`${providerLabel(provider)} model saved.`);
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
      setMessage(`${providerLabel(provider)} model changed to ${model.trim()}.`);
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
      const local = isLocalUrlProvider(provider);
      const result = await api.testProvider(provider, {
        apiKey: local ? undefined : keys[provider],
        baseUrl: local ? typedBaseUrl(provider) : undefined,
        model: models[provider],
      });
      setMessage(`${providerLabel(provider)}: ${result.message} (${result.latencyMs} ms)${result.details ? ` — ${result.details}` : ""}`);
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
      setMessage(`Default LLM changed to ${providerLabel(defaultProvider)} / ${model}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not set default.");
    } finally {
      setBusy(null);
    }
  };

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
      setMessage(isLocalUrlProvider(provider)
        ? `${providerLabel(provider)} configuration cleared.`
        : `${providerLabel(provider)} key cleared.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not clear provider.");
    } finally {
      setBusy(null);
    }
  };

  return <section className="settings-view">
    <div className="view-heading"><h2>Settings</h2></div>
    <nav className="settings-tabs" aria-label="Settings sections">
      <button className={activeTab === "general" ? "active" : ""} onClick={() => setActiveTab("general")}>General</button>
      <button className={activeTab === "resume" ? "active" : ""} onClick={() => setActiveTab("resume")}>Base resume</button>
      <button className={activeTab === "llm" ? "active" : ""} onClick={() => setActiveTab("llm")}>LLM models</button>
      <button className={activeTab === "tasks" ? "active" : ""} onClick={() => setActiveTab("tasks")}>Task routing</button>
    </nav>

    {activeTab === "general" ? <section className="settings-panel">
      <div className="toggle-row">
        <div>
          <h3>Dark theme</h3>
          <p className="muted">Switch the extension between light and dark appearance.</p>
        </div>
        <label className="toggle-switch">
          <input type="checkbox" checked={theme === "dark"} onChange={(event) => void changeTheme(event.target.checked ? "dark" : "light")} aria-label="Toggle dark theme" />
          <span className="toggle-slider" aria-hidden="true" />
        </label>
      </div>
      <div className="toggle-row">
        <div>
          <h3>Debug information</h3>
          <p className="muted">Show the technical debug details section on the job tab.</p>
        </div>
        <label className="toggle-switch">
          <input type="checkbox" checked={debugInfoEnabled} onChange={(event) => void changeDebugInfoEnabled(event.target.checked)} aria-label="Toggle debug information" />
          <span className="toggle-slider" aria-hidden="true" />
        </label>
      </div>
    </section> : activeTab === "resume" ? <section className="settings-panel">
      <h3>Base resume</h3>
      <p className="muted">{resumePresent ? "A base resume is saved on the local backend." : "No base resume is saved yet."}</p>
      <label className={`secondary upload-control ${busy === "resume" ? "disabled" : ""}`}>
        {busy === "resume" && <ButtonSpinner />}{busy === "resume" ? "Uploading..." : resumePresent ? "Replace base resume" : "Upload base resume"}
        <input type="file" accept=".txt,.md,.pdf,.doc,.docx" onChange={(event) => void uploadResume(event)} disabled={busy !== null} />
      </label>
      {resumeText && <textarea className="resume-preview" readOnly value={resumeText} aria-label="Base resume text" />}
    </section> : activeTab === "llm" ? <section className="settings-panel">
      <p className="muted">Cloud keys are encrypted on the local backend. They are never stored in this extension. Ollama uses a base URL instead of a key.</p>

      {PROVIDERS.map((provider) => {
        const providerConfig = config(provider.id);
        const connection = providerConnection(providerConfig);
        const local = provider.kind === "localUrl";
        return <section className="provider-card" key={provider.id}>
        <div className="provider-heading">
          <h3>{provider.label}</h3>
          <span className={`provider-connection ${connection.className}`} title={connection.label}><span className="provider-lamp" />{connection.label}</span>
        </div>
        {local ? <>
          <small>{providerConfig?.isEnabled
            ? (providerConfig.baseUrl ? `Saved URL: ${providerConfig.baseUrl}` : "Using env / default URL (nothing saved)")
            : "No Ollama endpoint saved"}</small>
          <input
            type="url"
            placeholder={provider.placeholder}
            value={baseUrls[provider.id] ?? ""}
            onChange={(event) => updateBaseUrl(provider.id, event.target.value)}
            aria-label={`${provider.label} base URL`}
          />
          {providerConfig?.effectiveBaseUrl && <small className="muted">Requests go to {providerConfig.effectiveBaseUrl}</small>}
          <p className="muted">Local models are usually less consistent than cloud providers, especially smaller ones. Rough or incomplete output is often a model-size limit, not a ResuMorph bug. Leave the URL blank to keep using the backend&apos;s env default (handy under Docker).</p>
        </> : <>
          <small>{providerConfig?.keyMask ?? "No key saved"}</small>
          <input type="password" placeholder={provider.placeholder} value={keys[provider.id] ?? ""} onChange={(event) => updateKey(provider.id, event.target.value)} />
        </>}
        {loadingModels[provider.id] ? <p className="muted">Loading available models…</p> : availableModels[provider.id]?.length ? <select value={models[provider.id] ?? ""} onChange={(event) => void changeModel(provider.id, event.target.value)} disabled={busy !== null}>
          <option value="">Choose model</option>
          {availableModels[provider.id].map((model) => <option key={model} value={model}>{model}</option>)}
        </select> : <input placeholder="Model" value={models[provider.id] ?? ""} onChange={(event) => setModels((value) => ({ ...value, [provider.id]: event.target.value }))} />}
        <div className="actions">
          <button className="primary" onClick={() => void save(provider.id)} disabled={busy !== null}>{busy === `save-${provider.id}` && <ButtonSpinner />}{busy === `save-${provider.id}` ? "Saving..." : local ? "Save" : "Save key"}</button>
          {providerConfig?.isEnabled && <button className="secondary" onClick={() => void saveModel(provider.id)} disabled={busy !== null || !(models[provider.id] ?? "").trim()}>{busy === `model-${provider.id}` && <ButtonSpinner />}{busy === `model-${provider.id}` ? "Saving..." : "Save model"}</button>}
          <button className="secondary" onClick={() => void test(provider.id)} disabled={busy !== null}>{busy === `test-${provider.id}` && <ButtonSpinner />}{busy === `test-${provider.id}` ? "Testing..." : "Test connection"}</button>
          {(providerConfig?.isEnabled || local) && <button className="secondary" onClick={() => void loadModels(provider.id, keys[provider.id] || undefined, true)} disabled={busy !== null || loadingModels[provider.id]}>{loadingModels[provider.id] && <ButtonSpinner />}{loadingModels[provider.id] ? "Loading..." : "Reload models"}</button>}
          {providerConfig?.isEnabled && <button className="danger" onClick={() => void deleteProvider(provider.id)} disabled={busy !== null}>{busy === `delete-${provider.id}` && <ButtonSpinner />}{busy === `delete-${provider.id}` ? "Clearing..." : local ? "Clear" : "Clear key"}</button>}
        </div>
      </section>;
      })}

      <section className="provider-card">
        <h3>Default LLM</h3>
        <select value={defaultProvider ?? ""} onChange={(event) => setSettings((current) => current ? { ...current, defaultProvider: event.target.value as ProviderName, defaultModel: "" } : current)}>
          <option value="">Choose provider</option>
          {enabledProviders.map((item) => <option key={item.provider} value={item.provider}>{providerLabel(item.provider)}</option>)}
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
            <option value="">{enabledProviders.length ? "Choose configured LLM" : "No configured LLM yet"}</option>
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

    {message && <p className="status">{message}</p>}
  </section>;
}
