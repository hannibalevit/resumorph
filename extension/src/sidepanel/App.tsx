import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ArtifactDetail, type GeneratedFile } from "../shared/apiClient";
import { isBlockedUrl } from "../shared/blockedSites";
import { EXTENSION_ENABLED_STORAGE_KEY, isExtensionEnabled, isOnboardingComplete, saveExtensionEnabled } from "../shared/storage";
import type { JobSession, JobSessionSummary, PageSnapshot } from "../shared/sidepanelTypes";
import { HistoryView } from "./HistoryView";
import { OnboardingView } from "./OnboardingView";
import { SettingsView } from "./SettingsView";

type ActiveTab = { id?: number; url?: string; title?: string };
type BackendStatus = "checking" | "connected" | "disconnected";
type BusyState = "scan" | "manualScan" | "resume" | "coverLetter" | "reconnect" | "download" | null;
const MAX_SCAN_TEXT_LENGTH = 80_000;
const MIN_MANUAL_TEXTAREA_HEIGHT = 56;
const MAX_MANUAL_TEXTAREA_HEIGHT = 260;

function ButtonSpinner() {
  return <span className="button-spinner" aria-hidden="true" />;
}

function tabName(session: JobSessionSummary): string {
  return `${session.companyName || "Unknown company"} | ${session.positionTitle || "Untitled role"}`;
}

function download(file: GeneratedFile): void {
  downloadBase64(file.base64, file.mimeType, file.fileName);
}

function downloadBase64(base64: string, mimeType: string | undefined, fileName: string): void {
  const bytes = Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: mimeType || "application/octet-stream" }));
  void chrome.downloads.download({ url, filename: fileName, saveAs: true }).finally(() => setTimeout(() => URL.revokeObjectURL(url), 10_000));
}

async function requestPageSnapshot(tabId: number): Promise<unknown> {
  try {
    return await chrome.tabs.sendMessage(tabId, { type: "SCAN_PAGE" }) as unknown;
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (!/Receiving end does not exist|Could not establish connection/i.test(message)) throw error;

    // A page opened before the extension was installed/reloaded has no declarative
    // content script yet. Inject the same bundled scanner on the explicit Scan click.
    try {
      await chrome.scripting.executeScript({ target: { tabId }, files: ["assets/pageAssistant.js"] });
      return await chrome.tabs.sendMessage(tabId, { type: "SCAN_PAGE" }) as unknown;
    } catch (injectionError) {
      const reason = injectionError instanceof Error ? injectionError.message : "Chrome blocked access to this page.";
      throw new Error(`This page cannot be scanned. Open a regular http(s) job page and try again. (${reason})`);
    }
  }
}

function normalizeUrl(url: string): string {
  try {
    const value = new URL(url);
    ["ref", "source", "trk", "trackingId", "utm_source", "utm_medium", "utm_campaign"].forEach((key) => value.searchParams.delete(key));
    value.hash = "";
    value.pathname = value.pathname.replace(/\/$/, "") || "/";
    return value.toString();
  } catch {
    return url;
  }
}

function createManualPageSnapshot(text: string, tab: ActiveTab, session: JobSession | null): PageSnapshot {
  const fallbackUrl = `manual://vacancy/${Date.now()}`;
  const tabUrl = tab.url && tab.url.trim() && !isBlockedUrl(tab.url) ? tab.url : undefined;
  const url = session?.sourceUrl || tabUrl || fallbackUrl;
  const title = session ? tabName(session) : tab.title?.trim() || "Manual vacancy";
  const hostname = (() => {
    if (session?.hostname) return session.hostname;
    try { return new URL(url).hostname; } catch { return "manual"; }
  })();
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);

  return {
    url,
    normalizedUrl: session?.normalizedUrl || normalizeUrl(url),
    title,
    hostname,
    capturedAt: new Date().toISOString(),
    visibleText: text.slice(0, MAX_SCAN_TEXT_LENGTH),
    primaryJobText: text.slice(0, MAX_SCAN_TEXT_LENGTH),
    primaryJobSource: "manual_input",
    primaryJobConfidence: 1,
    extractionWarnings: text.length > MAX_SCAN_TEXT_LENGTH ? ["Pasted text was truncated to 80,000 characters."] : [],
    meta: { description: lines.slice(0, 6).join(" ").slice(0, 500) || undefined },
    jsonLd: [],
    headings: lines.slice(0, 8).map((line, index) => ({ level: index === 0 ? 1 : 2, text: line.slice(0, 500) })),
    links: [],
    formFields: [],
    domBlocks: [{ selector: "manual-input", text: text.slice(0, 500), score: 1 }],
  };
}

