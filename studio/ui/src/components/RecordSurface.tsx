import { useCallback, useEffect, useRef, useState } from "react";
import {
  addRecordAsk,
  runRecordModel,
  fetchKept,
  fetchRecord,
  fetchRecordDay,
  rerollRecord,
  type RecordCard,
  type RecordToday,
} from "@/lib/api";
import { useRefresh, useStudioBack } from "@/lib/refresh";
import { formatLocalDay } from "@/lib/time";
import { cn } from "@/lib/utils";
import { RecordCardView } from "./RecordCardView";
import { RecordKnowsPanel } from "./RecordKnowsPanel";
import { RecordEvaluationPanel } from "./RecordEvaluationPanel";

/**
 * From your record: what from your own record, and from what you asked, is
 * worth writing from today.
 *
 * One batch a day, built the first time the studio runs that day and only
 * read here: this screen computes nothing. Five slots from three sources,
 * named on the cards ("Working for you", "You asked", "You engaged with"),
 * each card labelled with how it was arrived at and the rows it came from,
 * or a sentence saying what is missing. An empty slot is never padded.
 *
 * Three levels: Today; Kept, the Library the earlier report deferred for
 * want of a writer, read from the keep marks; and What the studio knows,
 * every ask, mark and setting the section holds, editable and reversible.
 */
type Level = "today" | "kept" | "knows" | "helped";

