import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ChevronRight, LifeBuoy, Search, X } from "lucide-react";
import {
  fetchDocLibrary,
  fetchDocument,
  searchDocs,
  type DocHit,
  type DocLibraryEntry,
  type DocModule,
  type DocSection,
} from "@/lib/api";
import { parseMarkdown, slugify, type Block, type Outline } from "@/lib/markdown";
import { DocumentView, InlineText, type ResolvedLink } from "@/components/DocumentView";
import { readableInline, readablePlain } from "@/lib/snippet";
import { HelpHome, ResultsView, SectionView } from "@/components/HelpCentre";
import { cn } from "@/lib/utils";

/**
 * The offline playbook.
 *
 * Three things were wrong here to begin with and all three were structural.
 * The reader printed every document as one <pre> block, so 798 table rows and
 * 91 fenced blocks arrived as literal markdown characters. The search could
 * match any of the 38 files the index covers and the product could open 7. And
 * the heading over each document was its own raw id.
 *
 * A fourth was the way in. The surface opened straight onto module 01, and the
 * only route to anything else was a sidebar grouped by the folder each file
 * sits in: "Reference", "Prudent Handoff", "Builder Feedback". Those are facts
 * about the filesystem, not answers to a question. Somebody asking what leaves
 * this machine has no reason to look under a directory named after a handoff
 * process.
 *
 * So it opens on the help instead: seven sections named for what a reader came
 * to do, each with the count and length of what is inside. Four things happen
 * in the reading column rather than one, because they are four different
 * moments: choosing a topic, seeing what a topic holds, seeing what a search
 * found, and reading. Search results in particular moved out of the 300px rail,
 * where a snippet wrapped to five lines and a filename was the only clue about
 * where the answer lived.
 */

/** Average adult reading speed. The estimate is labelled as one on screen. */
const WORDS_PER_MINUTE = 200;

/** Below this many sections a contents rail is chrome rather than navigation. */
const MIN_OUTLINE_FOR_RAIL = 3;

type View = "home" | "section" | "results" | "document";

interface OpenDocument {
  id: string;
  title: string;
  path: string;
  section: string;
  words: number;
  blocks: Block[];
  outline: Outline[];
}

