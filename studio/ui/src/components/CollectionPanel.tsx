import { useCallback, useEffect, useState } from "react";
import {
  anglesForItem,
  draftFromCollection,
  fetchCollection,
  fetchDraftById,
  photoToMediaLibrary,
  removeCollectionItem,
  setCollectionStatus,
  writeFromCollection,
  type CollectionItem,
  type CollectionKind,
  type CollectionMedia,
  type CollectionListing,
  type CollectionStatus,
} from "@/lib/api";
import { useRefresh } from "@/lib/refresh";
import { formatLocal } from "@/lib/time";
import { cn } from "@/lib/utils";
import { useWritingPreferences, WritingSummary } from "./WritingPreferences";

/** Combine takes this many at most, as the server does, so one request stays small. */
const COMBINE_AT_MOST = 10;

/**
 * Your collection: everything the creator sent their Telegram bot, in one
 * place (phase 3 of the bot, docs/quality/cycle4/collection-box.md).
 *
 * A level of From your record, which is "what is worth writing from today":
 * the collection is the creator's own material for that. Each item says
 * what it is, when it came, its words, and what it became; nothing is
 * written from an item until the creator asks. It reads again when the
 * studio says the collection changed, so a message sent from the phone is
 * here without a reload.
 */
const STATUS_TABS: [CollectionStatus | "all", string][] = [
  ["new", "New"],
  ["not_now", "Not now"],
  ["used", "Used"],
  ["all", "All"],
];

const KIND_CHOICES: [CollectionKind | "", string][] = [
  ["", "Every kind"],
  ["note", "Notes"],
  ["idea", "Ideas"],
  ["forward", "Forwarded"],
  ["bookmark", "Bookmarks"],
  ["post", "Your posts"],
  ["link", "Links"],
  ["photo", "Photos"],
  ["voice", "Voice notes"],
];

