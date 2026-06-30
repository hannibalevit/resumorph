import { useEffect, useState } from "react";
import { api, type AdminJob, type AdminJobDetail, type ArtifactDetail } from "../shared/apiClient";

type HistoryViewProps = {
  onDeleted?: (id: string) => void;
  onCleared?: () => void;
};

function ButtonSpinner() {
  return <span className="button-spinner" aria-hidden="true" />;
}

function downloadArtifact(artifact: ArtifactDetail): void {
  if (!artifact.base64File) return;
  const bytes = Uint8Array.from(atob(artifact.base64File), (char) => char.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: artifact.mimeType || "application/octet-stream" }));
  void chrome.downloads.download({ url, filename: artifact.fileName || "artifact.docx", saveAs: true }).finally(() => setTimeout(() => URL.revokeObjectURL(url), 10_000));
}

export function HistoryView({ onDeleted, onCleared }: HistoryViewProps) {
  const [items, setItems] = useState<AdminJob[]>([]);
  const [totalJobCount, setTotalJobCount] = useState(0);
  const [search, setSearch] = useState("");
  const [provider, setProvider] = useState("");
  const [detail, setDetail] = useState<AdminJobDetail | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactDetail[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [copiedArtifactId, setCopiedArtifactId] = useState<string | null>(null);

  const load = async (showProgress = false) => {
    if (showProgress) setBusy("search");
    try {
      const result = await api.adminSessions(search, provider);
      setItems(result.items);
      setTotalJobCount(result.total);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load history.");
    } finally {
      if (showProgress) setBusy(null);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const open = async (id: string) => {
    setBusy(`open-${id}`);
    try {
      const [job, files] = await Promise.all([api.adminSession(id), api.adminArtifacts(id)]);
      setDetail(job);
      setArtifacts(files);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not open job.");
    } finally {
      setBusy(null);
    }
  };

  const deleteJob = async (id: string) => {
    if (!confirm("Delete this job, generated files, and saved LLM artifacts?")) return;
    setBusy(`delete-${id}`);
    try {
      await api.deleteSession(id);
      setItems((current) => current.filter((item) => item.id !== id));
      setTotalJobCount((current) => Math.max(0, current - 1));
      if (detail?.id === id) {
        setDetail(null);
        setArtifacts([]);
      }
      onDeleted?.(id);
      setMessage("Job deleted from history.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not delete job.");
    } finally {
      setBusy(null);
    }
  };

  const clearHistory = async () => {
    if (!confirm("Clear all job history, generated files, and saved LLM artifacts?")) return;
    setBusy("clear-history");
    try {
      await api.clearSessions();
      setItems([]);
      setTotalJobCount(0);
      setDetail(null);
      setArtifacts([]);
      onCleared?.();
      setMessage("Job history cleared.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not clear job history.");
    } finally {
      setBusy(null);
    }
  };

  const copyText = async (artifact: ArtifactDetail) => {
    const body = typeof artifact.contentJson.body === "string" ? artifact.contentJson.body : "";
    if (!body) return;
    try {
      await navigator.clipboard.writeText(body);
      setCopiedArtifactId(artifact.id);
      window.setTimeout(() => setCopiedArtifactId((current) => current === artifact.id ? null : current), 1600);
      setMessage("Text copied.");
    } catch {
      setMessage("Could not copy text.");
    }
  };

  if (detail) return <section className="history-view">
    <div className="detail-toolbar">
      <button className="secondary" onClick={() => setDetail(null)}>← History</button>
      <button className="danger compact" disabled={busy !== null} onClick={() => void deleteJob(detail.id)}>{busy === `delete-${detail.id}` && <ButtonSpinner />}{busy === `delete-${detail.id}` ? "Deleting..." : "Delete job"}</button>
    </div>
    <h2>{detail.companyName || "Unknown company"} | {detail.positionTitle || "Untitled role"}</h2>
    <p>{detail.location || "Location not specified"} · {detail.hostname}</p>
    <a href={detail.sourceUrl} target="_blank" rel="noreferrer">Open source vacancy ↗</a>
    <h3>Job data</h3>
    <p>{detail.jobContext.jobDescription || "No description saved."}</p>
    <h3>Requirements</h3>
    <ul>{detail.jobContext.requirements.length ? detail.jobContext.requirements.map((item) => <li key={item}>{item}</li>) : <li>Not explicitly detected</li>}</ul>
    <h3>Related links</h3>
    <ul>{detail.relatedLinks.length ? detail.relatedLinks.map((link) => <li key={link.id}><a href={link.url} target="_blank" rel="noreferrer">{link.linkType}: {link.title || link.url}</a></li>) : <li>No related links saved.</li>}</ul>
    <h3>Generated artifacts</h3>
    {artifacts.length === 0 && <p className="muted">No generated artifacts for this job yet.</p>}
    {artifacts.map((artifact) => <article className="artifact" key={artifact.id}>
      <strong>{artifact.title}</strong>
      <small>{artifact.artifactType.replace("_", " ")} · {artifact.llmProvider || "—"} · {artifact.llmModel || "—"} · {new Date(artifact.createdAt).toLocaleString()}</small>
      {artifact.base64File && <button className="secondary compact" onClick={() => downloadArtifact(artifact)}>Download</button>}
      {typeof artifact.contentJson.body === "string" && <button className="secondary compact" onClick={() => void copyText(artifact)}>{copiedArtifactId === artifact.id ? "Copied" : "Copy text"}</button>}
    </article>)}
    <p className="status">{message}</p>
  </section>;

  return <section className="history-view">
    <div className="history-heading">
      <h2>History</h2>
      <button className="danger compact" disabled={busy !== null || totalJobCount === 0} onClick={() => void clearHistory()}>{busy === "clear-history" && <ButtonSpinner />}{busy === "clear-history" ? "Clearing..." : "Clear history"}</button>
    </div>
    <div className="filters">
      <input placeholder="Search company or position" value={search} onChange={(event) => setSearch(event.target.value)} />
      <select value={provider} onChange={(event) => setProvider(event.target.value)}>
        <option value="">All providers</option>
        <option value="openai">OpenAI</option>
        <option value="gemini">Gemini</option>
        <option value="claude">Claude</option>
      </select>
      <button className="secondary" disabled={busy !== null} onClick={() => void load(true)}>{busy === "search" && <ButtonSpinner />}{busy === "search" ? "Searching..." : "Search"}</button>
    </div>
    {items.map((item) => <article className="history-item" key={item.id} onClick={() => { if (busy === null) void open(item.id); }}>
      <div className="history-item-main">
        <strong>{item.title}</strong>
        <span>{item.location || "Location not specified"}</span>
        <small>{item.hostname} · {item.llmProviderUsed || "no provider"} · {new Date(item.updatedAt).toLocaleString()}</small>
      </div>
      <button className="danger compact" disabled={busy !== null} onClick={(event) => { event.stopPropagation(); void deleteJob(item.id); }}>{busy === `delete-${item.id}` && <ButtonSpinner />}{busy === `delete-${item.id}` ? "Deleting..." : "Delete"}</button>
    </article>)}
    {items.length === 0 && <p className="muted">No saved job sessions.</p>}
    <p className="status">{message}</p>
  </section>;
}
