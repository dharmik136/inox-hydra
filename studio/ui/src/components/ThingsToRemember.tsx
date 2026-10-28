import { useCallback, useEffect, useState } from "react";
import {
  addRemembered,
  fetchRemembered,
  removeRemembered,
  saveWritingPreferences,
  updateRemembered,
  type RememberedAbout,
  type RememberedFact,
} from "@/lib/api";
import { useRefresh } from "@/lib/refresh";
import { cn } from "@/lib/utils";

/**
 * Things to remember (phase 3, item 3): facts the creator tells the studio
 * about themselves, their audience, their offers and dates, here or with
 * /remember on their bot. Which go with writing is the creator's choice,
 * shown first with its default: all of them, only the ones ticked, or none.
 * Each fact can be edited, ticked or unticked, and removed.
 */

const ABOUT_ORDER: RememberedAbout[] = ["you", "audience", "offer", "date"];
const MODES = [
  ["all", "All of them"],
  ["chosen", "Only the ones ticked"],
  ["off", "None"],
] as const;
type Mode = (typeof MODES)[number][0];

const SELECT = "rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary disabled:opacity-40";
const BUTTON =
  "rounded-md border border-edge px-2 py-0.5 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40";

function firstWords(text: string, most = 40): string {
  return text.length > most ? `${text.slice(0, most - 3).trimEnd()}...` : text;
}

function usedSaid(fact: RememberedFact): string {
  if (!fact.used_count) return "Not used in writing yet";
  return fact.used_count === 1 ? "Went with one writing request" : `Went with ${fact.used_count} writing requests`;
}

