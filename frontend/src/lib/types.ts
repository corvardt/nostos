// Mirrors backend/app/models.py - keep the two in sync.

export type JobStatus = "queued" | "running" | "done" | "error";

export interface Format {
  id: string;
  label: string;
  ext: string | null;
  height: number | null;
  filesize: number | null;
  kind: "video" | "audio" | "image";
}

export interface MediaInfo {
  platform: string;
  title: string;
  author: string | null;
  thumbnail: string | null;
  duration: number | null;
  is_image: boolean;
  is_live: boolean;
  webpage_url: string | null;
  formats: Format[];
}

export interface Job {
  id: string;
  url: string;
  platform: string | null;
  title: string | null;
  status: JobStatus;
  progress: number;
  speed: string | null;
  eta: number | null;
  downloaded_bytes: number | null;
  total_bytes: number | null;
  filepath: string | null;
  error: string | null;
}

export interface PlaylistEntry {
  url: string;
  title: string | null;
  thumbnail: string | null;
}

export interface Playlist {
  title: string;
  count: number;
  entries: PlaylistEntry[];
  truncated: boolean;
}

export interface BatchItem {
  url: string;
  jobId: string | null;
  error: string | null;
}

export interface BatchResponse {
  accepted: number;
  rejected: number;
  items: BatchItem[];
}

export interface HistoryEntry {
  id: number;
  url: string;
  platform: string | null;
  title: string | null;
  status: string;
  filepath: string | null;
  created_at: string;
}

export interface Settings {
  download_dir: string;
  cookies_from_browser: string;
  /** Pasting a link analyzes and downloads it at best quality, with no clicks. */
  auto_download: boolean;
  /** Where the history database lives. Read-only - the server sets it. */
  db_path?: string;
}
