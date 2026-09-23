import { motion } from "motion/react";
import { Bold, Italic, Code, Strikethrough, Eraser, Sparkles } from "lucide-react";
import type { FormatKind } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface ToolbarPosition {
  /** Pixels from the left of the writing column, at the centre of the selection. */
  left: number;
  /** Pixels from the top of the writing column, at the top of the selection. */
  top: number;
}

interface SelectionToolbarProps {
  position: ToolbarPosition;
  busy: boolean;
  onFormat: (kind: FormatKind) => void;
  onReHook: () => void;
}

const FORMATTERS: { kind: FormatKind; label: string; icon: typeof Bold }[] = [
  { kind: "bold", label: "Bold", icon: Bold },
  { kind: "italic", label: "Italic", icon: Italic },
  { kind: "monospace", label: "Monospace", icon: Code },
  { kind: "strikethrough", label: "Strikethrough", icon: Strikethrough },
  { kind: "clean", label: "Clean formatting", icon: Eraser },
];

/**
 * The floating selection toolbar (blueprint section 7D).
 *
 * Springs in above the selection and follows it. Re-Hook is the only
 * high-attention action and carries signal orange, because it is the only one
 * that rewrites rather than decorates: the others can be undone by applying
 * their inverse, and Re-Hook replaces the author's sentence outright.
 */
export function SelectionToolbar({ position, busy, onFormat, onReHook }: SelectionToolbarProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 4, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 4, scale: 0.96 }}
      /* Spring, per the blueprint's tactile brief. Short enough that it does
         not lag behind a selection being dragged. */
      transition={{ type: "spring", stiffness: 520, damping: 32, mass: 0.6 }}
      role="toolbar"
      aria-label="Formatting"
      style={{ left: position.left, top: position.top }}
      className="absolute z-20 flex -translate-x-1/2 -translate-y-[calc(100%+10px)] items-center gap-0.5 rounded-md border border-edge bg-raised p-1 shadow-xl"
      /* The textarea loses focus on mousedown otherwise, which collapses the
         selection before the click ever lands. */
      onMouseDown={(event) => event.preventDefault()}
    >
      {FORMATTERS.map(({ kind, label, icon: Icon }) => (
        <button
          key={kind}
          type="button"
          disabled={busy}
          onClick={() => onFormat(kind)}
          aria-label={label}
          title={label}
          className={cn(
            "grid size-7 place-items-center rounded text-ink-secondary",
            "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
            "hover:bg-soft hover:text-ink-primary disabled:opacity-40",
          )}
        >
          <Icon className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
        </button>
      ))}

      <span className="mx-0.5 h-4 w-px bg-edge" aria-hidden="true" />

      <button
        type="button"
        disabled={busy}
        onClick={onReHook}
        aria-label="Re-hook this selection"
        title="Re-hook"
        className={cn(
          "flex items-center gap-1 rounded px-1.5 py-1 text-[11px] font-medium text-signal-orange",
          "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
          "hover:bg-signal-orange-subtle disabled:opacity-40",
        )}
      >
        <Sparkles className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
        Re-Hook
      </button>
    </motion.div>
  );
}
