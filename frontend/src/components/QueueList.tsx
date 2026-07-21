import type { Job } from "../lib/types";

function label(job: Job): string {
  return job.title ?? job.url.replace(/^https?:\/\/(www\.)?/, "");
}

export default function QueueList({ jobs }: { jobs: Job[] }) {
  const done = jobs.filter((j) => j.status === "done").length;
  const failed = jobs.filter((j) => j.status === "error").length;

  return (
    <div className="panel">
      <div className="transfer-head">
        <span className="eyebrow">Queue</span>
        <span className="queue-tally">
          {done}/{jobs.length}
          {failed > 0 && <span className="queue-failed"> · {failed} failed</span>}
        </span>
      </div>

      <ul className="queue">
        {jobs.map((job) => (
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
            <span className="queue-state">
              {job.status === "running"
                ? `${job.progress.toFixed(0)}%`
                : job.status === "done"
                  ? "done"
                  : job.status === "error"
                    ? "failed"
                    : "queued"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
