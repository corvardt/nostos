import { useCallback, useEffect, useState } from "react";
import SourceForm from "./SourceForm";
import * as api from "../lib/api";
import type { LibraryStats, LibraryTrack, SourceConfig, SourceType, SyncReport } from "../lib/types";

/** Statuses in the order they tell a story: what is left, what happened, what broke. */
const STATUS_ORDER: Array<{ key: string; label: string }> = [
  { key: "wanted", label: "missing" },
  { key: "queued", label: "queued" },
  { key: "downloaded", label: "downloaded" },
  { key: "owned", label: "on disk" },
  { key: "failed", label: "failed" },
  { key: "skipped", label: "skipped" },
];

/** A row says the same word as the filter chip that selects it. */
const STATUS_LABELS: Record<string, string> = Object.fromEntries(
  STATUS_ORDER.map((s) => [s.key, s.label]),
);

/** The services, named and priced in advance. The dropdown inside the add form
 *  used to be the only place these appeared, which meant you had to already know
 *  the feature existed to discover what it supported. */
const SERVICES: Array<{ type: string; name: string; reads: string; cost: string }> = [
  {
    type: "spotify",
    name: "Spotify",
    reads: "Liked Songs and playlists",
    cost: "a free developer id and secret",
  },
  {
    type: "apple",
    name: "Apple Music",
    reads: "your library and playlists",
    cost: "two tokens from a signed-in web session",
  },
  {
    type: "deezer",
    name: "Deezer",
    reads: "favourites and playlists",
    cost: "nothing, unless the favourites are private",
  },
  {
    type: "youtube",
    name: "YouTube Music",
    reads: "any playlist, Liked Music included",
    cost: "nothing, unless the playlist is private",
  },
  {
    type: "json",
    name: "A JSON file",
    reads: "a tracklist exported elsewhere",
    cost: "nothing",
  },
];

const STEPS: Array<[string, string]> = [
  ["Connect", "One or more of the services below. Credentials never leave this machine."],
  [
    "Collect",
    "Every track from every source, merged into one list. The same song liked on three platforms becomes one entry, matched on the ISRC the services publish.",
  ],
  [
    "Skip",
    "Anything already on disk. Point Settings at the folders you keep music in and a pass only fetches what is genuinely missing.",
  ],
  [
    "Fetch",
    "What is left is matched to a source of audio, scored, and refused rather than guessed at when nothing clearly matches. Then it goes through the same queue as any other download, and is tagged from the service's metadata.",
  ],
];

interface Props {
  /** A sync queues into the same job list the Links view shows. */
  onQueued: (jobIds: string[]) => void;
  /** Music folder, filing layout and format live in Settings, not here. */
  onOpenSettings: () => void;
}

