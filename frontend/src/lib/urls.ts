/** Pull every http(s) link out of pasted or typed text, de-duplicated. */
export function extractUrls(text: string): string[] {
  const found = text
    .split(/[\s,]+/)
    .map((t) => t.trim().replace(/[)\]},.]+$/, ""))
    .filter((t) => /^https?:\/\/\S+$/i.test(t));
  return [...new Set(found)];
}

/** A playlist page, or a video opened in the context of one. Mirrors
 *  `PLAYLIST_RE` in backend/app/providers/youtube.py. */
export function looksLikePlaylist(url: string): boolean {
  return /youtube\.com\/playlist\?|[?&]list=/i.test(url);
}
