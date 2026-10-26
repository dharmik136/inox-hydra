import { useState } from "react";
import { ExternalLink, PenLine } from "lucide-react";
import {
  draftFromCard,
  launchBridge,
  markRecordCard,
  moreOfThis,
  unmarkRecordCard,
  type RecordCard,
  type RecordFigure,
  type RecordLabel,
} from "@/lib/api";
import { formatLocalDay } from "@/lib/time";
import { cn } from "@/lib/utils";

/**
 * One card of From your record, in the report's five lines:
 *
 *   1  what it is and its label (measured, derived, typed, suggested,
 *      retrieved, curated), so a classification is never read as a finding
 *   2  the creator's own words, in quotation marks
 *   3  figures, only when a row measured them, each with its row
 *   4  the "because" sentence: the rows and the rule that chose it
 *   5  "Why this?": the whole rule, the figures' rows and the check
 *
 * An abstention is a sentence saying what is missing and what will fill it,
 * never a padded card. Nothing here computes a figure: every number arrives
 * from the server with the row it was read from.
 */

/** The label as the card says it. */
const LABEL_WORDS: Record<RecordLabel, string> = {
  measured: "measured",
  derived: "derived from measured rows",
  typed: "typed by a rule, not measured",
  suggested: "suggested by your model",
  retrieved: "retrieved",
  curated: "curated, not measured for you",
  abstained: "not yet",
};

export interface CardActions {
  /** Opens the Composer on a draft the server made from this card. */
  onDraft?: (draft: { id: string; content: string }) => void;
  /** Read the batch again after a mark. */
  onChanged?: () => void;
}

