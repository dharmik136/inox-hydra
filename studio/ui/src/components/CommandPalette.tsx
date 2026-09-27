import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Command } from "cmdk";
import { AnimatePresence, motion } from "motion/react";
import {
  ArrowRight,
  BookOpen,
  Bookmark,
  CornerDownLeft,
  FileText,
  Loader2,
  Search,
  SunMoon,
  PanelRight,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { type SectionId, type StudioSection } from "@/lib/navigation";
import { searchEverything, type SearchResponse, type SearchResult, type SearchOpens } from "@/lib/api";
import { highlightRuns, matchesAll, termsOf } from "@/lib/search";
import { readableSnippet } from "@/lib/snippet";
import { InlineText } from "@/components/DocumentView";
import { cn } from "@/lib/utils";

/**
 * Universal search, in the command palette.
 *
 * The palette searched a list of its own actions and nothing else. A post
 * from last week, a lead whose name you half remember, the specimen with the
 * opening you liked, the help article on what leaves this machine: none could
 * be reached from here, and an earlier post could not be reached from
 * anywhere.
 *
 * It also offered five actions that did not do what they said. "Generate 5
 * hooks", "Make sharper", "Add contrarian angle", "Turn into carousel" and
 * "Schedule at peak slot" each only switched screens, which the help had to
 * explain as a quirk. They are gone. What is left does exactly what its label
 * says, and everything else is a search result that opens the thing it names.
 *
 * Every query goes to this machine's own server and nowhere else.
 */

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The sections the rail offers. Devtools is absent when it is switched off. */
  sections: StudioSection[];
  onNavigate: (id: SectionId) => void;
  onToggleTheme: () => void;
  onToggleInspector: () => void;
  onOpenResult: (result: SearchResult) => void;
}

interface PaletteAction {
  id: string;
  label: string;
  hint?: string;
  icon: LucideIcon;
  run: () => void;
}

/** What opening a result does, in the words the interface uses. */
const OPENS: Record<SearchOpens, string> = {
  composer: "Opens in Composer",
  queue: "Opens Queue",
  analytics: "Opens Analytics",
  leads: "Opens the lead",
  swipe: "Shows in Swipe File",
  docs: "Opens the article",
};

const GROUPS: { key: keyof SearchResponse["groups"]; heading: string; icon: LucideIcon }[] = [
  { key: "posts", heading: "Posts", icon: FileText },
  { key: "leads", heading: "Leads", icon: UserRound },
  { key: "specimens", heading: "Swipe File", icon: Bookmark },
  { key: "help", heading: "Help", icon: BookOpen },
];

/** Typing settles before the server is asked. Local SQLite, so this is about intent, not cost. */
const DEBOUNCE_MS = 160;

