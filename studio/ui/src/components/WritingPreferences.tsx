import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  fetchWritingPreferences,
  saveWritingPreferences,
  type WritingDescribed,
  type WritingPreferences,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { ThingsToRemember } from "./ThingsToRemember";

/**
 * How the studio writes for you (phase 3, and the owner's direction of
 * 2026-10-29: "do not hardcode things as they will be users preference in
 * AI work"). Every choice a writing request makes is one of these, kept in
 * one place (studio/backend/writing.py) and read the same way by the
 * collection's Make a post, Combine and Angles, the bot's Write it up, and
 * the Composer's Command and Re-Hook. Brand's Writing view edits them; each
 * feature shows the ones it reads beside it, with their defaults named.
 */
export type PreferenceField = keyof WritingPreferences;

const LABELS: Record<PreferenceField, string> = {
  length_words: "Length of a draft",
  tone: "Tone",
  language: "Language",
  opening: "Opening line",
  emojis: "Emojis",
  hashtags: "Hashtags",
  line_breaks: "Line breaks",
  ending: "Ending",
  avoid: "Words to avoid",
  angles: "Angles",
  sources: "Ideas draw on",
  memory: "Things to remember",
  ideas: "Ideas asked for each day",
};

/** The preferences this view edits with its Save; the others are set beside their own feature. */
const EDITED_HERE: PreferenceField[] = [
  "length_words",
  "tone",
  "language",
  "opening",
  "emojis",
  "hashtags",
  "line_breaks",
  "ending",
  "avoid",
  "angles",
];

function only(values: Partial<WritingPreferences>): Partial<WritingPreferences> {
  return Object.fromEntries(EDITED_HERE.map((field) => [field, values[field]])) as Partial<WritingPreferences>;
}

/** A preference's value as the creator reads it. */
export function preferenceWords(field: PreferenceField, values: WritingPreferences, described: WritingDescribed): string {
  const labels = described.labels;
  switch (field) {
    case "length_words":
      return `about ${values.length_words} words`;
    case "tone":
      return values.tone;
    case "language":
      return values.language || labels.language;
    case "opening":
      return values.opening ? `in the manner of ${values.opening}` : labels.opening;
    case "emojis":
      return labels.emojis[values.emojis] ?? values.emojis;
    case "hashtags":
      return labels.hashtags[values.hashtags] ?? values.hashtags;
    case "line_breaks":
      return labels.line_breaks[values.line_breaks] ?? values.line_breaks;
    case "ending":
      return labels.ending[values.ending] ?? values.ending;
    case "avoid":
      return values.avoid.length ? values.avoid.join(", ") : "nothing set";
    case "angles":
      return `${values.angles} opening lines`;
    case "sources":
      return values.sources.length ? values.sources.map((s) => labels.sources[s]).join(", ") : "nothing";
    case "memory":
      return (labels.memory[values.memory] ?? values.memory).toLowerCase();
    case "ideas":
      return values.ideas === 1 ? "one idea" : `${values.ideas} ideas`;
  }
}

function isDefault(field: PreferenceField, described: WritingDescribed): boolean {
  return JSON.stringify(described.values[field]) === JSON.stringify(described.defaults[field]);
}

/**
 * The preferences a feature reads, beside it: each value, and whether it is
 * the default or what the default is. Folded, so the feature stays first.
 */
export function WritingSummary({
  described,
  fields,
  title = "How it writes",
}: {
  described: WritingDescribed | null;
  fields: PreferenceField[];
  title?: string;
}) {
  if (!described) return null;
  return (
    <details className="text-[12px] text-ink-secondary">
      <summary className="cursor-pointer select-none hover:text-ink-primary">
        {title}: as set in Brand, under Writing
      </summary>
      <ul className="mt-1.5 flex flex-col gap-0.5 pl-3">
        {fields.map((field) => (
          <li key={field}>
            <span className="text-ink-primary">{LABELS[field]}:</span> {preferenceWords(field, described.values, described)}
            <span className="text-ink-muted">
              {isDefault(field, described)
                ? " (the default)"
                : ` (default: ${preferenceWords(field, described.defaults, described)})`}
            </span>
          </li>
        ))}
        <li className="text-ink-muted">
          {described.provider.configured
            ? `Written by ${described.provider.provider} (${described.provider.model}), connected on the Composer's Prompt tab.`
            : "No AI provider is connected: connect yours on the Composer's Prompt tab."}
        </li>
      </ul>
    </details>
  );
}

