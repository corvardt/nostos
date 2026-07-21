import { useState } from "react";
import * as api from "../lib/api";
import type { Settings } from "../lib/types";

const BROWSERS = ["", "firefox", "chrome", "chromium", "brave", "edge", "opera", "vivaldi", "safari"];

interface Props {
  settings: Settings;
  onSaved: (settings: Settings) => void;
}

export default function SettingsPanel({ settings, onSaved }: Props) {
  const [draft, setDraft] = useState<Settings>(settings);
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setNote(null);
    try {
      onSaved(await api.putSettings(draft));
      setNote("Saved");
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Settings did not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="panel settings">
      <label className="field">
        <span className="field-label">Download folder</span>
        <input
          className="input mono-input"
          value={draft.download_dir}
          spellCheck={false}
          onChange={(e) => setDraft({ ...draft, download_dir: e.target.value })}
        />
        <p className="field-help">Where files land on this machine.</p>
      </label>

      <label className="field">
        <span className="field-label">Signed in with</span>
        <select
          className="select"
          value={draft.cookies_from_browser}
          onChange={(e) => setDraft({ ...draft, cookies_from_browser: e.target.value })}
        >
          {BROWSERS.map((b) => (
            <option key={b} value={b}>
              {b === "" ? "No browser (anonymous)" : b}
            </option>
          ))}
        </select>
        <p className="field-help">
          Instagram and Threads read your session from this browser. Threads needs it for every
          post; YouTube never does.
        </p>
      </label>

      <div className="field">
        <label className="toggle">
          <input
            type="checkbox"
            checked={draft.auto_download}
            onChange={(e) => setDraft({ ...draft, auto_download: e.target.checked })}
          />
          <span className="field-label">Download on paste</span>
        </label>
        <p className="field-help">
          Pasting a link analyzes it and starts the download at the highest quality, with no
          further clicks. Typing a link still waits for you to press Analyze.
        </p>
      </div>

      <label className="field">
        <span className="field-label">Subtitle languages</span>
        <input
          className="input mono-input"
          value={draft.subtitle_langs}
          placeholder="en, fr"
          spellCheck={false}
          onChange={(e) => setDraft({ ...draft, subtitle_langs: e.target.value })}
        />
        <p className="field-help">
          Comma-separated language codes, embedded into the file. Leave empty for no subtitles.
          Titles, cover art and chapters are always embedded.
        </p>
      </label>

      {settings.db_path && (
        <div className="field">
          <span className="field-label">History database</span>
          <p className="field-help mono-input">{settings.db_path}</p>
          <p className="field-help">
            Every download is recorded here, in the <code>history</code> table.
          </p>
        </div>
      )}

      <div className="settings-foot">
        <button className="btn" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        {note && <span className="field-help">{note}</span>}
      </div>
    </div>
  );
}
