import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  fetchWritingPreferences,
  saveWritingPreferences,
  type ReshapeButton,
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
  reshapes: "Rewrite buttons on your bot",
  combine_at_most: "Most items in one draft",
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
  "combine_at_most",
  "reshapes",
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
    case "reshapes":
      return values.reshapes.length ? values.reshapes.map((button) => button.label).join(", ") : "none";
    case "combine_at_most":
      return `${values.combine_at_most} items`;
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
          "combine_at_most",
          "writing-combine",
          <select id="writing-combine" className={SELECT} value={draft.combine_at_most} disabled={busy}
            onChange={(event) => set("combine_at_most", Number(event.target.value))}>
            {choices.combine_at_most.map((n) => (
              <option key={n} value={n}>
                {n} items, for Combine and /write
              </option>
            ))}
          </select>,
        )}
        <RewriteButtons
          value={draft.reshapes}
          defaults={defaults.reshapes}
          limits={described.limits}
          busy={busy}
          onChange={(next) => set("reshapes", next)}
        />
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
          onClick={() =>
            void save(
              // A rewrite button left wholly empty is dropped, not refused.
              only({ ...draft, avoid, reshapes: draft.reshapes.filter((b) => b.label.trim() || b.asks.trim()) }),
              "Saved. Every writing request reads these from now on.",
            )
          }
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

/**
 * The rewrite buttons under a draft the bot wrote (phase 4): which appear on
 * the phone, in this order, and what each asks the writer for, in the
 * creator's own words. Saved with the other preferences; none is a choice.
 */
function RewriteButtons({
  value,
  defaults,
  limits,
  busy,
  onChange,
}: {
  value: ReshapeButton[];
  defaults: ReshapeButton[];
  limits: WritingDescribed["limits"];
  busy: boolean;
  onChange: (next: ReshapeButton[]) => void;
}) {
  const change = (index: number, field: keyof ReshapeButton, text: string) =>
    onChange(value.map((button, at) => (at === index ? { ...button, [field]: text } : button)));
  return (
    <fieldset className="flex flex-col gap-1.5 border-b border-edge py-2.5">
      <legend className="text-[12px] text-ink-primary">{LABELS.reshapes}</legend>
      <p className="text-[11px] leading-relaxed text-ink-secondary">
        Under a draft your bot wrote, with The bot may send me what it writes from my collection on, each button
        rewrites it through your provider as it says. The label is what the phone shows; what it asks for is sent with
        the draft.
      </p>
      {value.length === 0 ? (
        <p className="text-[11px] text-ink-muted">No rewrite buttons: a draft from the bot carries none.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {value.map((button, index) => (
            <li key={index} className="flex flex-wrap items-center gap-2">
              <input
                aria-label={`Rewrite button ${index + 1}: its label`}
                className={cn(INPUT, "min-w-[8rem] flex-none")}
                value={button.label}
                maxLength={limits.reshape_label}
                disabled={busy}
                onChange={(event) => change(index, "label", event.target.value)}
              />
              <input
                aria-label={`Rewrite button ${index + 1}: what it asks for`}
                className={INPUT}
                value={button.asks}
                maxLength={limits.reshape_asks}
                disabled={busy}
                onChange={(event) => change(index, "asks", event.target.value)}
              />
              <button
                type="button"
                disabled={busy}
                onClick={() => onChange(value.filter((_button, at) => at !== index))}
                aria-label={`Remove the rewrite button ${button.label || index + 1}`}
                className="rounded-md px-1.5 py-0.5 text-[11px] text-ink-secondary underline underline-offset-2 hover:text-ink-primary disabled:opacity-40"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      {value.length < limits.reshapes && (
        <button
          type="button"
          disabled={busy}
          onClick={() => onChange([...value, { label: "", asks: "" }])}
          className="self-start rounded-md border border-edge px-2 py-0.5 text-[11px] text-ink-secondary hover:text-ink-primary disabled:opacity-40"
        >
          Add a rewrite button
        </button>
      )}
      <p className="text-[11px] text-ink-muted">
        Default: {defaults.map((button) => `${button.label} (${button.asks})`).join("; ")}
      </p>
    </fieldset>
  );
}
