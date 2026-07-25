// Mirrors backend/app/models.py - keep the two in sync.

export type JobStatus = "queued" | "running" | "done" | "error" | "cancelled";

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
  /** Set when this URL was already downloaded and the file is still present. */
  already_downloaded: string | null;
  webpage_url: string | null;
  formats: Format[];
}

export interface Job {
  id: string;
  url: string;
  /** Kept so a failed or stopped job can be retried as first asked for. */
  format: string | null;
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
  skipped: boolean;
}

export interface BatchResponse {
  accepted: number;
  rejected: number;
  skipped: number;
  items: BatchItem[];
}

export interface HistoryEntry {
  id: number;
  url: string;
  platform: string | null;
  title: string | null;
  status: string;
  filepath: string | null;
  error: string | null;
  created_at: string;
}

export interface Settings {
  download_dir: string;
  cookies_from_browser: string;
  /** Pasting a link analyzes and downloads it at best quality, with no clicks. */
  auto_download: boolean;
  /** Comma-separated language codes, e.g. "en,fr". Empty disables subtitles. */
  subtitle_langs: string;
  /** Where the history database lives. Read-only - the server sets it. */
  db_path?: string;

  // --- library sync ---
  /** Where archived music lands. Kept apart from download_dir on purpose. */
  music_dir: string;
  /** flat | artist | artist-album */
  music_layout: string;
  music_format: string;
  /** Folders you already keep music in, one per line. Never re-downloaded. */
  music_library_dirs: string;
  /** Let spotdl choose the video when it is installed. */
  music_use_spotdl: boolean;
}

// --------------------------------------------------------------------- library

export type TrackStatus =
  | "wanted"
  | "queued"
  | "downloaded"
  | "owned"
  | "failed"
  | "skipped";

export interface SourceType {
  type: string;
  description: string;
  secrets: string[];
}

export interface SourceConfig {
  id?: number;
  type: string;
  label: string;
  enabled: boolean;
  /** Secrets come back from the server masked as "********". */
  options: Record<string, unknown>;
}

export interface LibraryTrack {
  key: string;
  title: string;
  artist: string;
  album: string;
  isrc: string;
  duration_s: number;
  status: TrackStatus;
  filepath: string | null;
  job_id: string | null;
  error: string | null;
  sources: string[];
  playlists: string[];
  updated_at: string;
}

export interface SyncReport {
  collected: number;
  unique: number;
  already_owned: number;
  already_downloaded: number;
  queued: number;
  failed_sources: string[];
  job_ids: string[];
}

export interface LibraryStats {
  counts: Partial<Record<TrackStatus, number>>;
  total: number;
  sources: number;
  music_dir: string;
}

export interface SourceTestResult {
  ok: boolean;
  tracks: number;
  with_isrc: number;
  sample: string[];
}
