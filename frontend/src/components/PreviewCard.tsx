import type { MediaInfo } from "../lib/types";

function formatDuration(seconds: number | null): string | null {
  if (!seconds) return null;
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

export default function PreviewCard({ info }: { info: MediaInfo }) {
  const duration = formatDuration(info.duration);

  return (
    <div className="panel preview">
      {info.thumbnail && (
        <div className="thumb-wrap">
          {/* Referrer stripped: the CDNs 403 thumbnails on cross-origin referrers. */}
          <img
            className={`thumb${info.is_image ? " thumb-square" : ""}`}
            src={info.thumbnail}
            alt=""
            referrerPolicy="no-referrer"
          />
          {duration && <span className="duration">{duration}</span>}
        </div>
      )}

      <div className="preview-body">
        <div className="source">
          <span className="source-dot" />
          <span className="eyebrow">{info.platform}</span>
          {info.is_image && <span className="eyebrow">· image</span>}
          {info.is_live && <span className="eyebrow live">· live</span>}
        </div>
        <h2 className="preview-title">{info.title}</h2>
        {info.author && <p className="preview-author">{info.author}</p>}
        {info.already_downloaded && (
          <p className="hint dup">
            Already downloaded on {info.already_downloaded.slice(0, 10)}. Downloading again will
            make a second copy.
          </p>
        )}
        {info.is_live && (
          <p className="hint">
            Live broadcasts cannot be downloaded until the stream ends.
          </p>
        )}
      </div>
    </div>
  );
}
