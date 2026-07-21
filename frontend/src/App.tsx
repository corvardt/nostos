import { useCallback, useEffect, useMemo, useState } from "react";
import FormatPicker from "./components/FormatPicker";
import HistoryList from "./components/HistoryList";
import JobProgress from "./components/JobProgress";
import PreviewCard from "./components/PreviewCard";
import QueueList from "./components/QueueList";
import SettingsPanel from "./components/SettingsPanel";
import * as api from "./lib/api";
import type { HistoryEntry, Job, MediaInfo, Settings } from "./lib/types";
import { extractUrls, looksLikePlaylist } from "./lib/urls";
import markUrl from "../assets/down.png";

const POLL_MS = 500;

/** A confirmed-before-queueing set of links: a paste of many, or a playlist. */
interface Pending {
  urls: string[];
  title?: string;
  truncated?: boolean;
}

function blankJob(id: string, url: string, media?: MediaInfo | null): Job {
  return {
    id,
    url,
    platform: media?.platform ?? null,
    title: media?.title ?? null,
    status: "queued",
    progress: 0,
    speed: null,
    eta: null,
    downloaded_bytes: null,
    total_bytes: null,
    filepath: null,
    error: null,
  };
}

export default function App() {
  const [url, setUrl] = useState("");
  const [info, setInfo] = useState<MediaInfo | null>(null);
  const [format, setFormat] = useState("best");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<{ message: string; needsAuth: boolean } | null>(null);

  const refreshHistory = useCallback(() => {
    api.getHistory().then(setHistory).catch(() => {});
  }, []);

  useEffect(() => {
    refreshHistory();
    api.getSettings().then(setSettings).catch(() => {});
  }, [refreshHistory]);

  // Poll every unfinished job on one timer. Keyed on the active ids so the
  // interval is rebuilt when the set changes, not on every progress tick.
  const activeIds = useMemo(
    () => jobs.filter((j) => j.status !== "done" && j.status !== "error").map((j) => j.id),
    [jobs],
  );
  const activeKey = activeIds.join(",");

  useEffect(() => {
    if (!activeKey) return;
    const ids = activeKey.split(",");

    const timer = window.setInterval(async () => {
      const updates = await Promise.all(ids.map((id) => api.getJob(id).catch(() => null)));
      const fresh = updates.filter((j): j is Job => j !== null);
      if (fresh.length === 0) return;

      setJobs((prev) => prev.map((j) => fresh.find((f) => f.id === j.id) ?? j));
      if (fresh.some((j) => j.status === "done" || j.status === "error")) refreshHistory();
    }, POLL_MS);

    return () => window.clearInterval(timer);
  }, [activeKey, refreshHistory]);

  function reportError(err: unknown) {
    const needsAuth = err instanceof api.ApiError && err.needsAuth;
    setError({ message: err instanceof Error ? err.message : "Something went wrong.", needsAuth });
  }

  async function runAnalyze(raw: string): Promise<MediaInfo | null> {
    setAnalyzing(true);
    setError(null);
    setInfo(null);
    setPending(null);
    try {
      const result = await api.analyze(raw);
      setInfo(result);
      setFormat(result.formats[0]?.id ?? "best");
      return result;
    } catch (err) {
      reportError(err);
      return null;
    } finally {
      setAnalyzing(false);
    }
  }

  /** `media` is passed explicitly because the paste flow runs before state settles. */
  async function runDownload(raw: string, fmt: string, media?: MediaInfo | null) {
    setError(null);
    try {
      const { jobId } = await api.download(raw, fmt);
      setJobs((prev) => [blankJob(jobId, raw, media ?? info), ...prev]);
    } catch (err) {
      reportError(err);
    }
  }

  async function runBatch(urls: string[]) {
    setError(null);
    setInfo(null);
    try {
      const result = await api.downloadBatch(urls, "best");
      const started = result.items
        .filter((i) => i.jobId)
        .map((i) => blankJob(i.jobId!, i.url));
      setJobs((prev) => [...started, ...prev]);
      setPending(null);
      setUrl("");
      if (result.rejected > 0) {
        const first = result.items.find((i) => i.error);
        setError({
          message: `${result.accepted} queued, ${result.rejected} skipped. ${first?.error ?? ""}`,
          needsAuth: false,
        });
      }
    } catch (err) {
      reportError(err);
    }
  }

  async function runExpand(raw: string) {
    setAnalyzing(true);
    setError(null);
    setInfo(null);
    try {
      const list = await api.expand(raw);
      if (list.count === 0) {
        setError({ message: "That playlist has no items.", needsAuth: false });
        return;
      }
      setPending({
        urls: list.entries.map((e) => e.url),
        title: list.title,
        truncated: list.truncated,
      });
    } catch (err) {
      reportError(err);
    } finally {
      setAnalyzing(false);
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const urls = extractUrls(url);
    if (urls.length > 1) {
      setPending({ urls });
      return;
    }
    const one = url.trim();
    if (!one) return;
    // A playlist expands to a confirm step; a single link previews as before.
    if (looksLikePlaylist(one)) {
      await runExpand(one);
      return;
    }
    await runAnalyze(one);
  }

  function onPaste(e: React.ClipboardEvent<HTMLInputElement>) {
    const text = e.clipboardData.getData("text");
    const urls = extractUrls(text);

    // Several links at once is always a batch, and always needs confirming:
    // a stray paste must never start dozens of downloads on its own.
    if (urls.length > 1) {
      e.preventDefault();
      setUrl(text.trim());
      setInfo(null);
      setError(null);
      setPending({ urls });
      return;
    }

    // Never auto-download a playlist: expanding it needs confirming first.
    if (urls.length === 1 && looksLikePlaylist(urls[0])) {
      e.preventDefault();
      setUrl(urls[0]);
      void runExpand(urls[0]);
      return;
    }

    if (urls.length === 1 && settings?.auto_download) {
      e.preventDefault();
      setUrl(urls[0]);
      setPending(null);
      void (async () => {
        const media = await runAnalyze(urls[0]);
        if (media) await runDownload(urls[0], "best", media);
      })();
    }
  }

  const busy = jobs.some((j) => j.status !== "done" && j.status !== "error");
  const singleJob = jobs.length === 1 ? jobs[0] : null;

  return (
    <div className="app">
      <header className="masthead">
        <img className="mark" src={markUrl} alt="" width={30} height={30} />
        <h1 className="wordmark">Nostos</h1>
        <button
          className="destination"
          onClick={() => setShowSettings((s) => !s)}
          title="Settings"
          aria-expanded={showSettings}
        >
          <span className="eyebrow">to</span>
          <span className="destination-path">{settings?.download_dir ?? "…"}</span>
        </button>
      </header>

      {showSettings && settings && <SettingsPanel settings={settings} onSaved={setSettings} />}

      <form className="intake" onSubmit={onSubmit}>
        <input
          className="input"
          placeholder={
            settings?.auto_download
              ? "Paste a link to download it automatically"
              : "Paste a YouTube, Instagram or Threads link"
          }
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onPaste={onPaste}
          autoFocus
          spellCheck={false}
          aria-label="Media link"
        />
        <button className="btn" type="submit" disabled={analyzing || !url.trim()}>
          {analyzing ? "Analyzing…" : "Analyze"}
        </button>
      </form>

      <div className="stack">
        {pending && (
          <div className="panel batch">
            <div className="batch-body">
              <span className="eyebrow">{pending.title ? "Playlist" : "Batch"}</span>
              <p className="batch-count">
                <strong className="num">{pending.urls.length}</strong>
                {pending.urls.length === 1 ? " link" : " links"} ready
              </p>
              {pending.title && <p className="batch-sub">{pending.title}</p>}
              {pending.truncated && (
                <p className="batch-sub">Only the first {pending.urls.length} will be queued.</p>
              )}
            </div>
            <div className="batch-actions">
              <button className="btn" onClick={() => setPending(null)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={() => runBatch(pending.urls)}>
                Download all
              </button>
            </div>
          </div>
        )}

        {error && (
          <div className="panel panel-bad outcome">
            <div className="outcome-body">
              <span className="outcome-label">Cannot analyze</span>
              <p className="outcome-msg">{error.message}</p>
              {error.needsAuth && (
                <button className="link" onClick={() => setShowSettings(true)}>
                  Choose a browser
                </button>
              )}
            </div>
          </div>
        )}

        {info && (
          <>
            <PreviewCard info={info} />
            <div className="dispatch">
              <FormatPicker
                formats={info.formats}
                value={format}
                onChange={setFormat}
                disabled={busy}
              />
              <button
                className="btn btn-primary"
                onClick={() => runDownload(url.trim(), format)}
                disabled={busy || info.is_live}
              >
                {busy ? "Downloading…" : "Download"}
              </button>
            </div>
          </>
        )}

        {/* One download keeps the full instrument readout; a queue gets rows. */}
        {singleJob ? <JobProgress job={singleJob} /> : jobs.length > 1 && <QueueList jobs={jobs} />}
      </div>

      <section className="ledger">
        <div className="ledger-head">
          <span className="eyebrow">Recent</span>
          <span className="eyebrow">{history.length}</span>
        </div>
        <HistoryList entries={history} />
      </section>

      <footer className="footer">
        <span className="eyebrow">Nostos</span>
        <a
          className="footer-link"
          href="https://github.com/corvardt"
          target="_blank"
          rel="noreferrer noopener"
        >
          corvardt
        </a>
      </footer>
    </div>
  );
}
