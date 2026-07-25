import { useState } from "react";
import type { SourceConfig, SourceType } from "../lib/types";

/** What each source type needs, in the order it makes sense to fill in.
 *
 *  Kept here rather than generated from the backend because the *explanation*
 *  is the useful part - where a token comes from matters more than its name,
 *  and a schema cannot carry that.
 */
interface FieldSpec {
  key: string;
  label: string;
  help?: string;
  kind?: "text" | "password" | "boolean" | "list";
  placeholder?: string;
}

const FIELDS: Record<string, FieldSpec[]> = {
  apple: [
    {
      key: "developer_token",
      label: "Developer token",
      kind: "password",
      help: "From music.apple.com while signed in: the Authorization header, minus 'Bearer '. Short-lived.",
    },
    {
      key: "user_token",
      label: "Music user token",
      kind: "password",
      help: "The Music-User-Token header from the same request. Lasts about six months.",
    },
    { key: "storefront", label: "Storefront", placeholder: "us", help: "Your country code." },
    { key: "library_songs", label: "Include my whole library", kind: "boolean" },
    {
      key: "playlists",
      label: "Playlist ids",
      kind: "list",
      help: "Comma-separated. Ids starting with p. are your own playlists.",
    },
  ],
  spotify: [
    {
      key: "client_id",
      label: "Client id",
      kind: "password",
      help: "Register an app at developer.spotify.com. Free, and takes a minute.",
    },
    { key: "client_secret", label: "Client secret", kind: "password" },
    {
      key: "liked",
      label: "Include Liked Songs",
      kind: "boolean",
      help: "Opens a browser once to authorise, then remembers.",
    },
    { key: "user_playlists", label: "Include all my playlists", kind: "boolean" },
    { key: "playlists", label: "Extra playlist ids or URLs", kind: "list" },
  ],
  deezer: [
    {
      key: "arl",
      label: "arl cookie",
      kind: "password",
      help: "Only needed for your own private favourites. From deezer.com: Application > Cookies > arl.",
    },
    { key: "favorites", label: "Include my favourites", kind: "boolean" },
    { key: "user_id", label: "Public profile id", help: "An alternative to the arl, for a public profile." },
    { key: "playlists", label: "Playlist ids or URLs", kind: "list" },
    {
      key: "fetch_isrc",
      label: "Fetch ISRCs",
      kind: "boolean",
      help: "One extra request per track. Slow, but makes merging with Spotify and Apple exact.",
    },
  ],
  youtube: [
    { key: "playlists", label: "Playlist URLs", kind: "list", placeholder: "https://music.youtube.com/playlist?list=…" },
    {
      key: "use_cookies",
      label: "Use browser cookies",
      kind: "boolean",
      help: "Needed for private playlists. Uses the browser chosen in Settings.",
    },
    {
      key: "resolve_metadata",
      label: "Fetch full metadata",
      kind: "boolean",
      help: "Much slower, but gets real artist and album fields instead of guessing from the title.",
    },
  ],
  json: [
    { key: "path", label: "File path", placeholder: "/home/you/tracks.json", help: "A JSON list of {title, artist, album}." },
  ],
};

interface Props {
  types: SourceType[];
  /** Which service the form opens on, when it was reached from a named one. */
  initialType?: string;
  onAdd: (source: SourceConfig) => Promise<void>;
  onCancel: () => void;
}

export default function SourceForm({ types, initialType, onAdd, onCancel }: Props) {
  const [type, setType] = useState(initialType ?? types[0]?.type ?? "spotify");
  const [label, setLabel] = useState("");
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fields = FIELDS[type] ?? [];

  function set(key: string, value: unknown) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  async function submit() {
    setBusy(true);
    setError(null);
    // Drop anything left blank so the backend sees an absent option rather
    // than an empty one, which it would treat as configured-but-empty.
    const options = Object.fromEntries(
      Object.entries(values).filter(([, v]) => v !== "" && v !== false && v !== undefined),
    );
    try {
      await onAdd({ type, label: label.trim() || type, enabled: true, options });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add that source.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel source-form">
      <label className="field">
        <span className="field-label">Service</span>
        <select
          className="select"
          value={type}
          onChange={(e) => {
            setType(e.target.value);
            setValues({});
          }}
        >
          {types.map((t) => (
            <option key={t.type} value={t.type}>
              {t.description}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span className="field-label">Name</span>
        <input
          className="input"
          value={label}
          placeholder={type}
          onChange={(e) => setLabel(e.target.value)}
        />
        <p className="field-help">What to call it in the list. Any name you like.</p>
      </label>

      {fields.map((field) =>
        field.kind === "boolean" ? (
          <div className="field" key={field.key}>
            <label className="toggle">
              <input
                type="checkbox"
                checked={Boolean(values[field.key])}
                onChange={(e) => set(field.key, e.target.checked)}
              />
              <span className="field-label">{field.label}</span>
            </label>
            {field.help && <p className="field-help">{field.help}</p>}
          </div>
        ) : (
          <label className="field" key={field.key}>
            <span className="field-label">{field.label}</span>
            <input
              className="input mono-input"
              type={field.kind === "password" ? "password" : "text"}
              value={String(values[field.key] ?? "")}
              placeholder={field.placeholder}
              spellCheck={false}
              autoComplete="off"
              onChange={(e) =>
                set(
                  field.key,
                  field.kind === "list"
                    ? e.target.value.split(",").map((s) => s.trim()).filter(Boolean)
                    : e.target.value,
                )
              }
            />
            {field.help && <p className="field-help">{field.help}</p>}
          </label>
        ),
      )}

      {error && <p className="field-help">{error}</p>}

      <div className="settings-foot">
        <button className="btn btn-primary" onClick={submit} disabled={busy}>
          {busy ? "Adding…" : "Add source"}
        </button>
        <button className="link" onClick={onCancel}>
          Cancel
        </button>
        <span className="field-help">Credentials stay in the local database on this machine.</span>
      </div>
    </div>
  );
}