export function RecordSurface({ onOpenDraft }: { onOpenDraft?: (draft: { id: string; content: string }) => void } = {}) {
  const [level, setLevel] = useState<Level>("today");
  const [today, setToday] = useState<RecordToday | null>(null);
  const [failed, setFailed] = useState(false);
  const [viewing, setViewing] = useState<string | null>(null);
  const [earlier, setEarlier] = useState<RecordCard[] | null>(null);
  const [kept, setKept] = useState<RecordCard[] | null>(null);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);
  const back = useStudioBack();

  const load = useCallback(() => {
    return fetchRecord()
      .then((data) => {
        setToday(data);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    void load();
  }, [load, back]);

  // The model stage runs on the creator's first open of the day (decision
  // 7): asked once from here, as its own request, never by the read above.
  // The local cards are on screen already; the idea arrives into today's row.
  const asked = useRef(false);
  const modelStatus = today?.model?.status;
  useEffect(() => {
    if (!today?.model?.should_run || asked.current) return;
    asked.current = true;
    void runRecordModel()
      .then(() => load())
      .catch(() => undefined);
  }, [today, load]);
  useEffect(() => {
    if (modelStatus !== "running") return;
    const timer = window.setInterval(() => void load(), 3000);
    return () => window.clearInterval(timer);
  }, [modelStatus, load]);
  // Read again when the window comes back into view, never on a timer: the
  // batch changes once a day.
  useRefresh(load);

  useEffect(() => {
    if (level !== "kept") return;
    fetchKept()
      .then(setKept)
      .catch(() => setKept([]));
  }, [level]);

  useEffect(() => {
    if (!viewing || !today || viewing === today.batch_day) {
      setEarlier(null);
      return;
    }
    fetchRecordDay(viewing)
      .then((day) => setEarlier(day.cards))
      .catch(() => setEarlier([]));
  }, [viewing, today]);

  async function reroll() {
    try {
      await rerollRecord();
      setNote({ text: "Drawn again. Your marks on the earlier cards still count.", error: false });
      await load();
    } catch (error) {
      setNote({ text: error instanceof Error ? error.message : "That did not work.", error: true });
    }
  }

  if (failed && !today) return <Centered>FROM YOUR RECORD IS UNAVAILABLE. IS THE STUDIO RUNNING?</Centered>;
  if (!today) return <Centered>READING YOUR CARDS</Centered>;

  const showingDay = viewing && viewing !== today.batch_day ? viewing : today.batch_day;
  const cards = (showingDay === today.batch_day ? today.cards : earlier ?? []).filter(
    (card) => card.status === "shown" || card.status === "abstained",
  );
  const monday = cards.find((card) => card.kind === "monday");
  const slots = cards.filter((card) => card.slot >= 1).sort((a, b) => a.slot - b.slot);
  const isToday = showingDay === today.day;
  const actions = { onDraft: onOpenDraft, onChanged: () => void load() };

  return (
    <div className="px-6 py-6 lg:px-8" tabIndex={0} aria-labelledby="record-title">
      <header className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
        <div>
          <p className="studio-label">From your record</p>
          <h1 id="record-title" className="studio-title mt-1">
            What is worth writing from today
          </h1>
          <p className="studio-meta mt-2 text-[11px] text-ink-muted">{today.computed.toUpperCase()}</p>
          {today.nothing_new && <p className="mt-1 max-w-[70ch] text-[12px] text-ink-secondary">{today.nothing_new}</p>}
          {today.model?.configured && (
            <p className="mt-1 max-w-[70ch] text-[12px] text-ink-muted">
              {today.model.status === "running"
                ? `Your ${today.model.provider_label} key is answering now. The idea arrives in the fifth card.`
                : today.run?.model_note ?? today.model.reason}
              {today.run?.estimated_cost_usd
                ? ` Estimated $${today.run.estimated_cost_usd.toFixed(4)} of your $${today.model.ceiling_usd.toFixed(2)} a day, from ${today.model.provider_label} prices of ${today.model.price_date}.`
                : ""}
            </p>
          )}
          {today.run && today.run.dropped_cards > 0 && (
            <p className="mt-1 text-[12px] text-signal-orange-text">
              {/* The count covers both checks: a local card whose cited row was gone, and an idea of the model's
                  that failed record_model.verify_ideas, whose reasons the model's note above names. */}
              {today.run.dropped_cards} {today.run.dropped_cards === 1 ? "card failed a check and is" : "cards failed a check and are"}{" "}
              not shown: a row it cited was not found, or, for an idea from your model, the reason in the line above.
            </p>
          )}
        </div>
        <nav aria-label="From your record levels" className="flex flex-wrap items-center gap-1">
          {(
            [
              // Not "Today": the rail's Today button sits beside it with that name.
              ["today", "Today's cards"],
              ["kept", "Kept"],
              ["knows", "What the studio knows"],
              ["helped", "Did these help?"],
            ] as [Level, string][]
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              aria-pressed={level === id}
              onClick={() => setLevel(id)}
              className={cn(
                "rounded-md px-2.5 py-1 text-[12px] transition-colors",
                level === id ? "bg-soft text-ink-primary" : "text-ink-secondary hover:text-ink-primary",
              )}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      {level === "today" && (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            {today.days.length > 1 && (
              <label className="flex items-center gap-2 text-[12px] text-ink-secondary">
                Day
                <select
                  value={showingDay ?? ""}
                  onChange={(event) => setViewing(event.target.value)}
                  className="rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary"
                >
                  {today.days.map((day) => (
                    <option key={day} value={day}>
                      {formatLocalDay(day)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {isToday && (
              <button
                type="button"
                disabled={Boolean(today.run?.rerolled_at)}
                onClick={() => void reroll()}
                className="rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:text-ink-primary disabled:opacity-60"
              >
                {today.run?.rerolled_at ? "Drawn again today" : "Suggest new"}
              </button>
            )}
            <p className="text-[11px] text-ink-muted">Marks change which cards come back, from tomorrow. They never change a figure.</p>
          </div>

          {monday && (
            <section aria-label="Your week" className="mt-4 rounded-md border border-edge bg-ink px-3 py-2">
              <p className="text-[12px] text-ink-secondary">
                <span className="studio-label mr-2">Your week</span>
                {monday.payload.figure_sentence}.{" "}
                <span className="text-ink-muted">Counts of your own rows, compared with nothing.</span>
              </p>
            </section>
          )}

          {slots.length === 0 ? (
            <p className="mt-6 max-w-[62ch] text-[13px] leading-relaxed text-ink-secondary">
              No cards yet. The first batch is built within a few minutes of the studio starting each day, from your own
              posts, comments and asks. Import your LinkedIn archive in Setup and it fills from day one.
            </p>
          ) : (
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              {slots.map((card) => (
                <RecordCardView key={`${card.day}-${card.card_id}`} card={card} actions={isToday ? actions : { onChanged: actions.onChanged }} compact={!isToday} />
              ))}
            </div>
          )}

          {isToday && <AskBox onAsked={(text) => setNote({ text, error: false })} />}
        </>
      )}

      {level === "kept" && (
        <section aria-label="Kept" className="mt-4">
          <p className="max-w-[70ch] text-[12px] leading-snug text-ink-secondary">
            Every card you kept, newest first: your own posts, openers, asks and the comments you made. Keep is the one
            way in, and Kept is the way back to them.
          </p>
          {kept === null ? (
            <p className="studio-meta mt-3 text-[10px] text-ink-muted">READING WHAT YOU KEPT</p>
          ) : kept.length === 0 ? (
            <p className="mt-3 text-[13px] text-ink-secondary">Nothing kept yet. Press Keep on a card you want to come back to.</p>
          ) : (
            <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {kept.map((card) => (
                <RecordCardView
                  key={`${card.day}-${card.card_id}`}
                  card={{ ...card, marks: ["keep"] }}
                  actions={{ onDraft: onOpenDraft, onChanged: () => void fetchKept().then(setKept) }}
                  compact
                />
              ))}
            </div>
          )}
        </section>
      )}

      {level === "knows" && (
        <div className="mt-4">
          <RecordKnowsPanel />
        </div>
      )}

      {level === "helped" && (
        <div className="mt-4">
          <RecordEvaluationPanel />
        </div>
      )}

      {note && (
        <p role="status" className={cn("mt-3 text-[12px]", note.error ? "text-signal-orange-text" : "text-ink-muted")}>
          {note.text}
        </p>
      )}
    </div>
  );
}

function AskBox({ onAsked }: { onAsked: (text: string) => void }) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true);
    try {
      const answer = await addRecordAsk(text.trim(), "ask_box");
      setText("");
      setError(null);
      onAsked(`Remembered. ${answer.message}`);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "That was not kept.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="mt-5 border-t border-edge pt-4">
      <label htmlFor="record-ask" className="studio-label">
        Ask for something to write about
      </label>
      <div className="mt-2 flex flex-wrap items-start gap-2">
        <input
          id="record-ask"
          value={text}
          maxLength={2000}
          onChange={(event) => setText(event.target.value)}
          placeholder="pricing for a two person studio"
          className="min-w-[18rem] flex-1 rounded-md border border-edge bg-ink px-2 py-1.5 text-[13px] text-ink-primary placeholder:text-ink-muted"
        />
        <button
          type="submit"
          disabled={busy || !text.trim()}
          className="rounded-md bg-signal-orange px-3 py-1.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-60"
        >
          Remember this ask
        </button>
      </div>
      <p className="mt-1 text-[11px] text-ink-muted">
        Kept in this studio, listed on What the studio knows, and matched to your own posts from tomorrow. Nothing is sent
        anywhere unless your own model&rsquo;s stage is on.
      </p>
      {error && <p className="mt-1 text-[12px] text-signal-orange-text">{error}</p>}
    </form>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}
