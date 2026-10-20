/**
 * A surface with nothing to show yet, still introduced as itself.
 *
 * Posts, Patterns and Outbound are where a new creator lands before any
 * import. They used to answer with a single centred status line in 10px
 * uppercase monospace and no heading, so the first visit to each read as an
 * error code. The page keeps its label and title, and says in a sentence what
 * will be here and how to get it there, and ends in the button that does it:
 * the sentence said "Import them in Setup" with no way there but the rail.
 */
export function EmptySurface({
  label,
  title,
  children,
  onOpenSetup,
}: {
  label: string;
  title: string;
  children: React.ReactNode;
  onOpenSetup?: () => void;
}) {
  return (
    <article className="mx-auto max-w-[80ch] px-8 py-8">
      <p className="studio-label">{label}</p>
      <h1 className="studio-title mt-2">{title}</h1>
      <p className="mt-3 max-w-[60ch] text-[13px] leading-relaxed text-ink-secondary">{children}</p>
      {onOpenSetup && (
        <button
          type="button"
          onClick={onOpenSetup}
          className="mt-4 rounded-md bg-signal-orange px-3 py-1.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110"
        >
          Go to Setup
        </button>
      )}
    </article>
  );
}
