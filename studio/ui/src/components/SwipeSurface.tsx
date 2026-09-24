import { useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
import { Search } from "lucide-react";
import { fetchInspirations, type Inspiration } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * The swipe file (blueprint section 12).
 *
 * A specimen wall rather than a three column card grid. Each entry shows the
 * hook, the one structural pattern that makes it work, its category and its
 * reach, and expands in place on hover.
 *
 * The masonry is CSS columns, not a measured grid. Specimens vary in length,
 * a row grid would pad every one of them to the tallest in the row, and a
 * measured layout would need a resize observer for no gain over what the
 * browser already does correctly.
 */
export function SwipeSurface() {
  const [specimens, setSpecimens] = useState<Inspiration[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState("");
  const [archetype, setArchetype] = useState<string>("All");

  useEffect(() => {
    let live = true;
    fetchInspirations()
      .then((rows) => live && setSpecimens(rows))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  const archetypes = useMemo(() => {
    if (!specimens) return [];
    return ["All", ...Array.from(new Set(specimens.map((s) => s.archetype))).sort()];
  }, [specimens]);

  const shown = useMemo(() => {
    if (!specimens) return [];
    const term = query.trim().toLowerCase();
    return specimens.filter((specimen) => {
      if (archetype !== "All" && specimen.archetype !== archetype) return false;
      if (!term) return true;
      return (
        specimen.content.toLowerCase().includes(term) ||
        (specimen.key_hook ?? "").toLowerCase().includes(term) ||
        specimen.topic.toLowerCase().includes(term)
      );
    });
  }, [specimens, query, archetype]);

  if (failed) return <Centered>SWIPE FILE UNAVAILABLE</Centered>;
  if (!specimens) return <Centered>LOADING SPECIMENS</Centered>;
  if (specimens.length === 0) return <Centered>NO SPECIMENS SAVED YET</Centered>;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-edge px-8 pt-6 pb-4">
        <div className="flex items-baseline justify-between gap-4">
          <p className="studio-label">Specimen wall</p>
          <p className="studio-meta text-[10px]">
            {shown.length} OF {specimens.length}
          </p>
        </div>

        <div className="mt-3 flex items-center gap-2">
          <div className="relative flex-1">
            <Search
              className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-muted"
              strokeWidth={1.75}
              aria-hidden="true"
            />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search specimens"
              aria-label="Search specimens"
              className="w-full rounded-md border border-edge bg-ink py-1.5 pr-3 pl-8 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
            />
          </div>
        </div>

        <ul className="mt-3 flex flex-wrap gap-1">
          {archetypes.map((candidate) => (
            <li key={candidate}>
              <button
                type="button"
                onClick={() => setArchetype(candidate)}
                aria-pressed={archetype === candidate}
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-[10px] tracking-wide uppercase",
                  "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
                  archetype === candidate
                    ? "border-edge-strong bg-soft text-ink-primary"
                    : "border-edge text-ink-muted hover:text-ink-secondary",
                )}
              >
                {candidate}
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* tabIndex makes the wall scrollable from the keyboard. A region
          that scrolls but holds no focusable child cannot otherwise be
          reached without a pointer, which axe reports as serious. */}
      <div
        className="min-h-0 flex-1 overflow-y-auto px-8 py-6"
        tabIndex={0}
        role="region"
        aria-label="Saved specimens"
      >
        {shown.length === 0 ? (
          <p className="studio-meta pt-8 text-center text-ink-muted">NOTHING MATCHES THAT</p>
        ) : (
          <div className="columns-1 gap-4 lg:columns-2 xl:columns-3 [&>*]:mb-4">
            {shown.map((specimen) => (
              <Specimen key={specimen.id} specimen={specimen} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Specimen({ specimen }: { specimen: Inspiration }) {
  const [open, setOpen] = useState(false);

  return (
    <motion.article
      onHoverStart={() => setOpen(true)}
      onHoverEnd={() => setOpen(false)}
      /* break-inside-avoid keeps a specimen from being split across two
         columns, which CSS multi column will happily do otherwise. */
      className="break-inside-avoid rounded-md border border-edge bg-ink p-4 transition-colors duration-(--studio-motion-fast) hover:border-edge-strong"
    >
      {/* The two fields carry the same value for every specimen the product
          seeds, so printing both rendered "CONTRARIAN TRUTHS · CONTRARIAN
          TRUTHS" on all 36 cards: a separator with nothing on either side of
          it. The topic is shown only when it says something the archetype has
          not already said, which keeps the pair meaningful if the two ever
          diverge. */}
      <p className="studio-meta text-[10px]">
        {specimen.archetype.toUpperCase()}
        {specimen.topic.trim().toLowerCase() !== specimen.archetype.trim().toLowerCase() && (
          <>
            <span className="mx-1.5 text-ink-muted">·</span>
            {specimen.topic.toUpperCase()}
          </>
        )}
      </p>

      <p className="mt-2 text-[13px] leading-snug font-medium text-ink-primary">
        {specimen.key_hook || specimen.content.split("\n")[0]}
      </p>

      {/* The structural pattern is the thing worth stealing, so it is shown
          rather than buried. pacing_style is the backend's own name for it. */}
      {specimen.pacing_style && (
        <p className="studio-meta mt-3 text-[10px] text-signal-blue">
          {specimen.pacing_style.toUpperCase()}
        </p>
      )}

      <motion.div
        initial={false}
        animate={{ height: open ? "auto" : 0, opacity: open ? 1 : 0 }}
        transition={{ duration: 0.22, ease: [0.32, 0.72, 0.24, 1] }}
        className="overflow-hidden"
      >
        <p className="mt-3 text-[12px] leading-relaxed whitespace-pre-line text-ink-secondary">
          {specimen.content}
        </p>
      </motion.div>

      <p className="studio-meta mt-3 border-t border-edge pt-2 text-[10px]">
        {specimen.likes_count.toLocaleString()} REACTIONS
        <span className="mx-1.5 text-ink-muted">·</span>
        {specimen.comments_count.toLocaleString()} COMMENTS
        <span className="mx-1.5 text-ink-muted">·</span>
        VELOCITY {specimen.velocity_score.toFixed(1)}
      </p>
    </motion.article>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}
