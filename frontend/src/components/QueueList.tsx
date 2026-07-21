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
}

export default function QueueList({ jobs, onCancel, onCancelAll }: Props) {
  const done = jobs.filter((j) => j.status === "done").length;
  const failed = jobs.filter((j) => j.status === "error").length;
  const active = jobs.filter((j) => j.status === "queued" || j.status === "running");

  return (
    <div className="panel">
      <div className="transfer-head">
        <span className="eyebrow">Queue</span>
        <span className="queue-head-right">
          <span className="queue-tally">
            {done}/{jobs.length}
            {failed > 0 && <span className="queue-failed"> · {failed} failed</span>}
          </span>
          {active.length > 0 && (
            <button className="link" onClick={onCancelAll}>
              Stop all
            </button>
          )}
        </span>
      </div>

      <ul className="queue">
        {jobs.map((job) => {
          const stoppable = job.status === "queued" || job.status === "running";
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
    </div>
  );
}
