import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchMadeWith,
  fetchRelatedFromCollection,
  fetchRemembered,
  markCollectionUsed,
  setCollectionStatus,
  type CollectionItem,
  type MadeWith,
  type RememberedFact,
} from "@/lib/api";
import { useRefresh } from "@/lib/refresh";
import { formatLocal } from "@/lib/time";

/**
 * The collection, where the writing happens (phase 3, item 3).
 *
 * Two pieces beside the editor. "From your collection" is folded like What
 * worked for you: the new items in the creator's collection whose words the
 * draft shares, matched on this computer, each with Add to the draft. "What
 * this draft was written from" is the note a draft the studio wrote carries:
 * how many items, which things to remember went with it, and which provider
 * wrote it. Nothing here is generated, and nothing leaves the machine.
 */

/** Whether the writer has opened the panel, for this sitting, as What worked for you keeps it. */
let openedThisSession = false;

/**
 * Items added to a post that is not saved yet. Each is marked used once the
 * post is saved with its words still in it, and forgotten otherwise.
 */
let waitingForSave: { id: number; words: string }[] = [];

/** Bounded, as What worked for you is, so the editor stays where a writer can type in it. */
const PANEL_MAX_HEIGHT = "max-h-[15rem]";

/** How long after the last key the draft's words are matched again. */
const MATCH_AFTER_MS = 700;

function firstWords(text: string, most = 48): string {
  const line = text.trim().split("\n")[0] ?? "";
  return line.length > most ? `${line.slice(0, most - 3).trimEnd()}...` : line;
}

