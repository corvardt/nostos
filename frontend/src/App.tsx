import { useCallback, useEffect, useMemo, useState } from "react";
import FormatPicker from "./components/FormatPicker";
import HistoryList from "./components/HistoryList";
import JobProgress from "./components/JobProgress";
import LibraryPanel from "./components/LibraryPanel";
import PreviewCard from "./components/PreviewCard";
import QueueList from "./components/QueueList";
import SettingsPanel from "./components/SettingsPanel";
import * as api from "./lib/api";
import type { HistoryEntry, Job, MediaInfo, Settings } from "./lib/types";
import { extractUrls, looksLikePlaylist } from "./lib/urls";
import { BATCH_QUALITIES } from "./lib/quality";
import { useTheme } from "./lib/theme";
import markUrl from "../assets/down.png";

const POLL_MS = 500;

// How long a completed item stays visible before it clears itself. Failed and
// stopped items are never auto-cleared: they are the ones you may want to retry.
const DONE_LINGER_MS = 4000;

/** A confirmed-before-queueing set of links: a paste of many, or a playlist.
 *  Titles are known up front for playlists, so the queue can name its rows
 *  before anything starts. */
interface Pending {
  urls: string[];
  titles: Record<string, string>;
  title?: string;
  truncated?: boolean;
}

