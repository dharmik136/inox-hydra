import { useLayoutEffect, useRef, useState } from "react";
import { motion } from "motion/react";

/**
 * LinkedIn collapses the post body behind "see more" at roughly this many
 * characters. Blueprint section 7C labels the mark "LINKEDIN FOLD / 180 CHARS",
 * so that is the number the ruler is drawn from.
 */
export const FOLD_CHARS = 180;

interface ComposerCanvasProps {
  value: string;
  onChange: (next: string) => void;
}

/**
 * The main writing canvas (blueprint section 7B and 7C).
 *
 * No enclosing card: the editor sits directly on the work surface. The fold is
 * an editorial crop mark rather than a glowing line, and its position is
 * MEASURED rather than estimated. A character count cannot tell you which
 * visual line the fold lands on, because that depends on where the text
 * wrapped, so a mirror element with identical typography is laid out and a
 * Range over the first 180 characters reports the real offset.
 */
export function ComposerCanvas({ value, onChange }: ComposerCanvasProps) {
  const mirrorRef = useRef<HTMLDivElement>(null);
  const [foldTop, setFoldTop] = useState<number | null>(null);

  const crossed = value.length > FOLD_CHARS;

  useLayoutEffect(() => {
    const mirror = mirrorRef.current;
    if (!mirror || !crossed) {
      setFoldTop(null);
      return;
    }

    const textNode = mirror.firstChild;
    if (!textNode || textNode.nodeType !== Node.TEXT_NODE) {
      setFoldTop(null);
      return;
    }

    const range = document.createRange();
    range.setStart(textNode, 0);
    range.setEnd(textNode, Math.min(FOLD_CHARS, textNode.textContent?.length ?? 0));

    // getClientRects returns one rect per visual line the range covers, so the
    // last one is the line the fold actually falls on. getBoundingClientRect
    // would return the union of all of them and place the mark at the top of
    // the post.
    const rects = range.getClientRects();
    const last = rects[rects.length - 1];
    if (!last) {
      setFoldTop(null);
      return;
    }

    const mirrorBox = mirror.getBoundingClientRect();
    setFoldTop(last.bottom - mirrorBox.top);
  }, [value, crossed]);

  return (
    <div className="mx-auto w-full max-w-[68ch] px-10 py-12">
      <div className="relative">
        {/* Measuring mirror. Laid out so the Range has real geometry to
            report, but hidden from sight and from assistive technology. It
            must keep the same font, size, line height, width and wrapping as
            the textarea or the measurement describes a different paragraph. */}
        <div
          ref={mirrorRef}
          aria-hidden="true"
          className="pointer-events-none invisible absolute inset-0 whitespace-pre-wrap break-words font-editorial text-[18px] leading-[1.75]"
        >
          {value}
        </div>

        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          spellCheck
          aria-label="Post body"
          placeholder="Start writing. The fold mark appears once the post runs past it."
          className="relative block min-h-[60vh] w-full resize-none border-0 bg-transparent font-editorial text-[18px] leading-[1.75] text-ink-primary outline-none placeholder:text-ink-muted"
        />

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
            <span className="studio-meta absolute top-0 right-full mr-3 -translate-y-1/2 text-right leading-tight text-[10px] tracking-wider text-signal-orange">
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