export default function LibraryPanel({ onQueued, onOpenSettings }: Props) {
  const [sources, setSources] = useState<SourceConfig[]>([]);
  const [types, setTypes] = useState<SourceType[]>([]);
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [tracks, setTracks] = useState<LibraryTrack[]>([]);
  const [filter, setFilter] = useState("");
  const [search, setSearch] = useState("");
  /** null while closed; otherwise the service the form should open on. */
  const [adding, setAdding] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [report, setReport] = useState<SyncReport | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [testing, setTesting] = useState<number | null>(null);

  const refresh = useCallback(() => {
    api.getSources().then(setSources).catch(() => {});
    api.getLibraryStats().then(setStats).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    api.getSourceTypes().then(setTypes).catch(() => {});
  }, [refresh]);

  useEffect(() => {
    api
      .getLibraryTracks({ status: filter, search, limit: 300 })
      .then(setTracks)
      .catch(() => {});
  }, [filter, search, stats]);

  async function sync(dryRun: boolean) {
    setSyncing(true);
    setNote(null);
    setReport(null);
    try {
      const result = await api.runSync({ dry_run: dryRun });
      setReport(result);
      if (result.job_ids.length > 0) onQueued(result.job_ids);
      refresh();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "The sync did not run.");
    } finally {
      setSyncing(false);
    }
  }

  async function test(id: number) {
    setTesting(id);
    setNote(null);
    try {
      const result = await api.testSource(id);
      setNote(
        `${result.tracks} tracks found, ${result.with_isrc} with an ISRC.` +
          (result.sample.length ? ` First: ${result.sample[0]}` : ""),
      );
    } catch (err) {
      setNote(err instanceof Error ? err.message : "That source could not be read.");
    } finally {
      setTesting(null);
    }
  }

  async function remove(id: number) {
    await api.deleteSource(id).catch(() => {});
    refresh();
  }

  async function toggle(source: SourceConfig) {
    if (source.id == null) return;
    await api.updateSource(source.id, { ...source, enabled: !source.enabled }).catch(() => {});
    refresh();
  }

  async function retryFailed() {
    const { reset } = await api.retryFailedTracks();
    setNote(`${reset} track${reset === 1 ? "" : "s"} will be tried again on the next sync.`);
    refresh();
  }

  const counts = stats?.counts ?? {};

  const empty = sources.length === 0;

  return (
    <div className="stack">
      {/* Before anything is connected, the whole point has to be on screen: this
          is not a second link box, it is an account-to-disk archiver. */}
      {empty && adding === null && (
        <section className="panel guide">
          <span className="eyebrow">One pass, everything you have</span>
          <p className="guide-lede">
            Connect the services you listen on and Nostos collects every track you have on them,
            works out which ones you are missing, and downloads only those — to real files, tagged,
            filed, and yours.
          </p>
          <ol className="guide-steps">
            {STEPS.map(([name, what], i) => (
              <li key={name}>
                <span className="num">{i + 1}</span>
                <span className="guide-key">{name}</span>
                <span>{what}</span>
              </li>
            ))}
          </ol>
          <p className="field-help">
            A pass is resumable, and safe to repeat: every track's state is remembered, so running
            it again only does what is left.{" "}
            <button className="link" onClick={onOpenSettings}>
              Music folder and filing
            </button>{" "}
            are in Settings.
          </p>
        </section>
      )}

      {adding === null && (
        <section className="panel">
          <div className="ledger-head">
            <span className="eyebrow">What it can read</span>
            <span className="eyebrow">{SERVICES.length} services</span>
          </div>
          <div className="services">
            {SERVICES.map((service) => (
              <div className="service" key={service.type}>
                <div className="service-body">
                  <span className="source-name">{service.name}</span>
                  <span className="field-help">{service.reads}</span>
                  <span className="field-help">Needs: {service.cost}</span>
                </div>
                <button className="link" onClick={() => setAdding(service.type)}>
                  Connect
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="panel library-sources">
        <div className="ledger-head">
          <span className="eyebrow">Connected</span>
          <span className="eyebrow">{sources.length}</span>
        </div>

        {empty && adding === null && (
          <p className="field-help">
            Nothing connected yet. Pick a service above, or press Add a source.
          </p>
        )}

        {sources.map((source) => (
          <div className="source-row" key={source.id}>
            <span className={`source-dot ${source.enabled ? "" : "source-off"}`} />
            <div className="source-body">
              <span className="source-name">{source.label}</span>
              <span className="field-help">{source.type}</span>
            </div>
            <button className="link" onClick={() => test(source.id!)} disabled={testing === source.id}>
              {testing === source.id ? "Checking…" : "Check"}
            </button>
            <button className="link" onClick={() => toggle(source)}>
              {source.enabled ? "Disable" : "Enable"}
            </button>
            <button className="link" onClick={() => remove(source.id!)}>
              Remove
            </button>
          </div>
        ))}

        {adding !== null ? (
          <SourceForm
            types={types}
            initialType={adding || undefined}
            onCancel={() => setAdding(null)}
            onAdd={async (source) => {
              await api.addSource(source);
              setAdding(null);
              refresh();
            }}
          />
        ) : (
          <div className="settings-foot">
            <button className="btn" onClick={() => setAdding("")}>
              Add a source
            </button>
            <button
              className="btn btn-primary"
              onClick={() => sync(false)}
              disabled={syncing || empty}
              title="Collect every track, then download the ones you do not have"
            >
              {syncing ? "Syncing…" : "Sync and download"}
            </button>
            <button
              className="link"
              onClick={() => sync(true)}
              disabled={syncing || empty}
              title="Collect and count, but queue nothing"
            >
              Count what is missing
            </button>
          </div>
        )}

        {note && <p className="field-help">{note}</p>}
      </section>

      {report && (
        <section className="panel">
          <span className="eyebrow">Last pass</span>
          {/* Figures a pass just produced, so they arrive lit and settle. */}
          <div className="report-grid">
            <div><strong className="num settle">{report.collected}</strong><span>collected</span></div>
            <div><strong className="num settle">{report.unique}</strong><span>unique</span></div>
            <div><strong className="num settle">{report.already_owned}</strong><span>on disk</span></div>
            <div><strong className="num settle">{report.already_downloaded}</strong><span>fetched before</span></div>
            <div><strong className="num settle">{report.queued}</strong><span>queued</span></div>
          </div>
          {report.failed_sources.map((failure) => (
            <p className="field-help" key={failure}>
              {failure}
            </p>
          ))}
        </section>
      )}

      {/* An empty ledger below an empty source list is just noise. */}
      {(!empty || tracks.length > 0) && (
      <section className="panel library-tracks">
        <div className="ledger-head">
          <span className="eyebrow">Tracks</span>
          <span className="eyebrow">{stats?.total ?? 0}</span>
        </div>

        <div className="library-filters">
          <button className={`chip ${filter === "" ? "chip-on" : ""}`} onClick={() => setFilter("")}>
            all
          </button>
          {STATUS_ORDER.filter((s) => counts[s.key as keyof typeof counts]).map((status) => (
            <button
              key={status.key}
              className={`chip ${filter === status.key ? "chip-on" : ""}`}
              onClick={() => setFilter(filter === status.key ? "" : status.key)}
            >
              {status.label} <span className="num">{counts[status.key as keyof typeof counts]}</span>
            </button>
          ))}
          <input
            className="input chip-search"
            placeholder="Search"
            value={search}
            spellCheck={false}
            onChange={(e) => setSearch(e.target.value)}
          />
          {(counts.failed ?? 0) > 0 && (
            <button className="link" onClick={retryFailed}>
              Retry failed
            </button>
          )}
        </div>

        {tracks.length === 0 ? (
          <p className="field-help">Nothing here yet. Run a sync to collect your tracks.</p>
        ) : (
          <div className="rows">
            {tracks.map((track) => (
              <div
                className={`row row-${track.status}`}
                key={track.key}
                /* The reason is folded away until asked for: focusable so a
                   click or the keyboard opens it, titled so a rest does too. */
                tabIndex={track.error ? 0 : undefined}
                title={track.error ?? undefined}
              >
                <span className={`queue-dot-${statusDot(track.status)}`} />
                <div className="row-title">
                  <span>{track.artist} — {track.title}</span>
                  {track.error && <span className="row-reason">{track.error}</span>}
                </div>
                {/* A fixed, right-aligned column: the statuses line up against
                    the panel edge instead of ending wherever the title did. */}
                <span className="track-status">{STATUS_LABELS[track.status] ?? track.status}</span>
              </div>
            ))}
            {tracks.length >= 300 && (
              <p className="field-help">Showing the first 300. Use search to narrow it down.</p>
            )}
          </div>
        )}
      </section>
      )}
    </div>
  );
}

/** Reuse the queue's dot colours so a status means the same thing everywhere. */
function statusDot(status: string): string {
  if (status === "downloaded" || status === "owned") return "done";
  if (status === "failed") return "error";
  if (status === "queued") return "running";
  return "queued";
}