export function ThingsToRemember() {
  const [facts, setFacts] = useState<RememberedFact[] | null>(null);
  const [mode, setMode] = useState<Mode>("all");
  const [about, setAbout] = useState<Record<RememberedAbout, string> | null>(null);
  const [failed, setFailed] = useState(false);
  const [text, setText] = useState("");
  const [kind, setKind] = useState<RememberedAbout>("you");
  const [editing, setEditing] = useState<{ id: number; text: string } | null>(null);
  const [removing, setRemoving] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);

  const load = useCallback(
    () =>
      fetchRemembered()
        .then((held) => {
          setFacts(held.facts);
          setMode(held.mode as Mode);
          setAbout(held.about);
          setFailed(false);
        })
        .catch(() => setFailed(true)),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  // A /remember sent from the phone appears without a reload.
  useRefresh(load, undefined, ["collection"]);

  async function run(work: () => Promise<unknown>, said: string) {
    setBusy(true);
    setNote(null);
    try {
      await work();
      await load();
      setNote({ text: said, error: false });
      return true;
    } catch (caught) {
      setNote({ text: caught instanceof Error ? caught.message : "Nothing was changed.", error: true });
      return false;
    } finally {
      setBusy(false);
    }
  }

  const label = (key: RememberedAbout) => about?.[key] ?? key;

  return (
    <section aria-labelledby="remember-title" className="mt-4 flex flex-col gap-2 border-t border-edge pt-4">
      <div>
        <h2 id="remember-title" className="studio-label mb-1">
          Things to remember
        </h2>
        <p className="text-[12px] leading-relaxed text-ink-secondary">
          Facts about you, your audience, your offers and dates, typed here or sent to your bot with /remember. They go
          with every writing request as you choose below, never with an image prompt, and a draft the studio writes says
          which went with it. They are kept on this computer and counted in Storage.
        </p>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="remember-mode" className="text-[12px] text-ink-primary">
          Which go with writing
        </label>
        <select
          id="remember-mode"
          className={cn(SELECT, "self-start")}
          value={mode}
          disabled={busy || facts === null}
          onChange={(event) => {
            const next = event.target.value as Mode;
            void run(
              () => saveWritingPreferences({ memory: next }),
              next === "off"
                ? "None of them go with writing now."
                : next === "chosen"
                  ? "Only the ticked ones go with writing now."
                  : "All of them go with writing now.",
            );
          }}
        >
          {MODES.map(([value, words]) => (
            <option key={value} value={value}>
              {words}
            </option>
          ))}
        </select>
        <p className="text-[11px] text-ink-muted">Default: All of them</p>
      </div>

      <form
        className="flex flex-col gap-1.5"
        onSubmit={(event) => {
          event.preventDefault();
          const words = text.trim();
          if (!words) return;
          void run(() => addRemembered(words, kind), "Kept. It goes with writing as chosen above.").then(
            (kept) => kept && setText(""),
          );
        }}
      >
        <label htmlFor="remember-new" className="text-[12px] text-ink-primary">
          A thing to remember
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <input
            id="remember-new"
            value={text}
            maxLength={300}
            disabled={busy}
            onChange={(event) => setText(event.target.value)}
            placeholder="For example: my course opens on 1 March"
            className="min-w-[14rem] flex-1 rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary placeholder:text-ink-muted"
          />
          <select
            aria-label="What it is about"
            className={SELECT}
            value={kind}
            disabled={busy}
            onChange={(event) => setKind(event.target.value as RememberedAbout)}
          >
            {ABOUT_ORDER.map((key) => (
              <option key={key} value={key}>
                {label(key)}
              </option>
            ))}
          </select>
          <button type="submit" disabled={busy || !text.trim()} className={BUTTON}>
            Remember this
          </button>
        </div>
      </form>

      {failed ? (
        <p className="text-[12px] text-ink-muted">The studio did not answer. It is read again when this window comes back.</p>
      ) : facts === null ? (
        <p className="studio-meta text-ink-muted">READING</p>
      ) : facts.length === 0 ? (
        <p className="text-[12px] text-ink-muted">
          Nothing to remember yet. Add one here, or send /remember and a sentence to your bot.
        </p>
      ) : (
        <ul aria-label="Things to remember" className="flex flex-col divide-y divide-edge border-y border-edge">
          {facts.map((fact) => (
            <li key={fact.id} className="flex flex-col gap-1 py-2">
              <p className="studio-meta text-[10px] text-ink-muted">
                {fact.about_said} · {fact.source === "telegram" ? "sent from your bot" : "typed here"} · {usedSaid(fact)}
              </p>
              {editing?.id === fact.id ? (
                <form
                  className="flex flex-wrap items-center gap-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void run(() => updateRemembered(fact.id, { text: editing.text }), "Changed.").then(
                      (changed) => changed && setEditing(null),
                    );
                  }}
                >
                  <input
                    aria-label={`Change: ${firstWords(fact.text)}`}
                    value={editing.text}
                    maxLength={300}
                    disabled={busy}
                    onChange={(event) => setEditing({ id: fact.id, text: event.target.value })}
                    className="min-w-[14rem] flex-1 rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary"
                  />
                  <button type="submit" disabled={busy || !editing.text.trim()} className={BUTTON}>
                    Save
                  </button>
                  <button type="button" disabled={busy} onClick={() => setEditing(null)} className={BUTTON}>
                    Cancel
                  </button>
                </form>
              ) : (
                <p className="text-[13px] leading-snug text-ink-primary">{fact.text}</p>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-1.5 text-[11px] text-ink-secondary">
                  <input
                    type="checkbox"
                    checked={fact.in_use}
                    disabled={busy}
                    aria-label={`Ticked to go with writing: ${firstWords(fact.text)}`}
                    onChange={(event) =>
                      void run(
                        () => updateRemembered(fact.id, { in_use: event.target.checked }),
                        event.target.checked ? "Ticked." : "Unticked.",
                      )
                    }
                    className="size-3.5 accent-[var(--studio-orange)]"
                  />
                  Ticked
                </label>
                <select
                  aria-label={`What it is about: ${firstWords(fact.text)}`}
                  className={SELECT}
                  value={fact.about}
                  disabled={busy}
                  onChange={(event) =>
                    void run(() => updateRemembered(fact.id, { about: event.target.value as RememberedAbout }), "Changed.")
                  }
                >
                  {ABOUT_ORDER.map((key) => (
                    <option key={key} value={key}>
                      {label(key)}
                    </option>
                  ))}
                </select>
                {editing?.id !== fact.id && (
                  <button
                    type="button"
                    disabled={busy}
                    aria-label={`Edit: ${firstWords(fact.text)}`}
                    onClick={() => setEditing({ id: fact.id, text: fact.text })}
                    className={BUTTON}
                  >
                    Edit
                  </button>
                )}
                {removing === fact.id ? (
                  <>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void run(() => removeRemembered(fact.id), "Removed for good.").then(() => setRemoving(null))
                      }
                      className={BUTTON}
                    >
                      Remove for good
                    </button>
                    <button type="button" disabled={busy} onClick={() => setRemoving(null)} className={BUTTON}>
                      Keep it
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    disabled={busy}
                    aria-label={`Remove: ${firstWords(fact.text)}`}
                    onClick={() => setRemoving(fact.id)}
                    className={BUTTON}
                  >
                    Remove
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {mode === "chosen" && facts !== null && facts.length > 0 && (
        <p className="text-[11px] text-ink-muted">Only the ticked ones go with writing while that is chosen above.</p>
      )}
      {mode === "off" && <p className="text-[11px] text-ink-muted">None of them go with writing while None is chosen above.</p>}
      {note && (
        <p role="status" className={cn("text-[12px]", note.error ? "text-signal-orange-text" : "text-ink-secondary")}>
          {note.text}
        </p>
      )}
    </section>
  );
}
