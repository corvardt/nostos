// The single boundary between the UI and the backend.
//
// Components must never call fetch() directly. When this app is wrapped in Tauri,
// only the bodies below change (HTTP -> `invoke()`), and no component is touched.

import type {
  BatchResponse,
  HistoryEntry,
  Job,
  LibraryStats,
  LibraryTrack,
  MediaInfo,
  Playlist,
  Settings,
  SourceConfig,
  SourceTestResult,
  SourceType,
  SyncReport,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  /** 422 means the platform wants cookies - the UI points the user at Settings. */
  needsAuth: boolean;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.needsAuth = status === 422;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError("Cannot reach the Nostos backend. Is it running on port 8000?", 0);
  }

  if (!res.ok) {
    const detail = await res
      .json()
      .then((body) => body?.detail)
      .catch(() => null);
    throw new ApiError(
      typeof detail === "string" ? detail : `Request failed (${res.status})`,
      res.status,
    );
  }
  return res.json() as Promise<T>;
}

export const analyze = (url: string) =>
  request<MediaInfo>("/analyze", { method: "POST", body: JSON.stringify({ url }) });

export const download = (url: string, format: string) =>
  request<{ status: string; jobId: string }>("/download", {
    method: "POST",
    body: JSON.stringify({ url, format }),
  });

export const expand = (url: string) =>
  request<Playlist>("/expand", { method: "POST", body: JSON.stringify({ url }) });

export const downloadBatch = (
  urls: string[],
  format: string,
  titles: Record<string, string> = {},
) =>
  request<BatchResponse>("/download/batch", {
    method: "POST",
    body: JSON.stringify({ urls, format, titles }),
  });

export const getJob = (id: string) => request<Job>(`/jobs/${id}`);

export const cancelJob = (id: string) =>
  request<{ cancelled: boolean }>(`/jobs/${id}`, { method: "DELETE" });

export const retryJob = (id: string) =>
  request<{ status: string; jobId: string }>(`/jobs/${id}/retry`, { method: "POST" });

export const cancelAll = () =>
  request<{ cancelled: number }>("/jobs", { method: "DELETE" });

export const getHistory = () => request<HistoryEntry[]>("/history");

export const clearHistory = () =>
  request<{ cleared: number }>("/history", { method: "DELETE" });

export const getSettings = () => request<Settings>("/settings");

export const putSettings = (settings: Settings) =>
  request<Settings>("/settings", { method: "PUT", body: JSON.stringify(settings) });

// --------------------------------------------------------------------- library

export const getSourceTypes = () => request<SourceType[]>("/library/source-types");

export const getSources = () => request<SourceConfig[]>("/library/sources");

export const addSource = (source: SourceConfig) =>
  request<SourceConfig>("/library/sources", { method: "POST", body: JSON.stringify(source) });

export const updateSource = (id: number, source: SourceConfig) =>
  request<SourceConfig>(`/library/sources/${id}`, {
    method: "PUT",
    body: JSON.stringify(source),
  });

export const deleteSource = (id: number) =>
  request<{ deleted: boolean }>(`/library/sources/${id}`, { method: "DELETE" });

/** Check one source's credentials before committing to a full pass. */
export const testSource = (id: number) =>
  request<SourceTestResult>(`/library/sources/${id}/test`, { method: "POST" });

export const runSync = (options: { dry_run?: boolean; retry_failed?: boolean; limit?: number } = {}) =>
  request<SyncReport>("/library/sync", { method: "POST", body: JSON.stringify(options) });

export const getLibraryTracks = (params: { status?: string; search?: string; limit?: number } = {}) => {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.search) query.set("search", params.search);
  query.set("limit", String(params.limit ?? 200));
  return request<LibraryTrack[]>(`/library/tracks?${query}`);
};

export const getLibraryStats = () => request<LibraryStats>("/library/stats");

export const retryFailedTracks = () =>
  request<{ reset: number }>("/library/tracks/retry-failed", { method: "POST" });
