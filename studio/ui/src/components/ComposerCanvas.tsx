import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { SelectionToolbar, type ToolbarPosition } from "./SelectionToolbar";
import { formatText, type FormatKind } from "@/lib/api";
import { measurableLength, rawIndexAtMeasurableOffset } from "@/lib/text";

/**
 * LinkedIn collapses the post body behind "see more" at roughly this many
 * characters. Blueprint section 7C labels the mark "LINKEDIN FOLD / 180 CHARS",
 * so that is the number the ruler is drawn from.
 */
export const FOLD_CHARS = 180;

interface ComposerCanvasProps {
  value: string;
  onChange: (next: string) => void;
  onReHook: (selection: string) => void;
  /** Bumped when a hook replaces the opening, to play the text transition. */
  swapKey: number;
}

/**
 * The main writing canvas (blueprint sections 7B, 7C and 7D).
 *
 * No enclosing card: the editor sits directly on the work surface. A hidden
 * mirror element carrying identical typography is laid out behind the textarea,
 * and every geometric question is answered by running a Range over it. That one
 * mechanism serves three jobs: where the fold falls, where a selection is on
 * screen, and how tall the textarea has to be.
 */
export function ComposerCanvas({ value, onChange, onReHook, swapKey }: ComposerCanvasProps) {
  const mirrorRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const reduceMotion = useReducedMotion();

  const [foldTop, setFoldTop] = useState<number | null>(null);
  const [height, setHeight] = useState<number | null>(null);
  const [toolbar, setToolbar] = useState<ToolbarPosition | null>(null);
  const [busy, setBusy] = useState(false);
  const [swap, setSwap] = useState<{ height: number; text: string } | null>(null);

  // The fold is a reader-facing position, so it is measured on text with
  // decoration stripped. Using value.length here would move the mark every time
  // someone struck a line through, because each struck character carries a
  // second code point that no reader sees.
  const crossed = measurableLength(value) > FOLD_CHARS;

  /** Runs a Range over the mirror and returns its per-line rectangles. */
  const rectsFor = useCallback((start: number, end: number): DOMRect[] | null => {
    const mirror = mirrorRef.current;
    const textNode = mirror?.firstChild;
    if (!mirror || !textNode || textNode.nodeType !== Node.TEXT_NODE) return null;

    const length = textNode.textContent?.length ?? 0;
    const range = document.createRange();
    range.setStart(textNode, Math.min(start, length));
    range.setEnd(textNode, Math.min(end, length));
    return Array.from(range.getClientRects());
  }, []);

  // Keep the textarea exactly as tall as its content. Left to its own scrolling
  // the textarea would slide independently of the mirror, and every measurement
  // taken from the mirror would then describe a line that is somewhere else.
  useLayoutEffect(() => {
    const mirror = mirrorRef.current;
    if (mirror) setHeight(mirror.scrollHeight);
  }, [value]);

  useLayoutEffect(() => {
    if (!crossed) {
      setFoldTop(null);
      return;
    }

    // Translate the 180th character a reader sees into an index in the raw
    // string, which is what the DOM Range is addressed in.
    const rawEnd = rawIndexAtMeasurableOffset(value, FOLD_CHARS);
    const rects = rectsFor(0, rawEnd);
    const last = rects?.[rects.length - 1];
    const mirrorBox = mirrorRef.current?.getBoundingClientRect();

    // getClientRects gives one rectangle per visual line, so the last one is
    // the line the fold actually falls on. getBoundingClientRect would return
    // the union of them all and put the mark at the top of the post.
    setFoldTop(last && mirrorBox ? last.bottom - mirrorBox.top : null);
  }, [value, crossed, rectsFor]);

  /**
   * The opening paragraph settling into place (blueprint micro-interaction 3).
   *
   * The textarea already holds the new text by the time this runs, so the
   * overlay carries an opaque background: without it the incoming paragraph
   * would animate over a copy of itself. It covers only the first paragraph,
   * measured the same way everything else here is, so the rest of the post
   * does not move.
   */
  useEffect(() => {
    if (swapKey === 0) return;
    if (reduceMotion) return;

    const paragraphBreak = value.indexOf("\n\n");
    const rawEnd = paragraphBreak === -1 ? value.length : paragraphBreak;
    const rects = rectsFor(0, rawEnd);
    const mirrorBox = mirrorRef.current?.getBoundingClientRect();
    const last = rects?.[rects.length - 1];
    if (!last || !mirrorBox) return;

    setSwap({ height: last.bottom - mirrorBox.top, text: value.slice(0, rawEnd) });
    const timer = window.setTimeout(() => setSwap(null), 460);
    return () => window.clearTimeout(timer);
    // value is deliberately absent: this plays once per swap, not on every
    // keystroke that follows one.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [swapKey, reduceMotion, rectsFor]);

  /** Position the toolbar from whatever is currently selected. */
  const syncToolbar = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const { selectionStart, selectionEnd } = textarea;
    if (selectionStart === selectionEnd) {
      setToolbar(null);
      return;
    }

    const rects = rectsFor(selectionStart, selectionEnd);
    const first = rects?.[0];
    const mirrorBox = mirrorRef.current?.getBoundingClientRect();
    if (!first || !mirrorBox) {
      setToolbar(null);
      return;
    }

    // Anchored to the start of the selection rather than the middle of its
    // bounding box, so a selection spanning several lines does not park the
    // toolbar in the centre of the paragraph.
    setToolbar({
      left: first.left - mirrorBox.left + first.width / 2,
      top: first.top - mirrorBox.top,
    });
  }, [rectsFor]);

  const applyFormat = useCallback(
    async (kind: FormatKind) => {
      const textarea = textareaRef.current;
      if (!textarea) return;
      const { selectionStart, selectionEnd } = textarea;
      if (selectionStart === selectionEnd) return;

      const selected = value.slice(selectionStart, selectionEnd);
      setBusy(true);
      try {
        const formatted = await formatText(kind, selected);
        onChange(value.slice(0, selectionStart) + formatted + value.slice(selectionEnd));

        // Keep the same text selected so formatters can be chained. The end
        // offset moves, because a formatter changes how many code units the
        // selection occupies even when it reads the same length.
        requestAnimationFrame(() => {
          textarea.focus();
          textarea.setSelectionRange(selectionStart, selectionStart + formatted.length);
          syncToolbar();
        });
      } catch {
        // The selection is left exactly as it was. Nothing is reported as
        // having been formatted when the call did not come back.
        setToolbar(null);
      } finally {
        setBusy(false);
      }
    },
    [value, onChange, syncToolbar],
  );

  const handleReHook = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const { selectionStart, selectionEnd } = textarea;
    const selected = value.slice(selectionStart, selectionEnd);
    if (selected.trim()) onReHook(selected);
  }, [value, onReHook]);

  return (
    <div className="mx-auto w-full max-w-[68ch] px-10 py-12">
      <div className="relative">
        {/* Measuring mirror. Laid out so Ranges have real geometry to report,
            but hidden from sight and from assistive technology. It must keep
            the same font, size, line height, width and wrapping as the
            textarea or every measurement describes a different paragraph. */}
        <div
          ref={mirrorRef}
          aria-hidden="true"
          className="pointer-events-none invisible absolute inset-0 whitespace-pre-wrap break-words font-editorial text-[18px] leading-[1.75]"
        >
          {value}
        </div>

        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onSelect={syncToolbar}
          onBlur={() => setToolbar(null)}
          onScroll={syncToolbar}
          spellCheck
          aria-label="Post body"
          placeholder="Start writing. The fold mark appears once the post runs past it."
          style={height ? { height } : undefined}
          className="relative block min-h-[60vh] w-full resize-none overflow-hidden border-0 bg-transparent font-editorial text-[18px] leading-[1.75] text-ink-primary outline-none placeholder:text-ink-muted"
        />

        <AnimatePresence>
          {toolbar && (
            <SelectionToolbar
              position={toolbar}
              busy={busy}
              onFormat={applyFormat}
              onReHook={handleReHook}
            />
          )}
        </AnimatePresence>

        <AnimatePresence>
          {swap && (
            <motion.div
              key={swapKey}
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              /* Expressive tier: this is a canvas transition, not a hover. */
              transition={{ duration: 0.46, ease: [0.32, 0.72, 0.24, 1] }}
              aria-hidden="true"
              style={{ height: swap.height }}
              className="pointer-events-none absolute inset-x-0 top-0 z-10 overflow-hidden bg-canvas whitespace-pre-wrap break-words font-editorial text-[18px] leading-[1.75] text-ink-primary"
            >
              {swap.text}
            </motion.div>
          )}
        </AnimatePresence>

        {/* The crop mark. 1px dashed rule and a monospace annotation, drawn
            across the writing column only when the post has passed it. */}
        {crossed && foldTop !== null && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.22, ease: [0.32, 0.72, 0.24, 1] }}
            className="pointer-events-none absolute inset-x-0 z-10"
            style={{ top: foldTop }}
            aria-hidden="true"
          >
            <div className="border-t border-dashed border-signal-orange/60" />
            {/* Marginalia, not an overlay. Right aligned in the margin beside
                the column so the crop mark annotates the text instead of
                covering it, and stacked so it fits the narrow gutter that is
                left once the inspector is docked. */}
            <span className="studio-meta absolute top-0 right-full mr-3 -translate-y-1/2 text-right leading-tight text-[10px] tracking-wider text-signal-orange-text">
              LINKEDIN FOLD
              <br />
              {FOLD_CHARS} CHARS
            </span>
          </motion.div>
        )}
      </div>

      {/* The same fact stated once for screen readers, since the crop mark is
          purely visual and aria-hidden. */}
      <p className="sr-only" role="status" aria-live="polite">
        {crossed
          ? `Post runs past the LinkedIn fold at ${FOLD_CHARS} characters.`
          : `Post is within the ${FOLD_CHARS} character fold.`}
      </p>
    </div>
  );
}
