import { useCallback, useEffect, useRef, useState } from "react";
import FormatPicker from "./components/FormatPicker";
import HistoryList from "./components/HistoryList";
import JobProgress from "./components/JobProgress";
import PreviewCard from "./components/PreviewCard";
import SettingsPanel from "./components/SettingsPanel";
import * as api from "./lib/api";
import type { HistoryEntry, Job, MediaInfo, Settings } from "./lib/types";
import markUrl from "../assets/down.png";

const POLL_MS = 500;

export default function App() {
  const [url, setUrl] = useState("");
  const [info, setInfo] = useState<MediaInfo | null>(null);
  const [format, setFormat] = useState("best");
  const [job, setJob] = useState<Job | null>(null);
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

  // Poll the active job until it reaches a terminal state.
  const pollRef = useRef<number | null>(null);
  useEffect(() => {
    if (!job || job.status === "done" || job.status === "error") return;

    pollRef.current = window.setInterval(async () => {
      try {
        const next = await api.getJob(job.id);
        setJob(next);
        if (next.status === "done" || next.status === "error") refreshHistory();
      } catch {
        // A transient poll failure is not worth tearing the UI down over.
      }
    }, POLL_MS);

    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [job, refreshHistory]);

  function reportError(err: unknown) {
    const needsAuth = err instanceof api.ApiError && err.needsAuth;
    setError({ message: err instanceof Error ? err.message : "Something went wrong.", needsAuth });
  }

  async function runAnalyze(raw: string): Promise<MediaInfo | null> {
    setAnalyzing(true);
    setError(null);
    setInfo(null);
    setJob(null);
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
    const source = media ?? info;
    try {
      const { jobId } = await api.download(raw, fmt);
      setJob({
        id: jobId,
        url: raw,
        platform: source?.platform ?? null,
        title: source?.title ?? null,
        status: "queued",
        progress: 0,
        speed: null,
        eta: null,
        downloaded_bytes: null,
        total_bytes: null,
        filepath: null,
        error: null,
      });
    } catch (err) {
      reportError(err);
    }
  }

  async function onAnalyze(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    await runAnalyze(url.trim());
  }

  /** Paste-to-download: analyze the pasted link, then fetch it at best quality. */
  function onPaste(e: React.ClipboardEvent<HTMLInputElement>) {
    if (!settings?.auto_download) return;
    const pasted = e.clipboardData.getData("text").trim();
    if (!/^https?:\/\/\S+$/i.test(pasted)) return;

    e.preventDefault();
    setUrl(pasted);
    void (async () => {
      const media = await runAnalyze(pasted);
      // formats[0] is always "best"; image posts expose none and ignore it.
      if (media) await runDownload(pasted, "best", media);
    })();
  }

  const busy = job !== null && job.status !== "done" && job.status !== "error";

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

      <form className="intake" onSubmit={onAnalyze}>
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
                disabled={busy}
              >
                {busy ? "Downloading…" : "Download"}
              </button>
            </div>
          </>
        )}

        {job && <JobProgress job={job} />}
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