export function DocsSurface() {
  const [modules, setModules] = useState<DocModule[]>([]);
  const [library, setLibrary] = useState<DocLibraryEntry[]>([]);
  const [sections, setSections] = useState<DocSection[]>([]);
  const [failed, setFailed] = useState(false);

  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<DocHit[] | null>(null);
  const [searching, setSearching] = useState(false);

  /**
   * Which of the four things the reading column is doing.
   *
   * Held rather than derived from whether a query is set, because opening a
   * result has to win over the query that produced it. Derived, clicking a
   * result put the document on screen and then the still present query put the
   * results straight back over it.
   */
  const [view, setView] = useState<View>("home");
  const [sectionId, setSectionId] = useState<string | null>(null);

  const [openId, setOpenId] = useState<string | null>(null);
  const [doc, setDoc] = useState<OpenDocument | null>(null);
  const [readFailed, setReadFailed] = useState<string | null>(null);

  /** Where a cross reference was followed from, so it can be followed back. */
  const [cameFrom, setCameFrom] = useState<{ id: string; title: string } | null>(null);
  const [activeSlug, setActiveSlug] = useState<string | null>(null);

  /**
   * A heading to land on once the document it belongs to has rendered.
   *
   * A ref rather than state, and that is the bug this carries: as state, the
   * effect that resets the reader's scroll position watched it, so clearing it
   * after a successful jump re-ran the reset and scrolled straight back to the
   * top. Every anchor landing undid itself.
   */
  const pendingAnchor = useRef<string | null>(null);
  const readerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let live = true;
    fetchDocLibrary()
      .then((result) => {
        if (!live) return;
        setModules(result.modules);
        setLibrary(result.library);
        setSections(result.sections);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  // Search after the typing settles. Each keystroke is a query against the
  // FTS5 index, and the index is fast enough that the delay is about intent
  // rather than cost.
  useEffect(() => {
    const term = query.trim();
    if (!term) {
      setHits(null);
      setSearching(false);
      return;
    }
    let live = true;
    setSearching(true);
    const timer = window.setTimeout(() => {
      searchDocs(term)
        .then((rows) => live && setHits(rows))
        .catch(() => live && setHits([]))
        .finally(() => live && setSearching(false));
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    if (!openId) return;
    let live = true;
    setDoc(null);
    setReadFailed(null);
    setActiveSlug(null);
    fetchDocument(openId)
      .then((result) => {
        if (!live) return;
        const parsed = parseMarkdown(result.content);
        setDoc({
          id: result.id,
          title: result.title,
          path: result.path,
          section: result.section,
          words: result.words,
          blocks: parsed.blocks,
          outline: parsed.outline,
        });
      })
      .catch((error) => {
        if (!live) return;
        setReadFailed(error instanceof Error ? error.message : "The document could not be read.");
      });
    return () => {
      live = false;
    };
  }, [openId]);

  const prefersReducedMotion = () =>
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const jumpTo = useCallback((slug: string) => {
    const heading = document.getElementById(slug);
    if (!heading) return;
    heading.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
    setActiveSlug(slug);
  }, []);

  /**
   * Where a freshly rendered document opens.
   *
   * One effect, because the two answers are exclusive: either a heading was
   * asked for, which needs the blocks in the tree before the element exists to
   * scroll to, or the reader starts at the top.
   */
  useEffect(() => {
    if (!doc) return;
    const anchor = pendingAnchor.current;
    pendingAnchor.current = null;
    if (anchor) jumpTo(anchor);
    else readerRef.current?.scrollTo({ top: 0 });
  }, [doc, jumpTo]);

  /** The reading column starts at the top whenever it changes what it is showing. */
  useEffect(() => {
    if (view !== "document") readerRef.current?.scrollTo({ top: 0 });
  }, [view, sectionId]);

  /** Which section is being read, for the contents rail. */
  useEffect(() => {
    if (view !== "document" || !doc || doc.outline.length < MIN_OUTLINE_FOR_RAIL) return;
    const scroller = readerRef.current;
    if (!scroller) return;

    const headings = doc.outline
      .map((entry) => document.getElementById(entry.slug))
      .filter((node): node is HTMLElement => node !== null);
    if (!headings.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length) setActiveSlug(visible[0].target.id);
      },
      // A band near the top of the reader rather than the whole box, so the
      // marked section is the one being read and not the last one on screen.
      { root: scroller, rootMargin: "0px 0px -72% 0px", threshold: 0 },
    );
    headings.forEach((heading) => observer.observe(heading));
    return () => observer.disconnect();
  }, [doc, view]);

  const byId = useMemo(() => {
    const map = new Map<string, DocLibraryEntry>();
    for (const entry of library) map.set(entry.id, entry);
    return map;
  }, [library]);

  /** Library paths to ids, for resolving a relative link between documents. */
  const byPath = useMemo(() => {
    const map = new Map<string, string>();
    for (const entry of library) map.set(entry.path.toLowerCase(), entry.id);
    return map;
  }, [library]);

  const resolve = useCallback(
    (href: string): ResolvedLink => resolveHref(href, doc?.path ?? "", byPath),
    [doc, byPath],
  );

  /** Opened by following a cross reference inside a document. */
  const openDocument = useCallback(
    (id: string, anchor: string | null) => {
      if (id === openId && view === "document") {
        if (anchor) jumpTo(anchor);
        return;
      }
      if (doc) setCameFrom({ id: doc.id, title: doc.title });
      pendingAnchor.current = anchor;
      setOpenId(id);
      setView("document");
    },
    [doc, openId, view, jumpTo],
  );

  /** Opened from the library, a topic or a result, which is not a cross reference. */
  const selectDocument = useCallback((id: string, anchor: string | null = null) => {
    setCameFrom(null);
    pendingAnchor.current = anchor;
    setOpenId(id);
    setView("document");
  }, []);

  const onQuery = useCallback(
    (value: string) => {
      setQuery(value);
      if (value.trim()) setView("results");
      else setView(openId ? "document" : "home");
    },
    [openId],
  );

  const goHome = useCallback(() => {
    setQuery("");
    setSectionId(null);
    setView("home");
  }, []);

  const openSection = useCallback((id: string) => {
    setQuery("");
    setSectionId(id);
    setView("section");
  }, []);

  const byName = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return [];
    return library.filter(
      (entry) => entry.title.toLowerCase().includes(term) || entry.path.toLowerCase().includes(term),
    );
  }, [library, query]);

  if (failed) return <Centered>THE DOCUMENTATION LIBRARY COULD NOT BE READ</Centered>;
  if (!library.length) return <Centered>OPENING THE LIBRARY</Centered>;

  const currentSection = sections.find((section) => section.id === sectionId) ?? null;

  return (
    <div className="flex h-full min-h-0">
      <LibraryRail
        sections={sections}
        library={byId}
        modules={modules}
        openId={view === "document" ? openId : null}
        openSectionId={view === "section" ? sectionId : null}
        query={query}
        onQuery={onQuery}
        onHome={goHome}
        onOpenSection={openSection}
        onSelect={selectDocument}
      />

      <div
        ref={readerRef}
        className="min-w-0 flex-1 overflow-y-auto"
        tabIndex={0}
        role="region"
        aria-label="Document"
      >
        {view === "results" ? (
          <ResultsView
            query={query.trim()}
            searching={searching}
            hits={hits}
            byName={byName}
            onOpenDocument={selectDocument}
            slugFor={slugify}
          />
        ) : view === "section" && currentSection ? (
          <SectionView
            section={currentSection}
            library={byId}
            onOpenDocument={selectDocument}
            onBack={goHome}
          />
        ) : view === "document" ? (
          readFailed ? (
            <Centered>{readFailed.toUpperCase()}</Centered>
          ) : !doc ? (
            <Centered>READING</Centered>
          ) : (
            <article className="px-8 pt-6 pb-24">
              <div className="max-w-[92ch]">
                <button
                  type="button"
                  onClick={() => (cameFrom ? selectDocument(cameFrom.id) : goHome())}
                  className="studio-meta mb-4 flex items-center gap-1.5 text-ink-muted transition-colors duration-(--studio-motion-fast) hover:text-ink-primary"
                >
                  <ArrowLeft className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                  {cameFrom ? `BACK TO ${readablePlain(cameFrom.title).toUpperCase()}` : "ALL TOPICS"}
                </button>

                <DocumentMeta path={doc.path} section={doc.section} words={doc.words} />

                {/* A document with no level one heading of its own would open
                    with no name at all, so the curated title stands in. */}
                {!doc.blocks.some((block) => block.kind === "heading" && block.level === 1) && (
                  <h1 className="studio-title mt-2 max-w-[30ch] text-balance">{doc.title}</h1>
                )}

                {doc.blocks.length === 0 ? (
                  <p className="studio-meta mt-6 text-ink-muted">THIS DOCUMENT IS EMPTY</p>
                ) : (
                  <DocumentView
                    blocks={doc.blocks}
                    resolve={resolve}
                    onOpenDocument={openDocument}
                    onJumpTo={jumpTo}
                  />
                )}
              </div>
            </article>
          )
        ) : (
          <HelpHome
            sections={sections}
            library={byId}
            query={query}
            onQuery={onQuery}
            onOpenSection={openSection}
            onOpenDocument={selectDocument}
          />
        )}
      </div>

      {view === "document" && doc && doc.outline.length >= MIN_OUTLINE_FOR_RAIL && (
        <ContentsRail outline={doc.outline} active={activeSlug} onJump={jumpTo} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Left column: the help, by topic
// ---------------------------------------------------------------------------

interface LibraryRailProps {
  sections: DocSection[];
  library: Map<string, DocLibraryEntry>;
  modules: DocModule[];
  openId: string | null;
  openSectionId: string | null;
  query: string;
  onQuery: (value: string) => void;
  onHome: () => void;
  onOpenSection: (id: string) => void;
  onSelect: (id: string, anchor?: string | null) => void;
}

function LibraryRail({
  sections,
  library,
  modules,
  openId,
  openSectionId,
  query,
  onQuery,
  onHome,
  onOpenSection,
  onSelect,
}: LibraryRailProps) {
  /** The curated seven carry a number worth showing beside their title. */
  const numberOf = useMemo(() => {
    const map = new Map<string, string>();
    for (const module of modules) map.set(module.id, module.number);
    return map;
  }, [modules]);

  // Every section collapsed but the first, because the whole library open at
  // once is 38 rows and the rail is the thing you scan rather than read.
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const toggle = (id: string) => setExpanded((state) => ({ ...state, [id]: !state[id] }));

  return (
    <section aria-label="Help topics" className="flex w-[304px] shrink-0 flex-col border-r border-edge">
      <div className="shrink-0 px-4 pt-4 pb-3">
        <div className="relative">
          <Search
            className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-muted"
            strokeWidth={1.75}
            aria-hidden="true"
          />
          <input
            value={query}
            onChange={(event) => onQuery(event.target.value)}
            placeholder="Search every document"
            aria-label="Search the playbook"
            className="w-full rounded-md border border-edge bg-ink py-1.5 pr-8 pl-8 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
          />
          {query && (
            <button
              type="button"
              onClick={() => onQuery("")}
              aria-label="Clear the search"
              className="absolute top-1/2 right-2 grid size-4 -translate-y-1/2 place-items-center rounded-sm text-ink-muted transition-colors duration-(--studio-motion-fast) hover:text-ink-primary"
            >
              <X className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pb-6">
        <div className="px-2">
          <button
            type="button"
            onClick={onHome}
            className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left transition-colors duration-(--studio-motion-fast) hover:bg-soft/60"
          >
            <LifeBuoy className="size-3.5 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
            <span className="text-[12px] text-ink-primary">All topics</span>
          </button>
        </div>

        {sections.map((section, index) => {
          const open = expanded[section.id] ?? index === 0;
          const documents = section.document_ids
            .map((id) => library.get(id))
            .filter((entry): entry is DocLibraryEntry => entry !== undefined);

          return (
            <div key={section.id} className="px-2 pt-1">
              <div
                className={cn(
                  "flex items-center rounded-md transition-colors duration-(--studio-motion-fast)",
                  openSectionId === section.id ? "bg-soft" : "",
                )}
              >
                <button
                  type="button"
                  onClick={() => toggle(section.id)}
                  aria-expanded={open}
                  aria-label={`${open ? "Collapse" : "Expand"} ${section.title}`}
                  className="grid size-6 shrink-0 place-items-center rounded-md text-ink-muted transition-colors duration-(--studio-motion-fast) hover:text-ink-primary"
                >
                  <ChevronRight
                    className={cn(
                      "size-3 transition-transform duration-(--studio-motion-fast)",
                      open ? "rotate-90" : "",
                    )}
                    strokeWidth={2}
                    aria-hidden="true"
                  />
                </button>
                <button
                  type="button"
                  onClick={() => onOpenSection(section.id)}
                  className="flex min-w-0 flex-1 items-center gap-2 rounded-md py-1 pr-2 text-left transition-colors duration-(--studio-motion-fast) hover:bg-soft/60"
                >
                  <span className="studio-label flex-1 truncate text-ink-secondary">{section.title}</span>
                  <span className="studio-meta text-[10px] text-ink-muted">{section.count}</span>
                </button>
              </div>

              {open && (
                <ul className="mt-0.5 ml-3 border-l border-edge pl-1">
                  {documents.map((entry) => {
                    const number = entry.module_id ? numberOf.get(entry.module_id) : undefined;
                    return (
                      <li key={entry.id}>
                        <button
                          type="button"
                          onClick={() => onSelect(entry.id)}
                          title={entry.path}
                          aria-current={openId === entry.id ? "page" : undefined}
                          className={cn(
                            "w-full rounded-md px-2 py-1.5 text-left transition-colors duration-(--studio-motion-fast)",
                            openId === entry.id ? "bg-soft" : "hover:bg-soft/60",
                          )}
                        >
                          <span className="flex items-baseline gap-2">
                            {number && (
                              <span className="studio-meta w-[3.2em] shrink-0 text-[10px] text-ink-muted">
                                {number.toUpperCase()}
                              </span>
                            )}
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-[12px] text-ink-primary">
                                <InlineText spans={readableInline(entry.title)} />
                              </span>
                              <span className="studio-meta block truncate text-[10px] text-ink-muted">
                                {entry.words.toLocaleString()} words
                              </span>
                            </span>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Right column: the sections of the document being read
// ---------------------------------------------------------------------------

function ContentsRail({
  outline,
  active,
  onJump,
}: {
  outline: Outline[];
  active: string | null;
  onJump: (slug: string) => void;
}) {
  return (
    <nav
      aria-label="Sections in this document"
      className="hidden w-[228px] shrink-0 overflow-y-auto border-l border-edge px-3 py-6 xl:block"
    >
      <p className="studio-label px-2 pb-2">In this document</p>
      <ul>
        {outline.map((entry) => (
          <li key={entry.slug}>
            <button
              type="button"
              onClick={() => onJump(entry.slug)}
              aria-current={active === entry.slug ? "location" : undefined}
              className={cn(
                "w-full border-l py-1 text-left text-[12px] leading-snug transition-colors duration-(--studio-motion-fast)",
                entry.level === 3 ? "pr-2 pl-5" : "pr-2 pl-3",
                active === entry.slug
                  ? "border-l-signal-orange text-ink-primary"
                  : "border-l-edge text-ink-muted hover:border-l-edge-strong hover:text-ink-secondary",
              )}
            >
              {entry.text}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

// ---------------------------------------------------------------------------
// Pieces
// ---------------------------------------------------------------------------

/**
 * What this document is, above it.
 *
 * The section rather than the folder, because the folder is where the file
 * lives and the section is what the reader is in. The reading time is an
 * estimate and says so, on the same 200 words per minute the composer's dwell
 * figure uses. The path is shown because these documents refer to each other
 * by filename and a reader following one needs to know which file they are in.
 */
function DocumentMeta({ path, section, words }: { path: string; section: string; words: number }) {
  const estimate = Math.max(1, Math.round(words / WORDS_PER_MINUTE));
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      {section && <span className="studio-label">{section}</span>}
      {path && <span className="studio-meta text-[10px] text-ink-muted">{path}</span>}
      {words > 0 && (
        <span className="studio-meta text-[10px] text-ink-muted">
          {words.toLocaleString()} WORDS, EST {estimate} MIN
        </span>
      )}
    </div>
  );
}

function Centered({ children }: { children: ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Link resolution
// ---------------------------------------------------------------------------

const EXTERNAL = /^(https?:|mailto:|tel:)/i;

/**
 * Joins a relative href onto the directory of the document that contains it.
 *
 * Kept here rather than leaned on from the URL class because these are not
 * URLs: they are paths inside a docs directory, and giving them a fake origin
 * to parse would then need the origin stripped back off.
 */
export function resolveRelativePath(fromPath: string, href: string): string {
  const fromDir = fromPath.includes("/") ? fromPath.slice(0, fromPath.lastIndexOf("/")) : "";
  const segments = href.startsWith("/") ? [] : fromDir.split("/").filter(Boolean);
  const out = [...segments];
  for (const part of href.split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") {
      out.pop();
      continue;
    }
    out.push(part);
  }
  return out.join("/");
}

/**
 * The four things a link in these documents turns out to be.
 *
 * 43 of the 51 links point at another markdown file in this same corpus, and
 * until the whole library became openable none of them could have worked even
 * if the reader had rendered them. One leaves the machine. An href that
 * resolves to nothing is reported as missing rather than rendered as a control
 * that does nothing when pressed.
 */
export function resolveHref(href: string, fromPath: string, byPath: Map<string, string>): ResolvedLink {
  const target = (href || "").trim();
  if (!target) return { kind: "missing", href };
  if (target.startsWith("#")) return { kind: "anchor", anchor: target.slice(1).toLowerCase() };
  if (EXTERNAL.test(target)) return { kind: "external", href: target };

  const [rawPath, rawAnchor] = target.split("#");
  const anchor = rawAnchor ? rawAnchor.toLowerCase() : null;

  // A bare anchor after an empty path is a link into the current document.
  if (!rawPath) {
    return anchor ? { kind: "anchor", anchor } : { kind: "missing", href };
  }

  const resolved = resolveRelativePath(fromPath, rawPath);
  const id = byPath.get(resolved.toLowerCase());
  if (id) return { kind: "document", id, anchor };
  return { kind: "missing", href: resolved };
}