function blankJob(id: string, url: string, media?: MediaInfo | null): Job {
  return {
    id,
    url,
    format: null,
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

/** Two ways in: one link at a time, or whole accounts at once. */
type View = "links" | "library";

const MODES: Array<{ id: View; name: string; what: string }> = [
  { id: "links", name: "Links", what: "One page at a time. Video or audio, from a URL you paste." },
  { id: "library", name: "Library", what: "A whole music collection. Your accounts, archived in one pass." },
];

export default function App() {
  const [theme, toggleTheme] = useTheme();
  const [view, setView] = useState<View>("links");
  const [url, setUrl] = useState("");
  const [info, setInfo] = useState<MediaInfo | null>(null);
  const [format, setFormat] = useState("best");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);
  const [batchFormat, setBatchFormat] = useState("best");
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
    () => jobs.filter((j) => j.status !== "done" && j.status !== "error" && j.status !== "cancelled").map((j) => j.id),
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
      if (fresh.some((j) => j.status === "done" || j.status === "error" || j.status === "cancelled")) refreshHistory();
    }, POLL_MS);

    return () => window.clearInterval(timer);
  }, [activeKey, refreshHistory]);

  // Completed items retire themselves one by one, so what remains on screen is
  // exactly the work that still needs a decision: failed and stopped downloads.
  useEffect(() => {
    const finished = jobs.filter((j) => j.status === "done").map((j) => j.id);
    if (finished.length === 0) return;

    const timer = window.setTimeout(() => {
      setJobs((prev) => prev.filter((j) => !finished.includes(j.id)));
    }, DONE_LINGER_MS);
    return () => window.clearTimeout(timer);
  }, [jobs]);

  async function onCancel(id: string) {
    // Reflect it at once; the poll confirms once the worker unwinds.
    setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, status: "cancelled" } : j)));
    await api.cancelJob(id).catch(() => {});
  }

  async function onCancelAll() {
    setJobs((prev) =>
      prev.map((j) =>
        j.status === "queued" || j.status === "running" ? { ...j, status: "cancelled" } : j,
      ),
    );
    await api.cancelAll().catch(() => {});
  }

  async function onRetry(id: string) {
    try {
      const { jobId } = await api.retryJob(id);
      const previous = jobs.find((j) => j.id === id);
      // Swap the dead row for the fresh attempt, keeping its place in the list.
      setJobs((prev) =>
        prev.map((j) =>
          j.id === id
            ? { ...blankJob(jobId, j.url), format: j.format, title: previous?.title ?? null }
            : j,
        ),
      );
    } catch (err) {
      reportError(err);
    }
  }

  async function onClearQueue() {
    await api.cancelAll().catch(() => {});
    setJobs([]);
  }

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

  async function runBatch(urls: string[], fmt: string, titles: Record<string, string> = {}) {
    setError(null);
    setInfo(null);
    try {
      const result = await api.downloadBatch(urls, fmt, titles);
      const started = result.items
        .filter((i) => i.jobId)
        .map((i) => ({ ...blankJob(i.jobId!, i.url), title: titles[i.url] ?? null }));
      setJobs((prev) => [...started, ...prev]);
      setPending(null);
      setUrl("");
      if (result.rejected > 0 || result.skipped > 0) {
        const parts = [`${result.accepted} queued`];
        if (result.skipped > 0) parts.push(`${result.skipped} already downloaded`);
        if (result.rejected > 0) {
          const first = result.items.find((i) => i.error && !i.skipped);
          parts.push(`${result.rejected} could not be queued: ${first?.error ?? ""}`);
        }
        setError({ message: parts.join(", ") + ".", needsAuth: false });
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
        titles: Object.fromEntries(
          list.entries.filter((e) => e.title).map((e) => [e.url, e.title as string]),
        ),
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
      setPending({ urls, titles: {} });
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
      setPending({ urls, titles: {} });
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

  const busy = jobs.some((j) => j.status !== "done" && j.status !== "error" && j.status !== "cancelled");
  const singleJob = jobs.length === 1 ? jobs[0] : null;
  /** Nothing analyzed, queued, confirmed or broken: the screen is free to explain itself. */
  const idle = !info && !pending && !error && jobs.length === 0;

  /** A library sync queues through the same job registry, so its downloads
   *  join the same queue list and are polled by the same timer. */
  function adoptJobs(jobIds: string[]) {
    setJobs((prev) => [
      ...jobIds.filter((id) => !prev.some((j) => j.id === id)).map((id) => blankJob(id, "")),
      ...prev,
    ]);
  }

  return (
    <div className="app">
      <header className="masthead">
        <img className="mark" src={markUrl} alt="" width={30} height={30} />
        <h1 className="wordmark">Nostos</h1>
        <button
          className="destination"
          onClick={() => setShowSettings((s) => !s)}
          title="Settings: folders, quality, browser cookies, music filing"
          aria-expanded={showSettings}
        >
          <span className="eyebrow">saves to</span>
          <span className="destination-path">
            {(view === "library" ? settings?.music_dir : settings?.download_dir) ?? "…"}
          </span>
        </button>
        <button
          className="medium-toggle"
          onClick={toggleTheme}
          title={theme === "dark" ? "Switch to paper" : "Switch to tube"}
          aria-label="Switch medium"
        >
          {theme === "dark" ? "tube" : "paper"}
        </button>
      </header>

      {/* The two halves of the app, each saying what it is for. Naming them in
          the masthead was not enough: half the program was a word most people
          never clicked. */}
      <nav className="modes" role="tablist">
        {MODES.map((mode) => (
          <button
            key={mode.id}
            className={`mode ${view === mode.id ? "mode-on" : ""}`}
            role="tab"
            aria-selected={view === mode.id}
            onClick={() => setView(mode.id)}
          >
            <span className="mode-name">{mode.name}</span>
            <span className="mode-what">{mode.what}</span>
          </button>
        ))}
      </nav>

      {showSettings && settings && <SettingsPanel
          settings={settings}
          onSaved={setSettings}
          onHistoryCleared={refreshHistory}
        />}

      {view === "library" && (
        <LibraryPanel onQueued={adoptJobs} onOpenSettings={() => setShowSettings(true)} />
      )}

      {view === "links" && (
      <form className="intake" onSubmit={onSubmit}>
        <input
          className="input"
          placeholder={
            settings?.auto_download
              ? "Paste a link — it downloads on its own"
              : "Paste a link, a playlist, or several at once"
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
      )}

      <div className="stack">
        {view === "links" && pending && (
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

            <FormatPicker
              formats={BATCH_QUALITIES}
              value={batchFormat}
              onChange={setBatchFormat}
            />

            <div className="batch-actions">
              <button className="btn" onClick={() => setPending(null)}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={() => runBatch(pending.urls, batchFormat, pending.titles)}
              >
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

        {view === "links" && info && (
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

        {/* With nothing in flight there is nothing to read, so the space says what
            the thing can do instead. It yields the moment real work appears. */}
        {view === "links" && idle && (
          <section className="panel guide">
            <span className="eyebrow">What goes in the box</span>
            <ul className="guide-list">
              <li>
                <span className="guide-key">Any link</span>
                <span>
                  YouTube, Instagram and Threads are built and tested. Everything else is
                  passed to yt-dlp, which knows a thousand other sites — worth a try, not a
                  promise.
                </span>
              </li>
              <li>
                <span className="guide-key">Several links</span>
                <span>
                  Paste a whole block of them. You get one count, one quality for the lot, and a
                  confirm step, so a stray paste never starts anything.
                </span>
              </li>
              <li>
                <span className="guide-key">A playlist</span>
                <span>
                  Paste its URL and it is listed without touching a single video, up to 200
                  items. Queue the ones you want.
                </span>
              </li>
              <li>
                <span className="guide-key">Audio only</span>
                <span>
                  Pick <em>Audio</em> in the quality ladder after analyzing. Title, artist, date,
                  chapters and cover art are embedded either way.
                </span>
              </li>
              <li>
                <span className="guide-key">Signed-in pages</span>
                <span>
                  Threads always needs a session and Instagram sometimes does. Choose the browser
                  to borrow cookies from in <button className="link" onClick={() => setShowSettings(true)}>Settings</button>, alongside
                  subtitles and paste-to-download.
                </span>
              </li>
            </ul>
          </section>
        )}

        {/* One download keeps the full instrument readout; a queue gets rows. */}
        {jobs.length > 0 &&
          (singleJob ? (
            <JobProgress job={singleJob} onCancel={onCancel} onRetry={onRetry} />
          ) : (
            <QueueList
              jobs={jobs}
              onCancel={onCancel}
              onCancelAll={onCancelAll}
              onRetry={onRetry}
              onClear={onClearQueue}
            />
          ))}
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
