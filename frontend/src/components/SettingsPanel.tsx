import { useState } from "react";
import * as api from "../lib/api";
import type { Settings } from "../lib/types";

const BROWSERS = ["", "firefox", "chrome", "chromium", "brave", "edge", "opera", "vivaldi", "safari"];

interface Props {
  settings: Settings;
  onSaved: (settings: Settings) => void;
  onHistoryCleared: () => void;
}

export default function SettingsPanel({ settings, onSaved, onHistoryCleared }: Props) {
  const [confirmingClear, setConfirmingClear] = useState(false);
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

  async function clearHistory() {
    try {
      const { cleared } = await api.clearHistory();
      setNote(`Cleared ${cleared} ${cleared === 1 ? "entry" : "entries"}`);
      onHistoryCleared();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "History did not clear.");
    } finally {
      setConfirmingClear(false);
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

      <label className="field">
        <span className="field-label">Music folder</span>
        <input
          className="input mono-input"
          value={draft.music_dir}
          spellCheck={false}
          onChange={(e) => setDraft({ ...draft, music_dir: e.target.value })}
        />
        <p className="field-help">
          Where the Library tab archives songs. Separate from the download folder, so an archive
          does not get mixed in with one-off videos.
        </p>
      </label>

      <label className="field">
        <span className="field-label">Filing</span>
        <select
          className="select"
          value={draft.music_layout}
          onChange={(e) => setDraft({ ...draft, music_layout: e.target.value })}
        >
          <option value="flat">All in one folder</option>
          <option value="artist">One folder per artist</option>
          <option value="artist-album">Artist, then album</option>
        </select>
      </label>

      <label className="field">
        <span className="field-label">Audio format</span>
        <select
          className="select"
          value={draft.music_format}
          onChange={(e) => setDraft({ ...draft, music_format: e.target.value })}
        >
          {["mp3", "m4a", "opus", "flac"].map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
        <p className="field-help">
          Everything here is re-encoded from a compressed source, so flac buys size, not fidelity.
        </p>
      </label>

      <label className="field">
        <span className="field-label">Music you already have</span>
        <textarea
          className="input mono-input"
          rows={3}
          value={draft.music_library_dirs}
          spellCheck={false}
          placeholder={"/home/you/Music/Spotify\n/home/you/Music/Youtube"}
          onChange={(e) => setDraft({ ...draft, music_library_dirs: e.target.value })}
        />
        <p className="field-help">
          One folder per line. Anything matched in these is never downloaded again, whichever
          service it turns up on.
        </p>
      </label>

      <div className="field">
        <label className="toggle">
          <input
            type="checkbox"
            checked={draft.music_use_spotdl}
            onChange={(e) => setDraft({ ...draft, music_use_spotdl: e.target.checked })}
          />
          <span className="field-label">Use spotdl to pick the video</span>
        </label>
        <p className="field-help">
          When spotdl is installed, it matches against Spotify's catalogue first, which picks the
          right video more often than a title search. Ignored if it is not installed.
        </p>
      </div>

      {settings.db_path && (
        <div className="field">
          <span className="field-label">History database</span>
          <p className="field-help mono-input">{settings.db_path}</p>
          <p className="field-help">
            Every download is recorded here, in the <code>history</code> table.
          </p>
          <div className="settings-foot">
            {confirmingClear ? (
              <>
                <button className="btn btn-danger" onClick={clearHistory}>
                  Clear it, permanently
                </button>
                <button className="link" onClick={() => setConfirmingClear(false)}>
                  Keep it
                </button>
              </>
            ) : (
              <button className="btn" onClick={() => setConfirmingClear(true)}>
                Clear history
              </button>
            )}
            <span className="field-help">Downloaded files are not deleted.</span>
          </div>
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