export function FromYourCollection({
  value,
  onChange,
  postId,
}: {
  value: string;
  onChange: (next: string, cleared?: boolean) => void;
  postId?: string | null;
}) {
  const [items, setItems] = useState<CollectionItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(openedThisSession);
  // The draft as it was before an item was added, so one click puts it back,
  // as What worked for you's Undo does.
  const [undo, setUndo] = useState<{ before: string; words: string; id: number; marked: boolean } | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const latest = useRef(value);
  latest.current = value;

  const load = useCallback(() => {
    const text = latest.current;
    if (!text.trim()) {
      setItems([]);
      return Promise.resolve();
    }
    return fetchRelatedFromCollection(text)
      .then((found) => {
        setItems(found);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), MATCH_AFTER_MS);
    return () => window.clearTimeout(timer);
  }, [value, load]);

  // Something sent from the phone, or used elsewhere, is matched without a reload.
  useRefresh(load, undefined, ["collection"]);

  // A post saved for the first time: what was added to it while it was new
  // is used now, if its words are still in it.
  useEffect(() => {
    if (!postId || waitingForSave.length === 0) return;
    const added = waitingForSave;
    waitingForSave = [];
    for (const one of added) {
      if (!latest.current.includes(one.words)) continue;
      markCollectionUsed(one.id, postId)
        .then(() => setUndo((held) => (held && held.id === one.id ? { ...held, marked: true } : held)))
        .catch(() => undefined);
    }
  }, [postId]);

  function add(item: CollectionItem) {
    const words = (item.text ?? "").trim();
    if (!words) return;
    const before = value;
    onChange(before.trim() ? `${before.replace(/\s+$/, "")}\n\n${words}` : words);
    setUndo({ before, words, id: item.id, marked: false });
    if (postId) {
      setNote("Added at the end of your draft, and marked used in your collection.");
      markCollectionUsed(item.id, postId)
        .then(() => setUndo((held) => (held && held.id === item.id ? { ...held, marked: true } : held)))
        .catch(() => setNote("Added at the end of your draft. The collection did not answer, so it is still new there."));
    } else {
      waitingForSave.push({ id: item.id, words });
      setNote("Added at the end of your draft. It is marked used in your collection when you save the draft.");
    }
  }

  function takeBack() {
    if (!undo) return;
    onChange(undo.before);
    waitingForSave = waitingForSave.filter((one) => one.id !== undo.id);
    if (undo.marked) void setCollectionStatus(undo.id, "new").catch(() => undefined);
    setUndo(null);
    setNote("Taken back out. The item is new in your collection again.");
  }

  const canUndo = undo !== null && value.endsWith(undo.words);
  const pending = new Set(waitingForSave.map((one) => one.id));
  const shown = (items ?? []).filter((item) => !pending.has(item.id) && item.id !== undo?.id);

  return (
    <section aria-labelledby="composer-from-collection" className="mb-6 rounded-md border border-edge">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 px-3 py-2">
        <h2 id="composer-from-collection" className="studio-label">
          From your collection
        </h2>
        <div className="flex items-center gap-3">
          {canUndo && (
            <p className="studio-meta flex items-center gap-2 text-[10px] text-ink-muted">
              ADDED
              <button
                type="button"
                onClick={takeBack}
                aria-label="Undo: take the item back out of the draft"
                className="rounded-sm border border-edge px-1.5 text-ink-secondary transition-colors hover:border-edge-strong hover:text-ink-primary"
              >
                UNDO
              </button>
            </p>
          )}
          {!open && shown.length > 0 && (
            <p className="studio-meta text-[10px] text-ink-muted">
              {shown.length === 1 ? "1 SHARES ITS WORDS" : `${shown.length} SHARE ITS WORDS`}
            </p>
          )}
          <button
            type="button"
            onClick={() => {
              openedThisSession = !open;
              setOpen(!open);
            }}
            aria-expanded={open}
            aria-label={open ? "Hide From your collection" : "Show From your collection"}
            className="studio-meta text-[10px] text-ink-muted transition-colors hover:text-ink-primary"
          >
            {open ? "HIDE" : "SHOW"}
          </button>
        </div>
      </div>
      {note && (
        <p role="status" className="border-t border-edge px-3 py-1.5 text-[12px] leading-snug text-ink-secondary">
          {note}
        </p>
      )}

      {open && (
        <div
          className={`${PANEL_MAX_HEIGHT} overflow-y-auto border-t border-edge px-3 py-2`}
          tabIndex={0}
          role="group"
          aria-label="From your collection"
        >
          <p className="text-[12px] leading-snug text-ink-secondary">
            New items you sent your bot whose words this draft shares, matched on this computer. These are your own
            words as you sent them; nothing here was written by a model.
          </p>
          {!value.trim() ? (
            <p className="studio-meta mt-2 leading-relaxed text-ink-muted">
              Start writing, and the new items in your collection that share its words appear here.
            </p>
          ) : failed ? (
            <p className="studio-meta mt-2 leading-relaxed text-ink-muted">
              The studio did not answer. It is read again when this window comes back.
            </p>
          ) : items === null ? (
            <p className="studio-meta mt-2 leading-relaxed text-ink-muted">READING YOUR COLLECTION</p>
          ) : shown.length === 0 ? (
            <p className="studio-meta mt-2 leading-relaxed text-ink-muted">
              Nothing new in your collection shares words with this draft. What you send your bot appears here when it
              does.
            </p>
          ) : (
            <ul className="mt-2 flex flex-col divide-y divide-edge border-y border-edge">
              {shown.map((item) => (
                <li key={item.id} className="flex flex-wrap items-start gap-x-3 gap-y-1 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="studio-meta text-[10px] text-ink-muted">
                      {item.kind_said} · {formatLocal(item.received_at)}
                      {item.topic ? ` · ${item.topic}` : ""}
                    </p>
                    <p className="mt-0.5 whitespace-pre-wrap break-words text-[13px] leading-snug text-ink-primary">
                      {item.text}
                    </p>
                    {item.link && (
                      <p className="mt-0.5 break-all text-[11px] text-ink-muted">Link kept: {item.link}</p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => add(item)}
                    aria-label={`Add to the draft: ${firstWords(item.text ?? "")}`}
                    className="shrink-0 rounded-md border border-edge px-2 py-0.5 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
                  >
                    Add to the draft
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

/**
 * What a draft the studio wrote was written from: the items, the things to
 * remember that went with it (by their words), and the provider. Shown only
 * on a draft that records it; a draft written by hand has nothing to say.
 */
export function MadeWithNote({ postId }: { postId?: string | null }) {
  const [made, setMade] = useState<MadeWith | null>(null);
  const [facts, setFacts] = useState<RememberedFact[] | null>(null);

  useEffect(() => {
    let live = true;
    setMade(null);
    setFacts(null);
    if (!postId) return;
    fetchMadeWith(postId)
      .then((found) => {
        if (!live || !found) return;
        setMade(found);
        if (found.remembered.length === 0) return;
        fetchRemembered()
          .then((held) => live && setFacts(held.facts))
          .catch(() => live && setFacts([]));
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [postId]);

  if (!made) return null;
  const count = made.items.length;
  const named = (facts ?? []).filter((fact) => made.remembered.includes(fact.id));
  const gone = facts ? made.remembered.length - named.length : 0;
  const by = made.provider ? `${made.provider}${made.model ? ` (${made.model})` : ""}` : "your AI provider";

  return (
    <section aria-labelledby="composer-made-with" className="mb-6 rounded-md border border-edge px-3 py-2">
      <h2 id="composer-made-with" className="studio-label">
        What this draft was written from
      </h2>
      <p className="mt-1 text-[12px] leading-snug text-ink-secondary">
        Written by {by}
        {made.at ? ` on ${formatLocal(made.at)}` : ""}, from {count === 1 ? "one item" : `${count} items`} in your
        collection{made.angle ? ", starting from the angle you picked" : ""}. It is your draft now: change anything.
      </p>
      {made.remembered.length === 0 ? (
        <p className="mt-1 text-[12px] leading-snug text-ink-muted">No things to remember went with it.</p>
      ) : facts === null ? (
        <p className="studio-meta mt-1 text-ink-muted">READING</p>
      ) : (
        <>
          <p className="mt-1 text-[12px] leading-snug text-ink-secondary">
            Things to remember that went with it, as set in Brand, under Writing:
          </p>
          <ul className="mt-0.5 flex flex-col gap-0.5 pl-3 text-[12px] leading-snug text-ink-primary">
            {named.map((fact) => (
              <li key={fact.id}>{fact.text}</li>
            ))}
          </ul>
          {gone > 0 && (
            <p className="mt-0.5 text-[11px] text-ink-muted">
              {gone === 1 ? "One more went with it and has since been removed." : `${gone} more went with it and have since been removed.`}
            </p>
          )}
        </>
      )}
    </section>
  );
}
