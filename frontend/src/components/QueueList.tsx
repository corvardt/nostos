import type { Job } from "../lib/types";

function label(job: Job): string {
  return job.title ?? job.url.replace(/^https?:\/\/(www\.)?/, "");
}

function stateText(job: Job): string {
  switch (job.status) {
    case "running":
      return `${job.progress.toFixed(0)}%`;
    case "done":
      return "done";
    case "error":
      return "failed";
    case "cancelled":
      return "stopped";
    default:
      return "queued";
  }
}

interface Props {
  jobs: Job[];
  onCancel: (id: string) => void;
  onCancelAll: () => void;
  onRetry: (id: string) => void;
  onClear: () => void;
}

export default function QueueList({ jobs, onCancel, onCancelAll, onRetry, onClear }: Props) {
  const active = jobs.filter((j) => j.status === "queued" || j.status === "running");
  const stalled = jobs.filter((j) => j.status === "error" || j.status === "cancelled");

  return (
    <div className="panel">
      <div className="transfer-head">
        <span className="eyebrow">
          {active.length > 0 ? "Queue" : stalled.length > 0 ? "Unfinished" : "Queue"}
        </span>
        <span className="queue-head-right">
          <span className="queue-tally">
            {active.length > 0 && `${active.length} left`}
            {active.length > 0 && stalled.length > 0 && " · "}
            {stalled.length > 0 && <span className="queue-failed">{stalled.length} unfinished</span>}
          </span>
          {stalled.length > 1 && (
            <button className="link" onClick={() => stalled.forEach((j) => onRetry(j.id))}>
              Retry all
            </button>
          )}
          {active.length > 0 && (
            <button className="link" onClick={onCancelAll}>
              Stop all
            </button>
          )}
          <button className="link" onClick={onClear} title="Stop everything and empty the queue">
            Clear
          </button>
        </span>
      </div>

      <ul className="queue">
        {jobs.map((job) => {
          const stoppable = job.status === "queued" || job.status === "running";
          const retryable = job.status === "error" || job.status === "cancelled";
          return (
            <li key={job.id} className="queue-item">
              <span className={`row-status queue-dot-${job.status}`} title={job.status} />
              <span className="queue-title" title={job.error ?? job.filepath ?? job.url}>
                {label(job)}
              </span>
              {job.status === "running" && (
                <span className="queue-bar">
                  <span className="queue-fill" style={{ width: `${Math.max(job.progress, 2)}%` }} />
                </span>
              )}
              <span className="queue-state">{stateText(job)}</span>
              {retryable && (
                <button className="queue-action" onClick={() => onRetry(job.id)}>
                  Retry
                </button>
              )}
              {stoppable && (
                <button
                  className="queue-stop"
                  onClick={() => onCancel(job.id)}
                  title="Stop this download"
                  aria-label={`Stop ${label(job)}`}
                >
                  ×
                </button>
              )}
            </li>
          );
        })}
      </ul>

      {stalled.length > 0 && active.length === 0 && (
        <p className="queue-note">
          Finished downloads have cleared. These did not complete.
        </p>
      )}
    </div>
  );
}
