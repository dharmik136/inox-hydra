import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { SelectionToolbar, type ToolbarPosition } from "./SelectionToolbar";
import { formatText, type FormatKind } from "@/lib/api";
import { measurableLength, openingEnd, rawIndexAtMeasurableOffset } from "@/lib/text";

/**
 * LinkedIn collapses the post body behind "see more" at roughly this many
 * characters on mobile.
 *
 * This must equal MOBILE_FOLD_CHARS in studio/backend/fold.py. It was 180,
 * from the blueprint's "LINKEDIN FOLD / 180 CHARS" label, while the backend
 * settled on 140 for every check it runs: the audit, the hook generator, the
 * formatter and the ingress parser. The editor then drew its fold at 180 and
 * called a draft within it, and the Audit tab called the same draft over the
 * limit. One product, two answers to its central question.
 *
 * tests/test_fold_is_one_number.py reads both files and fails if they differ.
 */
export const FOLD_CHARS = 140;

/**
 * Margin the full fold label needs beside the column: the label itself, about
 * 52 pixels, its 12 pixel gap and a little slack. With less, as on a phone or
 * beside a docked inspector at 1024 pixels, it ran under the rail, so the
 * short form is drawn instead.
 */
const ROOM_FOR_FOLD_LABEL = 72;

interface ComposerCanvasProps {
  value: string;
  /**
   * `cleared` is true when this change emptied the editor or replaced all of
   * its text at once, as Select all and typing does: the author has started
   * a different post, and the draft they had must not be saved over.
   */
  onChange: (next: string, cleared?: boolean) => void;
  onReHook: (selection: string) => void;
  /** Bumped when a hook replaces the opening, to play the text transition. */
  swapKey: number;
  /** Ctrl+S or Cmd+S in the editor: the same as the Save button. */
  onSave?: () => void;
}

/** Ctrl or Cmd with these letters formats the selection, as the toolbar's buttons do. */
const FORMAT_KEYS: Record<string, FormatKind> = { b: "bold", i: "italic", u: "underline" };

/**
 * The main writing canvas (blueprint sections 7B, 7C and 7D).
 *
 * No enclosing card: the editor sits directly on the work surface. A hidden
 * mirror element carrying identical typography is laid out behind the textarea,
 * and every geometric question is answered by running a Range over it. That one
 * mechanism serves three jobs: where the fold falls, where a selection is on
 * screen, and how tall the textarea has to be.
 */
