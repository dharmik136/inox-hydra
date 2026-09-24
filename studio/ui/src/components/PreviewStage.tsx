import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { fetchProfile, type ProfileResponse } from "@/lib/api";
import { FOLD_CHARS } from "./ComposerCanvas";
import { measurableLength, rawIndexAtMeasurableOffset } from "@/lib/text";
import { cn } from "@/lib/utils";

type Surface = "Mobile" | "Desktop" | "Carousel";

const SURFACES: Surface[] = ["Mobile", "Desktop", "Carousel"];

/**
 * The preview stage (blueprint section 9).
 *
 * The phone is an object sitting inside a neutral stage rather than a card
 * pinned to the side of the app. It can be pushed around a little and snaps
 * back, which is what makes it read as a physical thing on a surface.
 */
export function PreviewStage({ draft }: { draft: string }) {
  const [surface, setSurface] = useState<Surface>("Mobile");
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    fetchProfile()
      .then((result) => live && setProfile(result))
      .catch(() => {
        // Leaves profile null, which renders unnamed placeholders. That is the
        // same state a fresh install is in, so it needs no separate branch.
      });
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-1" role="tablist" aria-label="Preview surface">
        {SURFACES.map((candidate) => (
          <button
            key={candidate}
            type="button"
            role="tab"
            aria-selected={surface === candidate}
            onClick={() => setSurface(candidate)}
            className={cn(
              "rounded-md px-2 py-1 text-[11px] font-medium",
              "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
              surface === candidate ? "bg-soft text-ink-primary" : "text-ink-muted hover:text-ink-secondary",
            )}
          >
            {candidate}
          </button>
        ))}
      </div>

      {/* The stage. A recessed neutral ground so the device reads as an object
          resting on it rather than another panel in the chrome. */}
      <div
        ref={stageRef}
        className="grid min-h-[320px] place-items-center rounded-lg border border-edge bg-soft/40 p-4"
      >
        {surface === "Carousel" ? (
          <CarouselStage />
        ) : (
          <motion.div
            drag
            dragConstraints={stageRef}
            dragElastic={0.12}
            /* Snaps home when released, so the stage never ends up with the
               device parked in a corner the author has to put back. */
            dragSnapToOrigin
            dragMomentum={false}
            whileDrag={{ scale: 1.02, cursor: "grabbing" }}
            transition={{ type: "spring", stiffness: 320, damping: 30 }}
            className={cn(
              "w-full cursor-grab",
              surface === "Mobile"
                ? "max-w-[300px] rounded-[26px] border border-edge-strong bg-raised p-2 shadow-2xl"
                : "max-w-full rounded-lg border border-edge bg-raised p-3 shadow-xl",
            )}
          >
            <FeedPost draft={draft} profile={profile} surface={surface} />
          </motion.div>
        )}
      </div>
    </div>
  );
}

/**
 * The post as the feed renders it.
 *
 * Truncation applies on mobile only. The 180 character fold is a mobile
 * measurement, and this product has no sourced figure for where the desktop
 * feed cuts, so desktop shows the post whole rather than cutting it at a
 * number that would be invented.
 */
