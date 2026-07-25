import { useCallback, useEffect, useState } from "react";

/** Palette token names. The values live in `styles.css` so the stylesheet is
 *  the single source of truth; these are the names, in both places. */
export const TOKENS = ["void", "panel", "line", "land", "dim", "text", "strike"] as const;

export type Theme = "dark" | "light";

// The medium is shared with the rest of unmod.fun, so the choice lives in a
// cookie scoped to the domain rather than in localStorage, which is per-origin
// and would not survive the walk between two projects. On localhost the cookie
// is simply host-scoped and the app keeps its own preference.
const COOKIE_KEY = "unmod-theme";
const STORAGE_KEY = "nostos-theme";

const cookie = (): Theme | null =>
  (document.cookie.match(/(?:^|;\s*)unmod-theme=(dark|light)/)?.[1] as Theme) ?? null;

function write(theme: Theme) {
  const domain = location.hostname.endsWith("unmod.fun") ? "; domain=.unmod.fun" : "";
  document.cookie = `${COOKIE_KEY}=${theme}; path=/; max-age=31536000; samesite=lax${domain}`;
  localStorage.setItem(STORAGE_KEY, theme);
}

// Applied synchronously rather than in an effect: effects run child-first, so a
// child reading computed style would otherwise see the outgoing theme.
function apply(next: Theme): Theme {
  document.documentElement.dataset.theme = next;
  return next;
}

/**
 * Two media, not one palette inverted. Dark is a phosphor tube: light emitted
 * on black. Light is ink on chart paper: marks deposited on stock. The same
 * seven tokens carry both, which is why every rule below can ignore the
 * difference.
 */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(
    () => (document.documentElement.dataset.theme as Theme) || "dark",
  );

  // Follow the system for as long as the reader has not expressed a preference.
  useEffect(() => {
    if (cookie() || localStorage.getItem(STORAGE_KEY)) return;
    const query = matchMedia("(prefers-color-scheme: light)");
    const onChange = () => setTheme(apply(query.matches ? "light" : "dark"));
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const toggle = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === "dark" ? "light" : "dark";
      write(next);
      return apply(next);
    });
  }, []);

  return [theme, toggle];
}
