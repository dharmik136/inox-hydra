import { useEffect, useState } from "react";
import { fetchRecordSetup, setRecordSetupField, type RecordSetupField } from "@/lib/api";

/**
 * Three optional questions for From your record: what you want to write
 * about, who you write for, and what the studio should never suggest.
 *
 * Each says why it is asked and can be skipped, which is what first-launch
 * questions need (a short list, the reason, a way past). An answer is an ask
 * like any other: kept on What the studio knows, editable there, used from
 * tomorrow's cards, and sent nowhere unless the model stage is on.
 */
const FIELDS: { field: RecordSetupField; label: string; why: string; placeholder: string }[] = [
  {
    field: "topics",
    label: "What do you want to write about?",
    why: "Your cards match these words to your own posts.",
    placeholder: "hiring without a recruiter, pricing for small studios",
  },
  {
    field: "audience",
    label: "Who do you write for?",
    why: "Only your own model is told this, and only if you switch its stage on.",
    placeholder: "founders of two to ten person agencies",
  },
  {
    field: "avoid",
    label: "What should the studio never suggest?",
    why: "Your own model is told never to suggest it.",
    placeholder: "listicles, anything about crypto",
  },
];

export function RecordSetupFields({ heading = true }: { heading?: boolean }) {
  const [values, setValues] = useState<Record<RecordSetupField, string>>({ topics: "", audience: "", avoid: "" });
  const [saved, setSaved] = useState<Record<RecordSetupField, string>>({ topics: "", audience: "", avoid: "" });
  const [skipped, setSkipped] = useState<Set<RecordSetupField>>(new Set());
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetchRecordSetup()
      .then((fields) => {
        const read = { topics: fields.topics ?? "", audience: fields.audience ?? "", avoid: fields.avoid ?? "" };
        setValues(read);
        setSaved(read);
      })
      .catch(() => setFailed(true));
  }, []);

  async function save(field: RecordSetupField) {
    try {
      await setRecordSetupField(field, values[field]);
      setSaved((current) => ({ ...current, [field]: values[field] }));
      setNote({ text: values[field].trim() ? "Kept. It shapes tomorrow's cards." : "Cleared.", error: false });
    } catch (error) {
      setNote({ text: error instanceof Error ? error.message : "That was not kept.", error: true });
    }
  }

  if (failed) {
    return <p className="studio-meta text-[10px] text-ink-muted">THESE QUESTIONS COULD NOT BE READ. IS THE STUDIO RUNNING?</p>;
  }

  return (
    <section aria-labelledby={heading ? "record-setup-title" : undefined}>
      {heading && (
        <p id="record-setup-title" className="studio-label mb-1">
          What you want from your record (optional)
        </p>
      )}
      <p className="mb-2 max-w-[62ch] text-[12px] leading-snug text-ink-secondary">
        Each answer is kept in this studio only, listed on From your record&rsquo;s What the studio knows page, and can be
        changed or removed there. Skip any of them.
      </p>
      <div className="flex flex-col gap-3">
        {FIELDS.map(({ field, label, why, placeholder }) =>
          skipped.has(field) ? (
            <p key={field} className="text-[12px] text-ink-muted">
              {label} Skipped.{" "}
              <button type="button" className="underline underline-offset-2 hover:text-ink-primary" onClick={() => setSkipped((s) => {
                const next = new Set(s);
                next.delete(field);
                return next;
              })}>
                Answer it after all
              </button>
            </p>
          ) : (
            <div key={field}>
              <label htmlFor={`record-setup-${field}`} className="text-[13px] text-ink-primary">
                {label}
              </label>
              <p className="text-[11px] text-ink-muted">{why}</p>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <input
                  id={`record-setup-${field}`}
                  value={values[field]}
                  maxLength={2000}
                  placeholder={placeholder}
                  onChange={(event) => setValues((current) => ({ ...current, [field]: event.target.value }))}
                  className="min-w-[16rem] flex-1 rounded-md border border-edge bg-ink px-2 py-1 text-[13px] text-ink-primary placeholder:text-ink-muted"
                />
                <button
                  type="button"
                  disabled={values[field] === saved[field]}
                  onClick={() => void save(field)}
                  className="rounded-md border border-edge px-2 py-1 text-[12px] text-ink-secondary transition-colors hover:text-ink-primary disabled:opacity-60"
                >
                  Keep this
                </button>
                {!saved[field] && (
                  <button
                    type="button"
                    onClick={() => setSkipped((s) => new Set(s).add(field))}
                    className="px-1 py-1 text-[12px] text-ink-muted underline underline-offset-2 hover:text-ink-primary"
                  >
                    Skip
                  </button>
                )}
              </div>
            </div>
          ),
        )}
      </div>
      {note && (
        <p role="status" className={note.error ? "mt-2 text-[12px] text-signal-orange-text" : "mt-2 text-[12px] text-ink-muted"}>
          {note.text}
        </p>
      )}
    </section>
  );
}