function FeedPost({
  draft,
  profile,
  surface,
}: {
  draft: string;
  profile: ProfileResponse | null;
  surface: Surface;
}) {
  const [expanded, setExpanded] = useState(false);
  const shortRef = useRef<HTMLParagraphElement>(null);
  const fullRef = useRef<HTMLParagraphElement>(null);
  const [heights, setHeights] = useState<{ short: number; full: number } | null>(null);

  const isMobile = surface === "Mobile";
  const collapses = isMobile && measurableLength(draft) > FOLD_CHARS;
  const cut = rawIndexAtMeasurableOffset(draft, FOLD_CHARS);
  const showFull = !collapses || expanded;

  // Both forms are measured, because the reveal animates between two real
  // heights. Clipping the full text to the height of the truncated text is not
  // the same thing and gets the common case wrong: a cut that lands part way
  // through the last line occupies the same number of lines as the whole post,
  // so nothing appears to be hidden at all while "see more" still sits there.
  useLayoutEffect(() => {
    if (shortRef.current && fullRef.current) {
      setHeights({ short: shortRef.current.offsetHeight, full: fullRef.current.offsetHeight });
    }
  }, [draft, surface]);

  useEffect(() => {
    // A new draft collapses again. Leaving it expanded would show the whole
    // post while claiming to be a preview of a feed that cuts it.
    setExpanded(false);
  }, [draft, surface]);

  const identity = profile?.is_set ? profile.profile : null;

  // One declaration for the visible text and both twins. If these drift, the
  // measured height describes a paragraph set at a different size.
  const bodyType = isMobile ? "text-[14px] leading-[1.55]" : "text-[15px] leading-[1.5]";

  return (
    <div className={cn("relative rounded-lg bg-raised", isMobile ? "p-3" : "p-4")}>
      <div className="flex items-center gap-2">
        <div className="size-9 shrink-0 rounded-full bg-soft" aria-hidden="true" />
        <div className="min-w-0">
          {identity ? (
            <>
              <p className="truncate text-[13px] font-medium text-ink-primary">{identity.name}</p>
              <p className="truncate text-[11px] text-ink-muted">{identity.headline || identity.company}</p>
            </>
          ) : (
            /* No name is invented. The backend flags an install that has never
               been told who its creator is, and names the feed simulator as a
               surface that must ask before rendering one. */
            <>
              <div className="h-2.5 w-28 rounded-full bg-soft" aria-hidden="true" />
              <div className="mt-1.5 h-2 w-20 rounded-full bg-soft/70" aria-hidden="true" />
            </>
          )}
        </div>
      </div>

      {/* Both forms, laid out and hidden, so each has a real height to read.
          Siblings of the visible text so they wrap at the same width. */}
      <div className="pointer-events-none invisible absolute inset-x-3" aria-hidden="true">
        <p ref={shortRef} className={cn("whitespace-pre-wrap", bodyType)}>
          {draft.slice(0, cut)}
        </p>
        <p ref={fullRef} className={cn("whitespace-pre-wrap", bodyType)}>
          {draft}
        </p>
      </div>

      <motion.div
        animate={{ height: heights ? (showFull ? heights.full : heights.short) : "auto" }}
        transition={{ duration: 0.38, ease: [0.32, 0.72, 0.24, 1] }}
        className="mt-3 overflow-hidden"
      >
        <p className={cn("whitespace-pre-wrap text-ink-primary", bodyType)}>
          {/* Collapsed shows the truncated text, not the whole post behind a
              shorter window. The feed removes what is past the cut, so a
              preview that merely clips it is showing the author something
              LinkedIn will not. */}
          {draft ? (
            showFull ? draft : draft.slice(0, cut)
          ) : (
            <span className="text-ink-muted">Nothing written yet.</span>
          )}
        </p>
      </motion.div>

      {/* The control lifts away rather than vanishing, and only exists while
          there is something still hidden. */}
      <AnimatePresence>
        {collapses && !expanded && (
          <motion.button
            type="button"
            initial={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.22, ease: [0.32, 0.72, 0.24, 1] }}
            onClick={() => setExpanded(true)}
            className="mt-1 text-[13px] text-ink-muted underline-offset-2 hover:underline"
          >
            ... see more
          </motion.button>
        )}
      </AnimatePresence>

      <p className="studio-meta mt-4 border-t border-edge pt-3">
        {isMobile
          ? collapses
            ? `COLLAPSES AT ${FOLD_CHARS} CHARS`
            : "FITS ABOVE THE FOLD"
          : `SHOWN WHOLE. THE ${FOLD_CHARS} CHAR FOLD IS A MOBILE MEASUREMENT`}
      </p>
    </div>
  );
}

/**
 * Carousel slides are produced by the carousel engine against a saved draft,
 * and the composer does not generate them. Rather than mock a filmstrip, this
 * says where they come from.
 */
function CarouselStage() {
  return (
    <p className="studio-meta max-w-[34ch] text-center leading-relaxed text-ink-muted">
      NO CAROUSEL SLIDES FOR THIS DRAFT
      <br />
      <span className="text-ink-muted">GENERATED BY THE CAROUSEL ENGINE, NOT THE COMPOSER</span>
    </p>
  );
}