export function ComposerCanvas({ value, onChange, onReHook, swapKey, onSave }: ComposerCanvasProps) {
  const mirrorRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // Whether the whole text is selected, so a keystroke or paste that replaces
  // it can be told from an ordinary edit.
  const wholeSelected = useRef(false);
  const reduceMotion = useReducedMotion();

  const [foldTop, setFoldTop] = useState<number | null>(null);
  // Room between the scrolling area's edge and the column, for the label.
  const [gutter, setGutter] = useState<number | null>(null);
  // Bumped when the column or the area around it changes size: either moves
  // where the fold falls or how much margin the label has.
  const [layoutPass, setLayoutPass] = useState(0);
  const [height, setHeight] = useState<number | null>(null);
  const [toolbar, setToolbar] = useState<ToolbarPosition | null>(null);
  const [busy, setBusy] = useState(false);
  // Said when a format came back but could not be applied, so a press that
  // changed nothing does not look like one that was ignored.
  const [formatNote, setFormatNote] = useState<string | null>(null);
  useEffect(() => {
    if (!formatNote) return;
    const timer = window.setTimeout(() => setFormatNote(null), 6000);
    return () => window.clearTimeout(timer);
  }, [formatNote]);
  const [swap, setSwap] = useState<{ height: number; text: string } | null>(null);

  // The text as of the latest render, for a format request that comes back
  // after the author has typed more.
  const latestValue = useRef(value);
  latestValue.current = value;

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
  }, [value, layoutPass]);

  useEffect(() => {
    const mirror = mirrorRef.current;
    if (!mirror || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => setLayoutPass((pass) => pass + 1));
    observer.observe(mirror);
    const scroller = mirror.closest("main");
    if (scroller) observer.observe(scroller);
    return () => observer.disconnect();
  }, []);

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
    const scroller = mirrorRef.current?.closest("main")?.getBoundingClientRect();
    setGutter(mirrorBox && scroller ? mirrorBox.left - scroller.left : null);
  }, [value, crossed, rectsFor, layoutPass]);

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

    const paragraphBreak = openingEnd(value);
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
      setFormatNote(null);
      try {
        const formatted = await formatText(kind, selected);

        // Applied to the text as it is now, not as it was when the button was
        // pressed. Rebuilding from the old copy threw away whatever the author
        // typed while the request was out. Typing before the selection moves
        // the words without changing them, so they are found where they went;
        // if the words themselves changed, the format is dropped, not the
        // typing, and the author is told.
        const current = latestValue.current;
        let start = selectionStart;
        let end = selectionEnd;
        if (current.slice(start, end) !== selected) {
          const moved = current.length - value.length;
          const after = value.slice(selectionEnd);
          if (moved !== 0 && current.slice(start + moved, end + moved) === selected && current.endsWith(after)) {
            start += moved;
            end += moved;
          } else {
            setToolbar(null);
            setFormatNote("The formatting was not applied: the selected words changed while it was working. Select them and try again.");
            return;
          }
        }
        const caretStart = textarea.selectionStart;
        const caretEnd = textarea.selectionEnd;
        const stillSelected = caretStart === start && caretEnd === end;
        const shift = formatted.length - selected.length;
        onChange(current.slice(0, start) + formatted + current.slice(end));

        // Keep the same text selected so formatters can be chained. The end
        // offset moves, because a formatter changes how many code units the
        // selection occupies even when it reads the same length. An author
        // who moved on to type elsewhere keeps their caret instead.
        requestAnimationFrame(() => {
          textarea.focus();
          if (stillSelected) {
            textarea.setSelectionRange(start, start + formatted.length);
            syncToolbar();
          } else {
            const moved = (index: number) => (index >= end ? index + shift : index);
            textarea.setSelectionRange(moved(caretStart), moved(caretEnd));
          }
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
      {formatNote && (
        <p role="status" className="mb-3 text-[12px] leading-snug text-signal-orange-text">
          {formatNote}
        </p>
      )}
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
          onChange={(event) => {
            const next = event.target.value;
            const replacedAll = wholeSelected.current && value.length > 0;
            wholeSelected.current = false;
            onChange(next, value.trim().length > 0 && (next.trim().length === 0 || replacedAll));
          }}
          onSelect={() => {
            const textarea = textareaRef.current;
            wholeSelected.current =
              !!textarea && textarea.value.length > 0 && textarea.selectionStart === 0 &&
              textarea.selectionEnd === textarea.value.length;
            syncToolbar();
          }}
          onBlur={() => setToolbar(null)}
          onScroll={syncToolbar}
          // A writing tool's keys. Ctrl+S opened the browser's Save Page As
          // over the draft, and Ctrl+B did nothing.
          onKeyDown={(event) => {
            if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return;
            const key = event.key.toLowerCase();
            if (key === "s") {
              event.preventDefault();
              onSave?.();
            } else if (FORMAT_KEYS[key]) {
              event.preventDefault();
              void applyFormat(FORMAT_KEYS[key]);
            }
          }}
          aria-keyshortcuts="Control+S Control+B Control+I Control+U"
          spellCheck
          aria-label="Post body"
          // The one text field where Alt and a digit applies a hook.
          data-hook-shortcuts
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
            {gutter === null || gutter >= ROOM_FOR_FOLD_LABEL ? (
              <span className="studio-meta absolute top-0 right-full mr-3 -translate-y-1/2 text-right leading-tight text-[10px] tracking-wider text-signal-orange-text">
                LINKEDIN FOLD
                <br />
                {FOLD_CHARS} CHARS
              </span>
            ) : (
              <span className="studio-meta absolute top-0 right-full mr-1.5 -translate-y-1/2 text-right leading-tight text-[10px] tracking-wider text-signal-orange-text">
                FOLD
                <br />
                {FOLD_CHARS}
              </span>
            )}
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