export function CollectionPanel({
  onOpenDraft,
}: {
  onOpenDraft?: (draft: { id: string; content: string }) => void;
} = {}) {
  const [status, setStatus] = useState<CollectionStatus | "all">("new");
  const [kind, setKind] = useState<CollectionKind | "">("");
  const [words, setWords] = useState("");
  const [listing, setListing] = useState<CollectionListing | null>(null);
  const [failed, setFailed] = useState(false);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);
  const [chosen, setChosen] = useState<number[]>([]);
  const [writingNow, setWritingNow] = useState<string | null>(null);
  const [described] = useWritingPreferences();
  const angleCount = described?.values.angles;

  const load = useCallback(() => {
    return fetchCollection({ status, kind, q: words })
      .then((data) => {
        setListing(data);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, [status, kind, words]);

  useEffect(() => {
    void load();
  }, [load]);
  // A message from the phone, or a change made on another screen, says so.
  useRefresh(load, undefined, ["collection"]);

  async function act(item: CollectionItem, work: () => Promise<unknown>, said?: string) {
    setBusy(item.id);
    setNote(null);
    try {
      await work();
      if (said) setNote({ text: said, error: false });
      await load();
    } catch (error) {
      setNote({ text: error instanceof Error ? error.message : "That did not work.", error: true });
    } finally {
      setBusy(null);
      setConfirming(null);
    }
  }

  async function useAsDraft(item: CollectionItem) {
    setBusy(item.id);
    setNote(null);
    try {
      const made = await draftFromCollection(item.id);
      await load();
      onOpenDraft?.(made);
    } catch (error) {
      setNote({ text: error instanceof Error ? error.message : "The draft was not made.", error: true });
    } finally {
      setBusy(null);
    }
  }

  /** Make a post (one item, maybe from an angle) or Combine: the provider writes, the Composer opens it. */
  async function write(ids: number[], angle?: string) {
    setBusy(ids.length === 1 ? ids[0] : -1);
    setNote(null);
    setWritingNow(ids.length > 1 ? `Writing one post from ${ids.length} items with your provider.` : "Writing it up with your provider.");
    try {
      const made = await writeFromCollection(ids, angle);
      if (made.status === "drafted") {
        setChosen([]);
        await load();
        onOpenDraft?.({ id: made.id, content: made.content });
      } else {
        setNote({ text: made.said, error: made.status === "refused" });
      }
    } catch (error) {
      setNote({ text: error instanceof Error ? error.message : "Nothing was written.", error: true });
    } finally {
      setBusy(null);
      setWritingNow(null);
    }
  }

  async function findAngles(item: CollectionItem) {
    setBusy(item.id);
    setNote(null);
    setWritingNow("Finding angles with your provider.");
    try {
      const found = await anglesForItem(item.id);
      if (found.status === "success") await load();
      else setNote({ text: found.said, error: found.status === "refused" });
    } catch (error) {
      setNote({ text: error instanceof Error ? error.message : "No angles were found.", error: true });
    } finally {
      setBusy(null);
      setWritingNow(null);
    }
  }

  function choose(item: CollectionItem, on: boolean) {
    setChosen((current) => (on ? [...current, item.id].slice(0, COMBINE_AT_MOST) : current.filter((id) => id !== item.id)));
  }

  async function openDraft(postId: string) {
    try {
      const post = await fetchDraftById(postId);
      if (!post) {
        setNote({ text: "That is no longer a draft: it is in the Queue, or published.", error: false });
        return;
      }
      onOpenDraft?.(post);
    } catch (error) {
      setNote({ text: error instanceof Error ? error.message : "That draft could not be opened.", error: true });
    }
  }

  const counts = listing?.counts;

  return (
    <section aria-labelledby="collection-title" className="flex max-w-3xl flex-col gap-3">
      <div>
        <h2 id="collection-title" className="studio-label mb-1">
          Your collection
        </h2>
        <p className="text-[12px] leading-relaxed text-ink-secondary">
          Everything you send your Telegram bot lands here as it arrives: notes, ideas, messages you forward, and
          links. A link to someone else&apos;s post is a bookmark, never opened by the studio; a link to one of yours
          is also on Today. Nothing is written from an item until you ask.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <nav aria-label="Collection by status" className="flex flex-wrap items-center gap-1">
          {STATUS_TABS.map(([id, label]) => (
            <button
              key={id}
              type="button"
              aria-pressed={status === id}
              onClick={() => setStatus(id)}
              className={cn(
                "rounded-md px-2.5 py-1 text-[12px] transition-colors",
                status === id ? "bg-soft text-ink-primary" : "text-ink-secondary hover:text-ink-primary",
              )}
            >
              {label}
              {counts ? ` (${counts[id].toLocaleString()})` : ""}
            </button>
          ))}
        </nav>
        <label htmlFor="collection-kind" className="sr-only">
          Kind of item
        </label>
        <select
          id="collection-kind"
          value={kind}
          onChange={(event) => setKind(event.target.value as CollectionKind | "")}
          className="rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary"
        >
          {KIND_CHOICES.map(([value, label]) => (
            <option key={label} value={value}>
              {label}
            </option>
          ))}
        </select>
        <label htmlFor="collection-words" className="sr-only">
          Find a word in your collection
        </label>
        <input
          id="collection-words"
          type="search"
          value={words}
          maxLength={200}
          placeholder="Find a word"
          onChange={(event) => setWords(event.target.value)}
          className="min-w-[10rem] flex-1 rounded-md border border-edge bg-ink px-2 py-1 text-[12px] text-ink-primary placeholder:text-ink-muted"
        />
      </div>

      <WritingSummary
        described={described}
        fields={["length_words", "tone", "language", "opening", "emojis", "hashtags", "line_breaks", "ending", "avoid", "angles", "memory"]}
        title="How Make a post, Combine and Angles write"
      />

      {chosen.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-ink-secondary">
          <span>
            {chosen.length} chosen{chosen.length < 2 ? ": choose one more to combine" : ""}
          </span>
          {chosen.length >= 2 && (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => void write(chosen)}
              className="rounded-md border border-edge px-2 py-0.5 hover:text-ink-primary disabled:opacity-40"
            >
              Combine {chosen.length} into one post
            </button>
          )}
          <button type="button" onClick={() => setChosen([])} className="underline underline-offset-2 hover:text-ink-primary">
            Clear
          </button>
        </div>
      )}

      {writingNow && (
        <p role="status" className="studio-meta text-ink-muted">
          {writingNow.toUpperCase()}
        </p>
      )}
      {note && (
        <p role="status" className={cn("text-[12px]", note.error ? "text-signal-orange-text" : "text-ink-secondary")}>
          {note.text}
        </p>
      )}

      {listing === null ? (
        <p className="studio-meta text-ink-muted">{failed ? "YOUR COLLECTION IS UNAVAILABLE. IS THE STUDIO RUNNING?" : "READING"}</p>
      ) : listing.items.length === 0 ? (
        <p className="text-[12px] text-ink-muted">
          {counts?.all
            ? "Nothing here with these filters."
            : "Nothing yet. Send your bot a thought, an idea, or a link, and it appears here."}
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-edge">
          {listing.items.map((item) => (
            <li key={item.id} className="py-2.5">
              <p className="flex flex-wrap items-baseline gap-x-2 text-[11px] text-ink-muted">
                {item.text && item.status !== "used" && (
                  <input
                    type="checkbox"
                    className="self-center"
                    aria-label={`Choose to combine: ${item.text.slice(0, 40)}`}
                    checked={chosen.includes(item.id)}
                    onChange={(event) => choose(item, event.target.checked)}
                  />
                )}
                <span className="studio-meta text-ink-secondary">{item.kind_said.toUpperCase()}</span>
                <span>{formatLocal(item.received_at)}</span>
                {item.source === "studio" && <span>from this computer</span>}
                {item.topic && <span>topic: {item.topic}</span>}
                {item.messages > 1 && <span>from {item.messages} of your messages</span>}
                {item.tags.length > 0 && <span>{item.tags.map((tag) => `#${tag}`).join(" ")}</span>}
              </p>
              {item.media && <KeptAsItIs item={item} media={item.media} />}
              {item.text && (
                <p className="mt-1 whitespace-pre-line text-[13px] leading-relaxed text-ink-primary">{item.text}</p>
              )}
              {item.link && (
                <a
                  href={item.link}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 block truncate text-[12px] text-ink-secondary underline decoration-edge-strong underline-offset-2 hover:text-ink-primary"
                >
                  {item.link}
                </a>
              )}
              {item.angles && item.angles.length > 0 && (
                <ol className="mt-1.5 flex list-decimal flex-col gap-1 pl-5 text-[12px] text-ink-secondary">
                  {item.angles.map((angle) => (
                    <li key={angle}>
                      <span className="text-ink-primary">{angle}</span>{" "}
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() => void write([item.id], angle)}
                        className="underline underline-offset-2 hover:text-ink-primary disabled:opacity-40"
                      >
                        Write it up
                      </button>
                    </li>
                  ))}
                </ol>
              )}
              {item.became && (
                <p className="mt-1 text-[12px] text-ink-secondary">
                  {item.became.kind === "draft" ? "Became: " : ""}
                  {item.became.said}
                  {item.became.kind === "draft" && item.became.post_id && onOpenDraft && (
                    <>
                      {" "}
                      <button
                        type="button"
                        onClick={() => void openDraft(item.became!.post_id!)}
                        className="underline underline-offset-2 hover:text-ink-primary"
                      >
                        Open it
                      </button>
                    </>
                  )}
                </p>
              )}
              <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[12px] text-ink-secondary">
                {item.text && (
                  <button
                    type="button"
                    disabled={busy !== null}
                    onClick={() => void write([item.id])}
                    className="rounded-md border border-edge px-2 py-0.5 hover:text-ink-primary disabled:opacity-40"
                  >
                    Make a post
                  </button>
                )}
                {item.text && (
                  <button
                    type="button"
                    disabled={busy !== null}
                    onClick={() => void findAngles(item)}
                    className="rounded-md border border-edge px-2 py-0.5 hover:text-ink-primary disabled:opacity-40"
                  >
                    {angleCount ? `${angleCount} angles` : "Angles"}
                  </button>
                )}
                {item.kind === "photo" && item.media && !item.became && (
                  <button
                    type="button"
                    disabled={busy === item.id}
                    onClick={() =>
                      void act(
                        item,
                        () => photoToMediaLibrary(item.id),
                        "In your media library: the Composer's Media tab lists it with your other images.",
                      )
                    }
                    className="rounded-md border border-edge px-2 py-0.5 hover:text-ink-primary disabled:opacity-40"
                  >
                    Add to your media library
                  </button>
                )}
                {item.text && (
                  <button
                    type="button"
                    disabled={busy === item.id}
                    onClick={() => void useAsDraft(item)}
                    className="rounded-md border border-edge px-2 py-0.5 hover:text-ink-primary disabled:opacity-40"
                  >
                    Use as a draft
                  </button>
                )}
                {item.status === "new" && (
                  <button
                    type="button"
                    disabled={busy === item.id}
                    onClick={() => void act(item, () => setCollectionStatus(item.id, "not_now"), "Set aside: it is under Not now.")}
                    className="underline underline-offset-2 hover:text-ink-primary disabled:opacity-40"
                  >
                    Not now
                  </button>
                )}
                {item.status === "not_now" && (
                  <button
                    type="button"
                    disabled={busy === item.id}
                    onClick={() => void act(item, () => setCollectionStatus(item.id, "new"), "Back with the new ones.")}
                    className="underline underline-offset-2 hover:text-ink-primary disabled:opacity-40"
                  >
                    Back to new
                  </button>
                )}
                {confirming === item.id ? (
                  <span className="flex items-center gap-2">
                    <span className="text-ink-primary">Remove it for good?</span>
                    <button
                      type="button"
                      disabled={busy === item.id}
                      onClick={() => void act(item, () => removeCollectionItem(item.id), "Removed from your collection.")}
                      className="underline underline-offset-2 hover:text-ink-primary disabled:opacity-40"
                    >
                      Remove
                    </button>
                    <button type="button" onClick={() => setConfirming(null)} className="underline underline-offset-2 hover:text-ink-primary">
                      Keep it
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirming(item.id)}
                    className="underline underline-offset-2 hover:text-ink-primary"
                  >
                    Remove
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Bytes as a person reads them. */
function sizeOf(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * A photo or a voice note as it was sent (phase 3, item 4): shown or played
 * from the profile's own folder, and never read. No text is taken from a
 * photo and no words from a voice note; a caption is the creator's own.
 */
function KeptAsItIs({ item, media }: { item: CollectionItem; media: CollectionMedia }) {
  const facts = [
    media.width && media.height ? `${media.width} x ${media.height}` : null,
    media.duration ? `${media.duration} s` : null,
    sizeOf(media.bytes),
  ].filter(Boolean);
  return (
    <div className="mt-1.5 flex flex-col gap-1">
      {item.kind === "photo" ? (
        <img
          src={media.path}
          alt={item.text ? `Your photo: ${item.text.split("\n")[0]}` : "A photo you sent your bot"}
          loading="lazy"
          className="max-h-48 max-w-full self-start rounded-md border border-edge object-contain"
        />
      ) : (
        <audio
          controls
          preload="none"
          src={media.path}
          aria-label={media.duration ? `Your voice note, ${media.duration} seconds` : "Your voice note"}
          className="max-w-full"
        />
      )}
      <p className="studio-meta text-[10px] text-ink-muted">
        {facts.join(" · ")} · KEPT AS IT IS: {item.kind === "photo" ? "NEVER READ" : "NEVER TRANSCRIBED"}
      </p>
    </div>
  );
}