export function RecordCardView({ card, actions, compact = false }: { card: RecordCard; actions?: CardActions; compact?: boolean }) {
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const marks = new Set(card.marks ?? []);
  const kept = marks.has("keep");
  const payload = card.payload;

  async function act(run: () => Promise<{ message?: string } | void>, after?: () => void) {
    if (busy) return;
    setBusy(true);
    try {
      const answer = await run();
      setNote(answer && answer.message ? { text: answer.message, error: false } : null);
      after?.();
      actions?.onChanged?.();
    } catch (error) {
      setNote({ text: error instanceof Error ? error.message : "That did not work.", error: true });
    } finally {
      setBusy(false);
    }
  }

  if (card.status === "abstained") {
    return (
      <article className="flex h-full flex-col rounded-md border border-dashed border-edge-strong bg-ink p-3" aria-label={`${payload.block_label ?? "Card"}: not yet`}>
        <p className="studio-label">{payload.block_label}</p>
        <p className="studio-meta mt-1 text-[10px] text-ink-muted">NOT YET</p>
        <p className="mt-2 text-[13px] leading-snug text-ink-secondary">{payload.sentence}</p>
        <p className="studio-meta mt-auto pt-2 text-[10px] leading-snug text-ink-muted">RULE: {card.method}</p>
      </article>
    );
  }

  const figures = payload.figures ?? [];
  const measured = card.label === "measured" || card.label === "derived";

  return (
    <article className="flex h-full flex-col rounded-md border border-edge bg-raised p-3" aria-label={`${payload.title ?? card.kind}, ${LABEL_WORDS[card.label]}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-2">
        <p className="studio-label">{payload.block_label}</p>
        {payload.date && <p className="studio-meta text-[10px] text-ink-muted">{formatLocalDay(payload.date)}</p>}
      </div>
      <p className="mt-1 text-[13px] font-medium text-ink-primary">
        {payload.title}{" "}
        <span className="studio-meta text-[10px] font-normal text-ink-muted">· {payload.badge ?? LABEL_WORDS[card.label]}</span>
      </p>
      {payload.excerpt ? (
        <p className="mt-2 text-[13px] leading-snug text-ink-secondary">&ldquo;{payload.excerpt}&rdquo;</p>
      ) : null}
      {measured && payload.figure_sentence ? (
        <p className="studio-meta mt-2 text-[11px] leading-snug text-ink-primary">{payload.figure_sentence}</p>
      ) : null}
      {!compact && payload.matches && payload.matches.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1 border-l border-edge pl-2">
          {payload.matches.map((match) => (
            <li key={match.activity_urn} className="text-[12px] leading-snug text-ink-secondary">
              &ldquo;{match.excerpt}&rdquo;{" "}
              <span className="studio-meta text-[10px] text-ink-muted">{formatLocalDay(match.date, "Date not recorded")}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-[12px] leading-snug text-ink-secondary">{payload.because}</p>
      {!compact && (
        <details className="mt-2 text-[12px] text-ink-secondary">
          <summary className="cursor-pointer text-ink-muted hover:text-ink-primary">Why this?</summary>
          <p className="mt-1 leading-snug">{payload.method_sentence}</p>
          {payload.source_sentence && <p className="mt-1 leading-snug">Source: {payload.source_sentence}.</p>}
          {figures.length > 0 && <FigureRows figures={figures} />}
          <p className="studio-meta mt-1 text-[10px] text-ink-muted">LABEL: {card.label.toUpperCase()}. EVERY ROW IT CITES WAS FOUND BEFORE IT WAS SHOWN.</p>
        </details>
      )}
      {actions && (
        <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-3">
          <Action
            pressed={kept}
            disabled={busy}
            onClick={() =>
              void act(() => (kept ? unmarkRecordCard(card.day, card.card_id, "keep") : markRecordCard(card.day, card.card_id, "keep")))
            }
          >
            {kept ? "Kept" : "Keep"}
          </Action>
          {!compact && (
            <>
              <Action disabled={busy || marks.has("skip")} onClick={() => void act(() => markRecordCard(card.day, card.card_id, "skip"))}>
                {marks.has("skip") ? "Skipped" : "Skip"}
              </Action>
              <Action disabled={busy} onClick={() => void act(() => markRecordCard(card.day, card.card_id, "hide"))}>
                Hide
              </Action>
              <Action disabled={busy} onClick={() => void act(() => moreOfThis(card.day, card.card_id))}>
                More of this
              </Action>
            </>
          )}
          {payload.draft_text && actions.onDraft && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void act(async () => actions.onDraft?.(await draftFromCard(card.day, card.card_id)))}
              className="inline-flex items-center gap-1 rounded-md bg-signal-orange px-2 py-1 text-[11px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-60"
            >
              <PenLine className="size-3" aria-hidden="true" />
              Draft from this
            </button>
          )}
          {payload.url && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void act(async () => ({ message: (await launchBridge("auto", payload.url as string)).message }))}
              className="inline-flex items-center gap-1 rounded-md border border-edge px-2 py-1 text-[11px] text-ink-secondary transition-colors hover:text-ink-primary"
            >
              <ExternalLink className="size-3" aria-hidden="true" />
              Open on LinkedIn
            </button>
          )}
        </div>
      )}
      {note && (
        <p role="status" className={cn("mt-2 text-[11px] leading-snug", note.error ? "text-signal-orange-text" : "text-ink-muted")}>
          {note.text}
        </p>
      )}
    </article>
  );
}

function Action({ children, onClick, pressed, disabled }: { children: React.ReactNode; onClick: () => void; pressed?: boolean; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={pressed === undefined ? undefined : pressed}
      className={cn(
        "rounded-md border px-2 py-1 text-[11px] transition-colors disabled:opacity-60",
        pressed ? "border-signal-green bg-signal-green-subtle text-signal-green-text" : "border-edge text-ink-secondary hover:text-ink-primary",
      )}
    >
      {children}
    </button>
  );
}

function FigureRows({ figures }: { figures: RecordFigure[] }) {
  return (
    <table className="mt-1 w-full text-left text-[11px]">
      <thead>
        <tr className="studio-meta text-[10px] text-ink-muted">
          <th className="font-normal">FIGURE</th>
          <th className="font-normal">VALUE</th>
          <th className="font-normal">READ FROM</th>
        </tr>
      </thead>
      <tbody>
        {figures.map((figure) => (
          <tr key={`${figure.name}-${figure.table}`}>
            <td className="pr-2">{figure.name.replace(/_/g, " ")}</td>
            <td className="pr-2 tabular-nums">{figure.value.toLocaleString()}</td>
            <td className="text-ink-muted">
              {figure.table}
              {figure.observed_at ? `, ${formatLocalDay(figure.observed_at)}` : ""}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