/** Reads the preferences, and reads them again when a window asks. */
export function useWritingPreferences(): [WritingDescribed | null, () => Promise<void>] {
  const [described, setDescribed] = useState<WritingDescribed | null>(null);
  const load = useCallback(
    () =>
      fetchWritingPreferences()
        .then(setDescribed)
        .catch(() => undefined),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  return [described, load];
}

const SELECT = "rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary disabled:opacity-40";
const INPUT =
  "min-w-[14rem] flex-1 rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary placeholder:text-ink-muted";

/** Brand, Writing: every writing preference, each with its default, and Save. */
export function WritingPreferencesPanel({ children }: { children?: ReactNode } = {}) {
  const [described, load] = useWritingPreferences();
  const [draft, setDraft] = useState<WritingPreferences | null>(null);
  const [avoidText, setAvoidText] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);

  useEffect(() => {
    if (!described) return;
    setDraft(described.values);
    setAvoidText(described.values.avoid.join(", "));
  }, [described]);

  if (!described || !draft) return <p className="studio-meta text-ink-muted">READING</p>;

  function set<K extends PreferenceField>(field: K, value: WritingPreferences[K]) {
    setDraft((current) => (current ? { ...current, [field]: value } : current));
    setNote(null);
  }

  async function save(change: Partial<WritingPreferences>, said: string) {
    setBusy(true);
    setNote(null);
    try {
      await saveWritingPreferences(change);
      await load();
      setNote({ text: said, error: false });
    } catch (caught) {
      setNote({ text: caught instanceof Error ? caught.message : "Nothing was saved.", error: true });
    } finally {
      setBusy(false);
    }
  }

  const avoid = avoidText
    .split(",")
    .map((phrase) => phrase.trim())
    .filter(Boolean);
  const defaults = described.defaults;
  const choices = described.choices;
  const labels = described.labels;

  const row = (field: PreferenceField, id: string, control: ReactNode) => (
    <div key={field} className="flex flex-col gap-1 border-b border-edge py-2.5 last:border-b-0">
      <label htmlFor={id} className="text-[12px] text-ink-primary">
        {LABELS[field]}
      </label>
      <div className="flex flex-wrap items-center gap-2">{control}</div>
      <p className="text-[11px] text-ink-muted">Default: {preferenceWords(field, defaults, described)}</p>
    </div>
  );

  return (
    <section aria-labelledby="writing-title" className="flex max-w-2xl flex-col gap-3">
      <div>
        <h2 id="writing-title" className="studio-label mb-1">
          How the studio writes for you
        </h2>
        <p className="text-[12px] leading-relaxed text-ink-secondary">
          Every writing request reads these: Make a post, Combine and Angles in your collection, Write it up on your
          bot, and Command and Re-Hook in the Composer. Each says its default. The rules that keep writing honest are
          not choices: only what you sent is used, no figure, person, date or quote is invented, and no em dash.
        </p>
        <p className="mt-1 text-[12px] text-ink-muted">
          {described.provider.configured
            ? `Written by ${described.provider.provider} (${described.provider.model}), connected on the Composer's Prompt tab.`
            : "No AI provider is connected: connect yours on the Composer's Prompt tab."}
        </p>
      </div>

      <div className="flex flex-col">
        {row(
          "length_words",
          "writing-length",
          <select id="writing-length" className={SELECT} value={draft.length_words} disabled={busy}
            onChange={(event) => set("length_words", Number(event.target.value))}>
            {choices.length_words.map((n) => (
              <option key={n} value={n}>
                About {n} words
              </option>
            ))}
          </select>,
        )}
        {row(
          "tone",
          "writing-tone",
          <input id="writing-tone" className={INPUT} value={draft.tone} maxLength={described.limits.tone} disabled={busy}
            onChange={(event) => set("tone", event.target.value)} />,
        )}
        {row(
          "language",
          "writing-language",
          <input id="writing-language" className={INPUT} value={draft.language} maxLength={described.limits.language}
            placeholder={labels.language} disabled={busy} onChange={(event) => set("language", event.target.value)} />,
        )}
        {row(
          "opening",
          "writing-opening",
          <select id="writing-opening" className={SELECT} value={draft.opening} disabled={busy}
            onChange={(event) => set("opening", event.target.value)}>
            {choices.opening.map((form) => (
              <option key={form || "default"} value={form}>
                {form || labels.opening}
              </option>
            ))}
          </select>,
        )}
        {(["emojis", "hashtags", "line_breaks", "ending"] as const).map((field) =>
          row(
            field,
            `writing-${field}`,
            <select id={`writing-${field}`} className={SELECT} value={draft[field]} disabled={busy}
              onChange={(event) => set(field, event.target.value)}>
              {Object.keys(choices[field]).map((key) => (
                <option key={key} value={key}>
                  {labels[field][key] ?? key}
                </option>
              ))}
            </select>,
          ),
        )}
        {row(
          "avoid",
          "writing-avoid",
          <input id="writing-avoid" className={INPUT} value={avoidText} disabled={busy}
            placeholder="Words and phrases, separated by commas" onChange={(event) => setAvoidText(event.target.value)} />,
        )}
        {row(
          "angles",
          "writing-angles",
          <select id="writing-angles" className={SELECT} value={draft.angles} disabled={busy}
            onChange={(event) => set("angles", Number(event.target.value))}>
            {choices.angles.map((n) => (
              <option key={n} value={n}>
                {n} opening lines
              </option>
            ))}
          </select>,
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void save(only({ ...draft, avoid }), "Saved. Every writing request reads these from now on.")}
          className="rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
        >
          Save
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void save(only(defaults), "Back to the defaults.")}
          className="rounded-md px-2 py-1 text-[12px] text-ink-secondary underline underline-offset-2 hover:text-ink-primary disabled:opacity-40"
        >
          Back to the defaults
        </button>
      </div>
      {note && (
        <p role="status" className={cn("text-[12px]", note.error ? "text-signal-orange-text" : "text-ink-secondary")}>
          {note.text}
        </p>
      )}
      <ThingsToRemember />
      {children}
    </section>
  );
}
