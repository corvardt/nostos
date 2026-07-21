// The single boundary between the UI and the backend.
//
// Components must never call fetch() directly. When this app is wrapped in Tauri,
// only the bodies below change (HTTP -> `invoke()`), and no component is touched.

import type { BatchResponse, HistoryEntry, Job, MediaInfo, Playlist, Settings } from "./types";

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

export const downloadBatch = (urls: string[], format: string) =>
  request<BatchResponse>("/download/batch", {
    method: "POST",
    body: JSON.stringify({ urls, format }),
  });

export const getJob = (id: string) => request<Job>(`/jobs/${id}`);

export const getHistory = () => request<HistoryEntry[]>("/history");

export const getSettings = () => request<Settings>("/settings");

export const putSettings = (settings: Settings) =>
  request<Settings>("/settings", { method: "PUT", body: JSON.stringify(settings) });
