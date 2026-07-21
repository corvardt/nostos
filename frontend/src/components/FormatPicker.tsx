import type { Format } from "../lib/types";

function humanSize(bytes: number | null): string | null {
  if (!bytes) return null;
  const mb = bytes / 1024 / 1024;
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`;
}

interface Props {
  formats: Format[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

/** The resolution ladder genuinely is a ladder, so it reads as one rather than
 *  hiding inside a dropdown - and it keeps downloading to a single click. */
export default function FormatPicker({ formats, value, onChange, disabled }: Props) {
  if (formats.length === 0) return null;

  return (
    <div>
      <span className="eyebrow">Quality</span>
      <div className="ladder" role="group" aria-label="Quality">
        {formats.map((f) => {
          const size = humanSize(f.filesize);
          return (
            <button
              key={f.id}
              type="button"
              className="rung"
              aria-pressed={f.id === value}
              disabled={disabled}
              onClick={() => onChange(f.id)}
            >
              {f.label}
              {size && <span className="rung-size">{size}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