export function App() {
  const [backend, setBackend] = useState<BackendStatus>("checking");
  const [sessions, setSessions] = useState<JobSessionSummary[]>([]);
  const [activeSession, setActiveSession] = useState<JobSession | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>({});
  const [resumePresent, setResumePresent] = useState(false);
  const [extensionActive, setExtensionActive] = useState(true);
  const [status, setStatus] = useState("Ready to scan this page.");
  const [busy, setBusy] = useState<BusyState>(null);
  const [showDebug, setShowDebug] = useState(false);
  const [view, setView] = useState<"jobs" | "history" | "settings">("jobs");
  const [closedSessionIds, setClosedSessionIds] = useState<Set<string>>(() => new Set());
  const [showOnboarding, setShowOnboarding] = useState<boolean | null>(null);
  const [manualTextByJobKey, setManualTextByJobKey] = useState<Record<string, string>>({});
  const [coverLetter, setCoverLetter] = useState<ArtifactDetail | null>(null);
  const [coverLetterExpanded, setCoverLetterExpanded] = useState(false);
  const [coverLetterCopied, setCoverLetterCopied] = useState(false);
  const manualTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const copiedTimeoutRef = useRef<number | null>(null);
  const manualTextKey = useMemo(() => activeSession?.id ?? `tab:${activeTab.url || activeTab.id || "manual"}`, [activeSession?.id, activeTab.id, activeTab.url]);
  const manualJobText = manualTextByJobKey[manualTextKey] ?? "";
  const coverLetterBody = typeof coverLetter?.contentJson.body === "string" ? coverLetter.contentJson.body : "";

  const setManualJobText = useCallback((value: string) => {
    setManualTextByJobKey((current) => {
      const next = { ...current };
      if (value) next[manualTextKey] = value;
      else delete next[manualTextKey];
      return next;
    });
  }, [manualTextKey]);

  useEffect(() => {
    const colorScheme = window.matchMedia("(prefers-color-scheme: dark)");
    const syncActionTheme = () => void chrome.runtime.sendMessage({ type: "COLOR_SCHEME_CHANGED", isDark: colorScheme.matches }).catch(() => undefined);
    syncActionTheme();
    colorScheme.addEventListener("change", syncActionTheme);
    return () => colorScheme.removeEventListener("change", syncActionTheme);
  }, []);

  const refreshSessions = useCallback(async () => {
    const result = await api.sessions(); setSessions(result); return result;
  }, []);

  const selectSession = useCallback(async (id: string) => {
    const result = await api.session(id); setActiveSession(result);
    setClosedSessionIds((current) => {
      const next = new Set(current);
      next.delete(id);
      return next;
    });
    void chrome.runtime.sendMessage({ type: "SET_ACTIVE_JOB_SESSION", jobSessionId: id });
  }, []);

  const matchActiveTab = useCallback(async (tab: ActiveTab) => {
    if (!tab.url || !/^https?:/.test(tab.url)) { setActiveSession(null); return; }
    if (isBlockedUrl(tab.url)) { setActiveSession(null); setStatus("This site isn't related to job search, so scanning is disabled here."); return; }
    try {
      const match = await api.match(tab.url, tab.title || "");
      if (match.matched && match.jobSessionId) { await selectSession(match.jobSessionId); setStatus("Matched the current page to a saved job."); }
      else { setActiveSession(null); setStatus("No saved job for this page — scan it to start."); }
    } catch { /* Backend state is already displayed separately. */ }
  }, [selectSession]);

  const reconnectBackend = useCallback(async (showProgress = false) => {
    if (showProgress) { setBusy("reconnect"); setStatus("Reconnecting to the backend…"); }
    setBackend("checking");
    try {
      await api.health();
      setBackend("connected");
      await refreshSessions();
    } catch {
      setBackend("disconnected");
      setStatus("Backend is disconnected. Start the local server, then reconnect.");
      if (showProgress) setBusy(null);
      return;
    }

    try { await api.getResume(); setResumePresent(true); } catch { setResumePresent(false); }
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const current = { id: tab?.id, url: tab?.url, title: tab?.title };
    setActiveTab(current);
    await matchActiveTab(current);
    if (showProgress) setBusy(null);
  }, [matchActiveTab, refreshSessions]);

  useEffect(() => {
    void isOnboardingComplete().then((complete) => setShowOnboarding(!complete)).catch(() => setShowOnboarding(true));
    void isExtensionEnabled().then(setExtensionActive).catch(() => undefined);
    void reconnectBackend();
    const listener = (message: { type?: string; tab?: ActiveTab }) => {
      if (message.type === "ACTIVE_TAB_CHANGED" && message.tab) { setActiveTab(message.tab); void matchActiveTab(message.tab); }
    };
    const storageListener = (changes: Record<string, chrome.storage.StorageChange>, areaName: string) => {
      if (areaName !== "local") return;
      const change = changes[EXTENSION_ENABLED_STORAGE_KEY];
      if (change) setExtensionActive(change.newValue !== false);
    };
    chrome.runtime.onMessage.addListener(listener);
    chrome.storage.onChanged.addListener(storageListener);
    return () => {
      chrome.runtime.onMessage.removeListener(listener);
      chrome.storage.onChanged.removeListener(storageListener);
    };
  }, [matchActiveTab, reconnectBackend]);

  useEffect(() => {
    const textarea = manualTextareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(Math.max(textarea.scrollHeight, MIN_MANUAL_TEXTAREA_HEIGHT), MAX_MANUAL_TEXTAREA_HEIGHT)}px`;
  }, [manualJobText, manualTextKey]);

  useEffect(() => {
    let cancelled = false;
    setCoverLetterExpanded(false);
    setCoverLetterCopied(false);
    const artifact = activeSession?.artifacts.find((item) => item.artifactType === "cover_letter");
    if (!activeSession || !artifact) {
      setCoverLetter(null);
      return;
    }
    void api.artifact(artifact.id)
      .then((detail) => { if (!cancelled) setCoverLetter(detail); })
      .catch(() => { if (!cancelled) setCoverLetter(null); });
    return () => { cancelled = true; };
  }, [activeSession]);

  useEffect(() => () => {
    if (copiedTimeoutRef.current) window.clearTimeout(copiedTimeoutRef.current);
  }, []);

  const toggleExtension = async () => {
    const next = !extensionActive;
    setExtensionActive(next);
    await saveExtensionEnabled(next);
    setStatus(next ? "Extension enabled." : "Extension disabled. Page assistant and scan actions are paused.");
  };

  const scan = async () => {
    if (!activeTab.id) return;
    setBusy("scan"); setStatus("Scanning the page…");
    try {
      const response = await requestPageSnapshot(activeTab.id) as { snapshot?: unknown; error?: string };
      if (response.error) throw new Error(response.error);
      if (!response.snapshot) throw new Error("The page scanner did not return a snapshot. Refresh the page and try again.");
      setStatus("Extracting the job context…"); const session = await api.scan(response.snapshot as Parameters<typeof api.scan>[0]);
      setClosedSessionIds((current) => {
        const next = new Set(current);
        next.delete(session.id);
        return next;
      });
      await refreshSessions(); setActiveSession(session); void chrome.runtime.sendMessage({ type: "SET_ACTIVE_JOB_SESSION", jobSessionId: session.id });
      setStatus("Job session saved.");
    } catch (error) { setStatus(error instanceof Error ? error.message : "The page could not be scanned."); }
    finally { setBusy(null); }
  };

  const scanManualText = async () => {
    const text = manualJobText.trim();
    if (!text) {
      setStatus("Paste vacancy text before sending it for scanning.");
      return;
    }

    setBusy("manualScan");
    setStatus("Extracting the job context from pasted text...");
    try {
      const isRescan = Boolean(activeSession);
      const previousManualTextKey = manualTextKey;
      const snapshot = createManualPageSnapshot(text, activeTab, activeSession);
      const session = await api.scan(snapshot);
      setClosedSessionIds((current) => {
        const next = new Set(current);
        next.delete(session.id);
        return next;
      });
      await refreshSessions();
      setActiveSession(session);
      setManualTextByJobKey((current) => {
        const next = { ...current };
        delete next[previousManualTextKey];
        delete next[session.id];
        return next;
      });
      void chrome.runtime.sendMessage({ type: "SET_ACTIVE_JOB_SESSION", jobSessionId: session.id });
      const savedMessage = isRescan ? "Job session rescanned from pasted text." : "Job session saved from pasted text.";
      setStatus(text.length > MAX_SCAN_TEXT_LENGTH ? `${savedMessage} Text was truncated to 80,000 characters.` : savedMessage);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "The pasted text could not be scanned.");
    } finally {
      setBusy(null);
    }
  };

  const generateResume = async () => {
    if (!activeSession) return;
    const sessionId = activeSession.id;
    setBusy("resume"); setStatus("Generating resume…");
    try {
      const file = await api.generateResume(sessionId);
      download(file);
      const updated = await api.session(sessionId);
      setActiveSession(updated);
      await refreshSessions();
      setStatus("Generated file is ready for download.");
    } catch (error) { setStatus(error instanceof Error ? error.message : "Generation failed."); }
    finally { setBusy(null); }
  };

  const generateCoverLetter = async () => {
    if (!activeSession) return;
    const sessionId = activeSession.id;
    setBusy("coverLetter"); setStatus("Generating cover letter...");
    try {
      const file = await api.generateCoverLetter(sessionId);
      const [updated, detail] = await Promise.all([api.session(sessionId), api.artifact(file.artifactId)]);
      setActiveSession(updated);
      setCoverLetter(detail);
      await refreshSessions();
      setStatus("Cover letter generated.");
    } catch (error) { setStatus(error instanceof Error ? error.message : "Cover letter generation failed."); }
    finally { setBusy(null); }
  };

  const copyCoverLetter = async () => {
    if (!coverLetterBody) return;
    try {
      await navigator.clipboard.writeText(coverLetterBody);
      setCoverLetterCopied(true);
      if (copiedTimeoutRef.current) window.clearTimeout(copiedTimeoutRef.current);
      copiedTimeoutRef.current = window.setTimeout(() => setCoverLetterCopied(false), 1600);
      setStatus("Cover letter copied.");
    } catch {
      setStatus("Could not copy the cover letter.");
    }
  };

  const downloadArtifact = async (artifactId: string) => {
    setBusy("download");
    setStatus("Fetching saved file from the database…");
    try {
      const artifact: ArtifactDetail = await api.artifact(artifactId);
      if (!artifact.base64File) throw new Error("This saved artifact does not include a downloadable file.");
      downloadBase64(artifact.base64File, artifact.mimeType, artifact.fileName || "resume-tailor-artifact");
      setStatus("Saved file is ready for download.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not download saved file.");
    } finally {
      setBusy(null);
    }
  };

  const closeSession = async (id: string) => {
    setClosedSessionIds((current) => new Set(current).add(id));
    if (activeSession?.id === id) {
      setActiveSession(null);
      setStatus("Tab closed. The job and generated files remain in History.");
    }
  };

  const context = activeSession?.jobContext;
  const snapshot = activeSession?.rawPageSnapshot;
  const artifactCount = useMemo(() => activeSession?.artifacts.length ?? 0, [activeSession]);
  const visibleSessions = useMemo(() => sessions.filter((session) => !closedSessionIds.has(session.id)), [closedSessionIds, sessions]);
  const hasResumeArtifact = Boolean(activeSession?.artifacts.some((artifact) => artifact.artifactType === "resume"));
  const hasCoverLetterArtifact = Boolean(activeSession?.artifacts.some((artifact) => artifact.artifactType === "cover_letter"));
  const siteBlocked = isBlockedUrl(activeTab.url);
  const actionsDisabled = busy !== null || backend !== "connected" || !extensionActive || siteBlocked;
  const manualScanDisabled = busy !== null || backend !== "connected" || !extensionActive || !manualJobText.trim();
  const generationDisabled = busy !== null || !resumePresent || !extensionActive || !activeSession || siteBlocked;
  const connectionLabel = !extensionActive ? "disabled" : backend;

  if (showOnboarding === null) {
    return <main className="panel onboarding-shell"><section className="onboarding-card"><p className="status">Loading setup...</p></section></main>;
  }

  if (showOnboarding) {
    return <OnboardingView onComplete={() => { setShowOnboarding(false); setResumePresent(true); setStatus("Ready to scan this page."); void reconnectBackend(true); }} />;
  }

  return <main className="panel">
    {view === "settings" ? <SettingsView onResumeSaved={() => { setResumePresent(true); setStatus("Base resume saved."); }} /> : view === "history" ? <HistoryView onDeleted={(id) => { setSessions((current) => current.filter((session) => session.id !== id)); if (activeSession?.id === id) { setActiveSession(null); setCoverLetter(null); void chrome.storage.local.remove("activeJobSessionId"); } }} onCleared={() => { setSessions([]); setActiveSession(null); setClosedSessionIds(new Set()); setCoverLetter(null); setStatus("Job history cleared."); void chrome.storage.local.remove("activeJobSessionId"); }} /> : <>
    <section className="actions page-actions">
      <button className="primary" onClick={() => void scan()} disabled={actionsDisabled}>{busy === "scan" && <ButtonSpinner />}{busy === "scan" ? "Scanning..." : activeSession ? "Rescan this page" : "Scan this page"}</button>
      <button className="primary" disabled={generationDisabled} onClick={() => void generateResume()}>{busy === "resume" && <ButtonSpinner />}{busy === "resume" ? "Generating..." : hasResumeArtifact ? "Update resume" : "Generate resume"}</button>
      <button className="primary" disabled={generationDisabled} onClick={() => void generateCoverLetter()}>{busy === "coverLetter" && <ButtonSpinner />}{busy === "coverLetter" ? "Generating..." : hasCoverLetterArtifact ? "Update cover letter" : "Generate cover letter"}</button>
    </section>
    <section className="manual-scan" aria-label="Manual vacancy scan">
      <label htmlFor="manual-job-text">Manual vacancy text</label>
      <textarea ref={manualTextareaRef} id="manual-job-text" value={manualJobText} onChange={(event) => setManualJobText(event.target.value)} placeholder="Paste vacancy text here" />
      <div className="manual-scan-actions">
        <span>{manualJobText.trim().length.toLocaleString()} chars</span>
        <button className="secondary compact" onClick={() => void scanManualText()} disabled={manualScanDisabled}>{busy === "manualScan" && <ButtonSpinner />}{busy === "manualScan" ? "Sending..." : activeSession ? "Rescan from pasted text" : "Scan pasted text"}</button>
      </div>
    </section>
    <p className="status" role="status">{status}</p>
    <nav className="tabs" aria-label="Job sessions">{visibleSessions.length === 0 ? <span className="empty">No open job tabs</span> : visibleSessions.map((session) => <div key={session.id} className={session.id === activeSession?.id ? "tab-wrap active" : "tab-wrap"}><button className="tab" onClick={() => void selectSession(session.id)} title={tabName(session)}>{tabName(session)}</button><button className="close-tab" aria-label={`Close ${tabName(session)}`} title="Close tab" onClick={() => void closeSession(session.id)}>×</button></div>)}</nav>
    {!activeSession ? (siteBlocked ? <section className="neutral"><h2>Not a job site</h2><p>Resume Tailor is disabled on this site because it isn't related to job search.</p><small>Current: {activeTab.title || activeTab.url || "No browser page"}</small></section> : <section className="neutral"><h2>Scan a vacancy</h2><p>Open a job listing or application page, then scan it. The extension never scans or sends page data without your click.</p><small>Current: {activeTab.title || activeTab.url || "No browser page"}</small></section>) : <section className="job">
      <div className="job-title"><div><h2>{context?.positionTitle || "Untitled role"}</h2><p>{context?.companyName || "Unknown company"}{context?.location ? ` · ${context.location}` : ""}</p></div><span className="confidence">{Math.round((context?.confidence ?? 0) * 100)}% extracted</span></div>
      <a href={activeSession.sourceUrl} target="_blank" rel="noreferrer">Open source vacancy ↗</a>
      <div className="badges"><span>Scanned</span>{artifactCount > 0 && <span>{artifactCount} file{artifactCount === 1 ? "" : "s"}</span>}{(snapshot?.formFields.length ?? 0) > 0 && <span>Form detected</span>}</div>
      <section><h3>Summary</h3><p>{context?.jobDescription?.slice(0, 800) || "No description could be extracted."}</p></section>
      <section><h3>Requirements</h3><ul>{context?.requirements.length ? context.requirements.map((item) => <li key={item}>{item}</li>) : <li>Not explicitly detected</li>}</ul></section>
      <section><h3>Responsibilities</h3><ul>{context?.responsibilities.length ? context.responsibilities.map((item) => <li key={item}>{item}</li>) : <li>Not explicitly detected</li>}</ul></section>
      <section><h3>Keywords</h3><div className="keywords">{context?.keywords.length ? context.keywords.map((word) => <span key={word}>{word}</span>) : "No keywords detected"}</div></section>
      {coverLetterBody && <section><div className="section-heading"><h3>Cover letter</h3><button className={coverLetterCopied ? "icon compact copy-button copied" : "icon compact copy-button"} type="button" aria-label={coverLetterCopied ? "Cover letter copied" : "Copy cover letter"} title={coverLetterCopied ? "Copied" : "Copy cover letter"} onClick={() => void copyCoverLetter()}>{coverLetterCopied ? "Copied" : "⧉"}</button></div><article className={coverLetterExpanded ? "cover-letter-card expanded" : "cover-letter-card"}><p>{coverLetterBody}</p></article><button className="secondary compact show-more-button" type="button" onClick={() => setCoverLetterExpanded((current) => !current)}>{coverLetterExpanded ? "Show less" : "Show more"}</button></section>}
      {activeSession.artifacts.length > 0 && <section><h3>Saved files</h3>{activeSession.artifacts.map((artifact) => <article className="artifact" key={artifact.id}><strong>{artifact.title}</strong><small>{artifact.artifactType.replace("_", " ")} · {artifact.llmProvider || "—"} · {artifact.llmModel || "—"} · {new Date(artifact.createdAt).toLocaleString()}</small>{artifact.fileName && <button className="secondary compact" disabled={busy !== null} onClick={() => void downloadArtifact(artifact.id)}>{busy === "download" && <ButtonSpinner />}{busy === "download" ? "Downloading..." : "Download"}</button>}</article>)}</section>}
      {!resumePresent && <p className="warning">Upload a base resume before generating tailored materials.</p>}
      <details open={showDebug} onToggle={(event) => setShowDebug((event.target as HTMLDetailsElement).open)}><summary>Debug information</summary><dl><dt>Canonical job key</dt><dd>{activeSession.canonicalJobKey}</dd><dt>Backend job session</dt><dd>{activeSession.id}</dd><dt>Active browser tab</dt><dd>{activeTab.id ?? "unknown"}</dd><dt>Full visible characters</dt><dd>{snapshot?.visibleText.length ?? 0}</dd><dt>Primary source</dt><dd>{snapshot?.primaryJobSource || "full_visible_text"}</dd><dt>Primary characters</dt><dd>{snapshot?.primaryJobText?.length ?? 0}</dd><dt>Detected form fields</dt><dd>{snapshot?.formFields.length ?? 0}</dd><dt>Extraction warnings</dt><dd>{snapshot?.extractionWarnings?.join("; ") || "None"}</dd><dt>LLM warnings</dt><dd>{context?.warnings.join("; ") || "None"}</dd></dl></details>
    </section>}</>}
    <footer className="app-footer" aria-label="Extension controls">
      <span className={`connection ${connectionLabel}`}>● {connectionLabel}</span>
      <div className="footer-actions">
        <button className={`footer-button ${view === "jobs" ? "active" : ""}`} data-tooltip="Jobs" aria-label="Jobs" title="Jobs" onClick={() => setView("jobs")}>▦</button>
        <button className={`footer-button ${view === "history" ? "active" : ""}`} data-tooltip="History" aria-label="History" title="History" onClick={() => setView((current) => current === "history" ? "jobs" : "history")}>◷</button>
        <button className="footer-button reconnect-fab" data-tooltip="Reconnect" aria-label="Reconnect to backend" title="Reconnect" disabled={busy !== null} onClick={() => void reconnectBackend(true)}>{busy === "reconnect" ? <ButtonSpinner /> : "↻"}</button>
        <button className={`footer-button settings-fab ${view === "settings" ? "active" : ""}`} data-tooltip="Settings" aria-label="Settings" title="Settings" onClick={() => setView((current) => current === "settings" ? "jobs" : "settings")}>⚙</button>
        <button className="footer-button power-fab" data-tooltip={extensionActive ? "Disable" : "Enable"} aria-label={extensionActive ? "Disable extension" : "Enable extension"} aria-pressed={extensionActive} title={extensionActive ? "Disable" : "Enable"} onClick={() => void toggleExtension()}>⏻</button>
      </div>
    </footer>
  </main>;
}