export function CommandPalette({
  open,
  onOpenChange,
  sections,
  onNavigate,
  onToggleTheme,
  onToggleInspector,
  onOpenResult,
}: CommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Responses can arrive out of order; only the latest request may land. */
  const sequence = useRef(0);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      // metaKey covers macOS, ctrlKey covers Windows and Linux.
      if (event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        onOpenChange(!open);
        return;
      }
      // cmdk binds Escape only inside Command.Dialog, and this palette renders
      // a bare Command in its own animated overlay, so it binds it here.
      if (event.key === "Escape" && open) {
        event.preventDefault();
        onOpenChange(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  // A fresh palette every time it opens, rather than last time's results
  // sitting under a query that has been cleared.
  useEffect(() => {
    if (!open) {
      setQuery("");
      setResponse(null);
      setError(null);
      setSearching(false);
    }
  }, [open]);

  const terms = useMemo(() => termsOf(query), [query]);

  useEffect(() => {
    if (!terms.length) {
      setResponse(null);
      setSearching(false);
      setError(null);
      return;
    }
    const mine = ++sequence.current;
    setSearching(true);
    const timer = window.setTimeout(() => {
      searchEverything(terms.join(" "))
        .then((result) => {
          if (mine !== sequence.current) return;
          setResponse(result);
          setError(null);
        })
        .catch((caught) => {
          if (mine !== sequence.current) return;
          setResponse(null);
          setError(caught instanceof Error ? caught.message : "The search could not run.");
        })
        .finally(() => {
          if (mine === sequence.current) setSearching(false);
        });
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [terms]);

  const actions: PaletteAction[] = useMemo(
    () => [
      ...sections.map<PaletteAction>((section) => ({
        id: `go-${section.id}`,
        label: `Go to ${section.label}`,
        hint: section.blurb,
        icon: section.icon,
        run: () => onNavigate(section.id),
      })),
      { id: "theme", label: "Switch theme", hint: "Light and dark", icon: SunMoon, run: onToggleTheme },
      {
        id: "inspector",
        label: "Show or hide the inspector",
        hint: "On the Composer",
        icon: PanelRight,
        run: () => {
          onNavigate("composer");
          onToggleInspector();
        },
      },
    ],
    [sections, onNavigate, onToggleTheme, onToggleInspector],
  );

  const shownActions = terms.length
    ? actions.filter((action) => matchesAll(`${action.label} ${action.hint ?? ""}`, terms)).slice(0, 4)
    : actions;

  const run = (thunk: () => void) => {
    thunk();
    onOpenChange(false);
  };

  const failedGroups = response ? Object.keys(response.failures) : [];
  const nothing =
    terms.length > 0 && !searching && !error && response !== null && response.total === 0 && shownActions.length === 0;

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.12 }}
          className="fixed inset-0 z-50 grid place-items-start justify-center bg-canvas/70 p-4 pt-[12vh] backdrop-blur-sm"
          onClick={() => onOpenChange(false)}
        >
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.22, ease: [0.32, 0.72, 0.24, 1] }}
            onClick={(event) => event.stopPropagation()}
            className="w-full max-w-2xl overflow-hidden rounded-lg border border-edge bg-raised shadow-2xl"
          >
            {/* shouldFilter is off because the server already decided what
                matches. cmdk's own fuzzy filter would re-rank the results by
                how their labels score against the query and hide a post whose
                match is in its body rather than its first line. */}
            <Command label="Search the studio" loop shouldFilter={false}>
              <div className="flex items-center gap-2.5 border-b border-edge px-4">
                <Search className="size-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
                <Command.Input
                  autoFocus
                  value={query}
                  onValueChange={setQuery}
                  placeholder="Search posts, leads, the Swipe File and help"
                  className="w-full bg-transparent py-3.5 text-[14px] text-ink-primary outline-none placeholder:text-ink-muted"
                />
                {searching && (
                  <Loader2 className="size-4 shrink-0 animate-spin text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
                )}
              </div>

              <Command.List className="max-h-[58vh] overflow-y-auto p-2">
                {nothing && (
                  <p className="px-3 py-8 text-center text-[13px] text-ink-muted">
                    Nothing in your posts, leads, Swipe File or help matches that.
                  </p>
                )}

                {error && (
                  <p role="alert" className="px-3 py-6 text-center text-[13px] text-signal-orange-text">
                    The search could not run: {error}
                  </p>
                )}

                {shownActions.length > 0 && (
                  <Group heading={terms.length ? "Actions" : "Go to"}>
                    {shownActions.map((action) => (
                      <Row
                        key={action.id}
                        value={`action:${action.id}`}
                        icon={action.icon}
                        onSelect={() => run(action.run)}
                        trailing={action.hint}
                      >
                        {action.label}
                      </Row>
                    ))}
                  </Group>
                )}

                {response &&
                  GROUPS.map(({ key, heading, icon }) => {
                    const items = response.groups[key];
                    const failed = failedGroups.includes(key);
                    if (!items.length && !failed) return null;
                    return (
                      <Group key={key} heading={heading}>
                        {failed && (
                          <p className="px-3 py-2 text-[12px] text-signal-orange-text">
                            {heading} could not be searched.
                          </p>
                        )}
                        {items.map((result) => (
                          <ResultRow
                            key={`${result.kind}:${result.id}:${result.title}`}
                            result={result}
                            icon={icon}
                            terms={response.terms}
                            onSelect={() => run(() => onOpenResult(result))}
                          />
                        ))}
                      </Group>
                    );
                  })}
              </Command.List>

              <div className="flex items-center justify-between gap-3 border-t border-edge px-4 py-2">
                <span className="studio-meta text-[10px] text-ink-muted">
                  SEARCHES THIS MACHINE ONLY
                </span>
                <span className="studio-meta flex items-center gap-3 text-[10px] text-ink-muted">
                  <span className="flex items-center gap-1">
                    <CornerDownLeft className="size-3" strokeWidth={1.75} aria-hidden="true" />
                    OPEN
                  </span>
                  <span>ESC CLOSE</span>
                </span>
              </div>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Group({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <Command.Group
      heading={heading}
      className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.08em] [&_[cmdk-group-heading]]:text-ink-muted"
    >
      {children}
    </Command.Group>
  );
}

function Row({
  value,
  icon: Icon,
  onSelect,
  trailing,
  children,
}: {
  value: string;
  icon: LucideIcon;
  onSelect: () => void;
  trailing?: string;
  children: ReactNode;
}) {
  return (
    <Command.Item
      value={value}
      onSelect={onSelect}
      className="flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-[13px] text-ink-secondary data-[selected=true]:bg-soft data-[selected=true]:text-ink-primary"
    >
      <Icon className="size-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {trailing && <span className="shrink-0 truncate text-[11px] text-ink-muted">{trailing}</span>}
    </Command.Item>
  );
}

function Highlighted({ text, terms }: { text: string; terms: string[] }) {
  return (
    <>
      {highlightRuns(text, terms).map((run, index) =>
        run.matched ? (
          <mark key={index} className="rounded-sm bg-signal-orange-subtle px-0.5 text-ink-primary">
            {run.text}
          </mark>
        ) : (
          <span key={index}>{run.text}</span>
        ),
      )}
    </>
  );
}

function ResultRow({
  result,
  icon: Icon,
  terms,
  onSelect,
}: {
  result: SearchResult;
  icon: LucideIcon;
  terms: string[];
  onSelect: () => void;
}) {
  return (
    <Command.Item
      value={`${result.kind}:${result.id}:${result.title}`}
      onSelect={onSelect}
      className="group flex cursor-pointer items-start gap-3 rounded-md px-3 py-2.5 data-[selected=true]:bg-soft"
    >
      <Icon className="mt-0.5 size-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline gap-2">
          <span className="min-w-0 truncate text-[13px] font-medium text-ink-primary">
            <Highlighted text={result.title} terms={terms} />
          </span>
          {result.meta && (
            <span
              className={cn(
                "studio-meta shrink-0 text-[10px]",
                result.retired ? "text-signal-orange-text" : "text-ink-muted",
              )}
            >
              {result.retired ? "RETIRED" : result.meta}
            </span>
          )}
        </span>
        {result.kind === "help" && result.document_title && (
          <span className="studio-meta mt-0.5 block truncate text-[10px] text-ink-muted">{result.document_title}</span>
        )}
        {result.snippet && (
          <span className="mt-0.5 line-clamp-2 block text-[12px] leading-snug text-ink-secondary">
            {result.kind === "help" ? (
              // A help snippet is a window onto markdown with FTS5 markers in
              // it, so it goes through the same reader the Docs results use.
              readableSnippet(result.snippet).map((run, index) =>
                run.matched ? (
                  <mark key={index} className="rounded-sm bg-signal-orange-subtle px-0.5 text-ink-primary">
                    <InlineText spans={run.spans} />
                  </mark>
                ) : (
                  <InlineText key={index} spans={run.spans} />
                ),
              )
            ) : (
              <Highlighted text={result.snippet} terms={terms} />
            )}
          </span>
        )}
      </span>
      <span className="mt-0.5 flex shrink-0 items-center gap-1 text-[11px] text-ink-muted opacity-0 transition-opacity group-data-[selected=true]:opacity-100">
        {OPENS[result.opens]}
        <ArrowRight className="size-3" strokeWidth={1.75} aria-hidden="true" />
      </span>
    </Command.Item>
  );
}
