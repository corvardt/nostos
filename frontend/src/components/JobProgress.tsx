import type { Job } from "../lib/types";

function bytes(n: number | null): string | null {
  if (!n) return null;
  const mb = n / 1024 / 1024;
  return mb >= 1024 ? `${(mb / 1024).toFixed(2)} GB` : `${mb.toFixed(1)} MB`;
}

export default function JobProgress({
  job,
  onCancel,
  onRetry,
}: {
  job: Job;
  onCancel: (id: string) => void;
  onRetry: (id: string) => void;
}) {
  if (job.status === "cancelled") {
    return (
      <div className="panel outcome">
        <div className="outcome-body">
          <span className="outcome-label">Stopped</span>
          <p className="outcome-msg">Download cancelled.</p>
          <button className="link" onClick={() => onRetry(job.id)}>
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (job.status === "error") {
    return (
      <div className="panel panel-bad outcome">
        <div className="outcome-body">
          <span className="outcome-label">Failed</span>
          <p className="outcome-msg">{job.error ?? "The download did not finish."}</p>
          <button className="link" onClick={() => onRetry(job.id)}>
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (job.status === "done") {
    return (
      <div className="panel panel-ok outcome">
        <div className="outcome-body">
          <span className="outcome-label">Downloaded</span>
          <p className="filepath">{job.filepath}</p>
        </div>
      </div>
    );
  }

  const running = job.status === "running";
  const moved = bytes(job.downloaded_bytes);
  const total = bytes(job.total_bytes);

  return (
    <div className={`panel${running ? "" : " transfer-idle"}`}>
      <div className="transfer-head">
        <span className="eyebrow">{running ? "Transferring" : "Starting"}</span>
        <span className="queue-head-right">
          <span className="transfer-pct">{job.progress.toFixed(0)}%</span>
          <button className="link" onClick={() => onCancel(job.id)}>
            Stop
          </button>
        </span>
      </div>

      <div
        className="track"
        role="progressbar"
        aria-valuenow={Math.round(job.progress)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="track-fill" style={{ width: `${Math.max(job.progress, 2)}%` }} />
      </div>

      <div className="readout">
        <span>{moved && total ? `${moved} of ${total}` : moved ?? "-"}</span>
        <span>{job.speed ?? "-"}</span>
        <span>{job.eta ? `${job.eta}s left` : "-"}</span>
      </div>
    </div>
  );
}
