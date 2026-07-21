import type { HistoryEntry } from "../lib/types";

/** "2026-07-21 14:16:31" -> "21 Jul 16:16" in local reading order. */
function shortTime(stamp: string): string {
  const parsed = new Date(stamp.replace(" ", "T") + "Z");
  if (Number.isNaN(parsed.getTime())) return stamp;
  return parsed.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function HistoryList({ entries }: { entries: HistoryEntry[] }) {
  if (entries.length === 0) {
    return <p className="empty">Nothing downloaded yet. Paste a link above to start.</p>;
  }

  return (
    <ul className="rows">
      {entries.map((e) => (
        <li key={e.id} className="row">
          <span
            className={`row-status row-${e.status}`}
            title={e.status === "done" ? "Downloaded" : "Failed"}
          />
          {/* The title links back to the post it came from. */}
          <a
            className="row-title"
            href={e.url}
            target="_blank"
            rel="noreferrer noopener"
            title={e.url}
          >
            {e.title ?? e.url}
          </a>
          <span className="row-meta">{e.platform}</span>
          <span className="row-meta">{shortTime(e.created_at)}</span>
        </li>
      ))}
    </ul>
  );
}
