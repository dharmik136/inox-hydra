import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { X } from "lucide-react";
import { fetchHookTemplates, type GeneratedHook, type HookTemplate } from "@/lib/api";
import { cn } from "@/lib/utils";

interface HookFilmstripProps {
  onApply: (hook: string) => void;
  /** Alternatives produced from a selection. When set, these replace the library. */
  generated: GeneratedHook[] | null;
  onClearGenerated: () => void;
}

/** How many specimens carry a keyboard shortcut. Alt and a digit, so 1 to 9. */
const SHORTCUT_LIMIT = 9;

/** One strip entry, whichever source it came from. */
interface Specimen {
  key: string;
  category: string;
  text: string;
  /**
   * The ranking under its own name. The two sources score differently: the
   * vault stores a velocity score, generated hooks come back with a predicted
   * one. Showing them under a single label would imply they are comparable.
   */
  score: { label: string; value: number } | null;
  /** Generated hooks report whether they clear the fold. The vault does not. */
  fits: boolean | null;
}

/**
 * The hook rail (blueprint section 7A).
 *
 * A horizontal contact sheet of thin specimens rather than a carousel of 260px
 * cards. Every field shown is one that actually exists, under the name it has
 * on the server. Neither number is presented as a CTR or a confidence
 * percentage, because the product holds neither, and a number with the wrong
 * label is worse than no number.
 *
 * The two sources are not interchangeable. The vault stores a velocity score
 * and nothing about the fold; generated hooks come back with a predicted score
 * and a mobile_safe flag. So each is labelled for what it is, and the fold
 * verdict appears only on the specimens that actually carry one.
 */
export function HookFilmstrip({ onApply, generated, onClearGenerated }: HookFilmstripProps) {
  const [templates, setTemplates] = useState<HookTemplate[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    fetchHookTemplates(12)
      .then((rows) => live && setTemplates(rows))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  const specimens: Specimen[] | null = generated
    ? generated.map((hook, index) => ({
        key: `generated-${index}`,
        category: hook.archetype,
        text: hook.hook_text,
        score: { label: "SCORE", value: hook.predicted_score },
        fits: hook.mobile_safe,
      }))
    : templates?.map((template) => ({
        key: `template-${template.id}`,
        category: template.archetype,
        text: template.hook_text,
        score: { label: "VELOCITY", value: template.velocity_score },
        fits: null,
      })) ?? null;

  // Alt and a digit applies that specimen. Alt rather than a bare digit
  // because the composer is a text field and bare digits belong to the author.
  useEffect(() => {
    if (!specimens?.length) return;
    const onKey = (event: KeyboardEvent) => {
      if (!event.altKey || event.ctrlKey || event.metaKey) return;
      const position = Number(event.key);
      if (!Number.isInteger(position) || position < 1 || position > SHORTCUT_LIMIT) return;
      const chosen = specimens[position - 1];
      if (!chosen) return;
      event.preventDefault();
      onApply(chosen.text);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [specimens, onApply]);

  if (failed && !generated) return <StripNotice>HOOK LIBRARY UNAVAILABLE</StripNotice>;
  if (!specimens) return <StripNotice>LOADING HOOKS</StripNotice>;
  if (specimens.length === 0) return <StripNotice>NO HOOKS IN THE LOCAL LIBRARY YET</StripNotice>;

  return (
    <section aria-label="Hook archetypes" className="shrink-0 border-b border-edge">
      <div className="flex items-baseline justify-between gap-3 px-10 pt-3">
        <p className="studio-label">{generated ? "Generated from selection" : "Hook rail"}</p>
        <div className="flex items-center gap-3">
          <p className="studio-meta text-[10px] text-ink-muted">ALT + NUMBER TO APPLY</p>
          {generated && (
            <button
              type="button"
              onClick={onClearGenerated}
              className="studio-meta flex items-center gap-1 text-[10px] text-ink-muted transition-colors hover:text-ink-primary"
            >
              <X className="size-3" strokeWidth={2} aria-hidden="true" />
              BACK TO LIBRARY
            </button>
          )}
        </div>
      </div>

      {/* Horizontal contact sheet. Scrolls rather than wraps, so the strip
          stays one line deep however many specimens are vaulted. */}
      <ul className="flex gap-2 overflow-x-auto px-10 py-3">
        {specimens.map((specimen, index) => (
          <li key={specimen.key} className="shrink-0">
            <motion.button
              type="button"
              onClick={() => onApply(specimen.text)}
              /* Expands in place on hover. whileHover keeps the resting state
                 in the layout, so neighbours do not shift as the pointer
                 travels along the strip. */
              whileHover={{ y: -2 }}
              transition={{ duration: 0.12, ease: [0.32, 0.72, 0.24, 1] }}
              aria-label={`Apply ${specimen.category} hook: ${specimen.text}`}
              className={cn(
                "group flex h-full w-64 flex-col items-start gap-1.5 rounded-md border border-edge bg-ink p-3 text-left",
                "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
                "hover:border-edge-strong hover:bg-raised",
              )}
            >
              <span className="flex w-full items-center justify-between gap-2">
                <span className="studio-meta truncate text-[10px] tracking-wider text-ink-muted">
                  {String(index + 1).padStart(2, "0")}
                  <span className="mx-1.5">·</span>
                  {specimen.category.toUpperCase()}
                </span>
                {index < SHORTCUT_LIMIT && (
                  <kbd className="studio-meta shrink-0 rounded border border-edge px-1 text-[9px] text-ink-muted">
                    ALT {index + 1}
                  </kbd>
                )}
              </span>

              {/* Three lines, then clipped. A specimen is a sample of the hook,
                  not the hook in full. */}
              <span className="line-clamp-3 text-[12px] leading-snug whitespace-pre-line text-ink-secondary group-hover:text-ink-primary">
                {specimen.text}
              </span>

              <span className="studio-meta mt-auto flex w-full items-center justify-between gap-2 text-[10px] text-ink-muted">
                {specimen.score && (
                  <span>
                    {specimen.score.label} {specimen.score.value.toFixed(1)}
                  </span>
                )}
                {specimen.fits !== null && (
                  <span className={specimen.fits ? "text-signal-green" : "text-signal-orange-text"}>
                    {specimen.fits ? "FITS FOLD" : "PAST FOLD"}
                  </span>
                )}
              </span>
            </motion.button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function StripNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="shrink-0 border-b border-edge px-10 py-3">
      <p className="studio-meta text-ink-muted">{children}</p>
    </div>
  );
}
