import type { Format } from "./types";

const HEIGHTS = [2160, 1440, 1080, 720, 480, 360];

/** Quality choices for a mixed queue.
 *
 * A queue has no single format ladder, because its items do not share one: a
 * Short caps at 1080p while a film offers 4K. These are height-*capped*
 * selectors, so each item gets the best it has at or below the cap, and one
 * that has nothing higher simply gets its best. Hence "up to", not "1080p".
 */
export const BATCH_QUALITIES: Format[] = [
  { id: "best", label: "Best available", ext: null, height: null, filesize: null, kind: "video" },
  ...HEIGHTS.map<Format>((h) => ({
    id: `bv*[height<=${h}]+ba/b[height<=${h}]`,
    label: `Up to ${h}p`,
    ext: "mp4",
    height: h,
    filesize: null,
    kind: "video",
  })),
  {
    id: "ba[ext=m4a]/ba/b",
    label: "Audio only",
    ext: "m4a",
    height: null,
    filesize: null,
    kind: "audio",
  },
];
