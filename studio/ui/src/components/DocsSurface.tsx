import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, BookOpen, ChevronRight, FileText, Search, X, type LucideIcon } from "lucide-react";
import {
  fetchDocLibrary,
  fetchDocument,
  searchDocs,
  type DocHit,
  type DocLibraryEntry,
  type DocModule,
} from "@/lib/api";
import { parseMarkdown, parseInline, slugify, type Block, type Outline } from "@/lib/markdown";
import { DocumentView, InlineText, type ResolvedLink } from "@/components/DocumentView";
import { splitSnippet } from "@/lib/snippet";
import { cn } from "@/lib/utils";

/**
 * The offline playbook.
 *
 * Three things were wrong here and all three were structural rather than
 * cosmetic.
 *
 * The reader printed every document as one <pre> block, so 798 table rows, 91
 * fenced blocks, 1,266 bullets and 1,226 bold runs arrived as literal markdown
 * characters. The six row penalty table in module 01 is the content of the
 * algorithmic audit section, not an aside, and it was unreadable.
 *
 * The search could match any of the 38 files the index covers and the product
 * could open 7, so four fifths of every result set pointed at a document with
 * no route. The hits were not even clickable, which was consistent: there was
 * nowhere for them to go.
 *
 * And the heading over each document was its own raw id, because the client
 * read data.title from a response that never had one.
 *
 * So: lib/markdown.ts turns a document into blocks, DocumentView draws them,
 * the backend gives every indexed file an id, and this file is the three
 * columns around that. Searching, reading and moving between cross references
 * are the three things anyone actually does with a playbook, and each has a
 * column: the library and its matches on the left, the document in the middle,
 * its sections on the right.
 */

/** Average adult reading speed. The estimate is labelled as one on screen. */
const WORDS_PER_MINUTE = 200;

/** Below this many sections a contents rail is chrome rather than navigation. */
const MIN_OUTLINE_FOR_RAIL = 3;

interface OpenDocument {
  id: string;
  title: string;
  path: string;
  category: string;
  words: number;
  blocks: Block[];
  outline: Outline[];
}

export function DocsSurface() {
  const [modules, setModules] = useState<DocModule[]>([]);
  const [library, setLibrary] = useState<DocLibraryEntry[]>([]);
  const [failed, setFailed] = useState(false);

  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<DocHit[] | null>(null);
  const [searching, setSearching] = useState(false);

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
   * top. Every anchor landing undid itself. It is a one shot instruction for
   * the next document, not a piece of what is on screen.
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
        setOpenId((current) => current ?? result.modules[0]?.id ?? result.library[0]?.id ?? null);
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
          // The curated title wins when there is one, because it is the name
          // this product uses for the document elsewhere. A file with no
          // curated entry falls back to its own first heading.
          title: result.title,
          path: result.path,
          category: result.category,
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
   * scroll to, or the reader starts at the top. The reader is a single
   * scrolling box, so without the reset the next document opens at the
   * previous one's offset, somewhere in its middle.
   */
  useEffect(() => {
    if (!doc) return;
    const anchor = pendingAnchor.current;
    pendingAnchor.current = null;
    if (anchor) jumpTo(anchor);
    else readerRef.current?.scrollTo({ top: 0 });
  }, [doc, jumpTo]);

  /** Which section is being read, for the contents rail. */
  useEffect(() => {
    if (!doc || doc.outline.length < MIN_OUTLINE_FOR_RAIL) return;
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
  }, [doc]);

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

  const openDocument = useCallback(
    (id: string, anchor: string | null) => {
      if (id === openId) {
        if (anchor) jumpTo(anchor);
        return;
      }
      if (doc) setCameFrom({ id: doc.id, title: doc.title });
      pendingAnchor.current = anchor;
      setOpenId(id);
    },
    [doc, openId, jumpTo],
  );

  /** Opened from the library or a search result, which is not a cross reference. */
  const selectDocument = useCallback((id: string, anchor: string | null = null) => {
    setCameFrom(null);
    pendingAnchor.current = anchor;
    setOpenId(id);
  }, []);

  const titleMatches = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return [];
    return library.filter(
      (entry) => entry.title.toLowerCase().includes(term) || entry.path.toLowerCase().includes(term),
    );
  }, [library, query]);

  if (failed) return <Centered>THE DOCUMENTATION LIBRARY COULD NOT BE READ</Centered>;
  if (!library.length && !modules.length) return <Centered>OPENING THE LIBRARY</Centered>;

  return (
    <div className="flex h-full min-h-0">
      <LibraryRail
        modules={modules}
        library={library}
        openId={openId}
        query={query}
        onQuery={setQuery}
        hits={hits}
        searching={searching}
        titleMatches={titleMatches}
        onSelect={selectDocument}
      />

      <div ref={readerRef} className="min-w-0 flex-1 overflow-y-auto" tabIndex={0} role="region" aria-label="Document">
        {readFailed ? (
          <Centered>{readFailed.toUpperCase()}</Centered>
        ) : !doc ? (
          <Centered>READING</Centered>
        ) : (
          <article className="px-8 pt-6 pb-24">
            <div className="max-w-[92ch]">
              {cameFrom && (
                <button
                  type="button"
                  onClick={() => selectDocument(cameFrom.id)}
                  className="studio-meta mb-4 flex items-center gap-1.5 text-ink-muted transition-colors duration-(--studio-motion-fast) hover:text-ink-primary"
                >
                  <ArrowLeft className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
                  BACK TO {cameFrom.title.toUpperCase()}
                </button>
              )}

              <DocumentMeta path={doc.path} category={doc.category} words={doc.words} />

              {/* A document with no level one heading of its own would open
                  with no name at all, so the curated title stands in. When it
                  has one, the heading is the title and this is not drawn. */}
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
        )}
      </div>

      {doc && doc.outline.length >= MIN_OUTLINE_FOR_RAIL && (
        <ContentsRail outline={doc.outline} active={activeSlug} onJump={jumpTo} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Left column: the library, and what a search found in it
// ---------------------------------------------------------------------------

interface LibraryRailProps {
  modules: DocModule[];
  library: DocLibraryEntry[];
  openId: string | null;
  query: string;
  onQuery: (value: string) => void;
  hits: DocHit[] | null;
  searching: boolean;
  titleMatches: DocLibraryEntry[];
  onSelect: (id: string, anchor?: string | null) => void;
}

function LibraryRail({
  modules,
  library,
  openId,
  query,
  onQuery,
  hits,
  searching,
  titleMatches,
  onSelect,
}: LibraryRailProps) {
  // The curated seven are listed on their own. Everything else is grouped by
  // the folder it lives in, which is the only grouping these files actually
  // carry; inventing a taxonomy for the other 31 would be inventing one.
  const referenceGroups = useMemo(() => {
    const groups = new Map<string, DocLibraryEntry[]>();
    for (const entry of library) {
      if (entry.module_id) continue;
      const list = groups.get(entry.category) ?? [];
      list.push(entry);
      groups.set(entry.category, list);
    }
    return [...groups.entries()];
  }, [library]);

  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const toggle = (name: string) => setCollapsed((state) => ({ ...state, [name]: !state[name] }));

  return (
    <section aria-label="Playbook library" className="flex w-[304px] shrink-0 flex-col border-r border-edge">
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
        {query.trim() ? (
          <SearchResults
            hits={hits}
            searching={searching}
            titleMatches={titleMatches}
            openId={openId}
            onSelect={onSelect}
          />
        ) : (
          <>
            <Group
              name="Module manuals"
              icon={BookOpen}
              count={modules.length}
              collapsed={Boolean(collapsed["Module manuals"])}
              onToggle={toggle}
            >
              {modules.map((module) => (
                <Row
                  key={module.id}
                  active={openId === module.id}
                  onClick={() => onSelect(module.id)}
                  title={module.summary}
                >
                  <span className="flex items-baseline gap-2">
                    <span className="studio-meta w-[3.2em] shrink-0 text-[10px] text-ink-muted">
                      {module.number.toUpperCase()}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12px] text-ink-primary">{module.title}</span>
                      <span className="studio-label block truncate text-[9px]">{module.category}</span>
                    </span>
                  </span>
                </Row>
              ))}
            </Group>

            {referenceGroups.map(([name, entries]) => (
              <Group
                key={name}
                name={name}
                icon={FileText}
                count={entries.length}
                collapsed={collapsed[name] ?? name !== "Reference"}
                onToggle={toggle}
              >
                {entries.map((entry) => (
                  <Row key={entry.id} active={openId === entry.id} onClick={() => onSelect(entry.id)} title={entry.path}>
                    <span className="block truncate text-[12px] text-ink-primary">{entry.title}</span>
                    <span className="studio-meta block truncate text-[10px] text-ink-muted">
                      {entry.words.toLocaleString()} words
                    </span>
                  </Row>
                ))}
              </Group>
            ))}
          </>
        )}
      </div>
    </section>
  );
}

function Group({
  name,
  icon: Icon,
  count,
  collapsed,
  onToggle,
  children,
}: {
  name: string;
  icon: LucideIcon;
  count: number;
  collapsed: boolean;
  onToggle: (name: string) => void;
  children: ReactNode;
}) {
  return (
    <div className="px-2 pt-3">
      <button
        type="button"
        onClick={() => onToggle(name)}
        aria-expanded={!collapsed}
        className="flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left transition-colors duration-(--studio-motion-fast) hover:bg-soft/60"
      >
        <ChevronRight
          className={cn(
            "size-3 shrink-0 text-ink-muted transition-transform duration-(--studio-motion-fast)",
            collapsed ? "" : "rotate-90",
          )}
          strokeWidth={2}
          aria-hidden="true"
        />
        <Icon className="size-3 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
        <span className="studio-label flex-1 truncate">{name}</span>
        <span className="studio-meta text-[10px] text-ink-muted">{count}</span>
      </button>
      {!collapsed && <ul className="mt-0.5">{children}</ul>}
    </div>
  );
}

function Row({
  active,
  onClick,
  title,
  children,
}: {
  active: boolean;
  onClick: () => void;
  title?: string;
  children: ReactNode;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        title={title}
        aria-current={active ? "page" : undefined}
        className={cn(
          "w-full rounded-md px-2 py-1.5 text-left transition-colors duration-(--studio-motion-fast)",
          active ? "bg-soft" : "hover:bg-soft/60",
        )}
      >
        {children}
      </button>
    </li>
  );
}

/**
 * What a search found, in two kinds.
 *
 * A title match and a section match answer different questions ("which
 * document is this" against "where is this mentioned") and the index only
 * answers the second, so the first is filtered here. Both are separated and
 * labelled rather than merged into one ranked list, because a document whose
 * name matches is not competing with a passage that mentions the term.
 *
 * Every hit is a destination now. A section's anchor is its heading run
 * through the same slug function the parser uses, which is why clicking a
 * result lands on the passage rather than at the top of the file.
 */
function SearchResults({
  hits,
  searching,
  titleMatches,
  openId,
  onSelect,
}: {
  hits: DocHit[] | null;
  searching: boolean;
  titleMatches: DocLibraryEntry[];
  openId: string | null;
  onSelect: (id: string, anchor?: string | null) => void;
}) {
  if (hits === null && searching) {
    return <p className="studio-meta px-4 pt-3 text-ink-muted">SEARCHING</p>;
  }

  const sections = hits ?? [];
  if (!titleMatches.length && !sections.length) {
    return <p className="studio-meta px-4 pt-3 text-ink-muted">NOTHING MATCHES THAT</p>;
  }

  return (
    <div className="px-2 pt-3">
      {titleMatches.length > 0 && (
        <>
          <p className="studio-label px-2 pb-1">
            {titleMatches.length} document{titleMatches.length === 1 ? "" : "s"} by name
          </p>
          <ul className="mb-3">
            {titleMatches.map((entry) => (
              <Row key={entry.id} active={openId === entry.id} onClick={() => onSelect(entry.id)} title={entry.path}>
                <span className="block truncate text-[12px] text-ink-primary">{entry.title}</span>
                {entry.excerpt && (
                  <span className="mt-0.5 line-clamp-2 block text-[11px] leading-snug text-ink-secondary">
                    <InlineText spans={parseInline(entry.excerpt)} />
                  </span>
                )}
                <span className="studio-meta mt-0.5 block truncate text-[10px] text-ink-muted">{entry.path}</span>
              </Row>
            ))}
          </ul>
        </>
      )}

      <p className="studio-label px-2 pb-1">
        {sections.length} section{sections.length === 1 ? "" : "s"} by content
      </p>
      {sections.length === 0 ? (
        <p className="studio-meta px-2 text-ink-muted">NO PASSAGE MENTIONS IT</p>
      ) : (
        <ul className="flex flex-col gap-0.5">
          {sections.map((hit, index) => (
            <li key={`${hit.filename}-${index}`}>
              <button
                type="button"
                onClick={() => onSelect(hit.document_id, slugify(hit.section))}
                className="w-full rounded-md border-l border-edge py-1 pr-2 pl-2.5 text-left transition-colors duration-(--studio-motion-fast) hover:border-l-signal-orange hover:bg-soft/60"
              >
                <span className="studio-meta block truncate text-[10px] text-ink-secondary">
                  {hit.section.toUpperCase()}
                </span>
                {/* FTS5 wraps the matched terms in markers. They are parsed
                    into runs rather than handed to the HTML parser, because
                    the snippet is document content and a playbook file may
                    contain markup of its own. */}
                <span className="mt-0.5 block text-[12px] leading-snug text-ink-secondary">
                  {splitSnippet(hit.snippet).map((run, runIndex) =>
                    run.matched ? (
                      <mark key={runIndex} className="rounded-sm bg-signal-orange-subtle px-0.5 text-ink-primary">
                        {run.text}
                      </mark>
                    ) : (
                      <span key={runIndex}>{run.text}</span>
                    ),
                  )}
                </span>
                <span className="studio-meta mt-0.5 block truncate text-[10px] text-ink-muted">{hit.filename}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
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
 * The reading time is an estimate and says so, on the same 200 words per minute
 * the composer's dwell figure uses. The path is shown because these documents
 * refer to each other by filename and a reader following one needs to know
 * which file they are in.
 */
function DocumentMeta({ path, category, words }: { path: string; category: string; words: number }) {
  const minutes = Math.max(1, Math.round(words / WORDS_PER_MINUTE));
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      {category && <span className="studio-label">{category}</span>}
      {path && <span className="studio-meta text-[10px] text-ink-muted">{path}</span>}
      {words > 0 && (
        <span className="studio-meta text-[10px] text-ink-muted">
          {words.toLocaleString()} WORDS, EST {minutes} MIN
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
 * 43 of the 51 links point at another markdown file in this corpus, and until
 * the whole library became openable none of them could have worked even if the
 * reader had rendered them. One leaves the machine. An href that resolves to
 * nothing is reported as missing rather than rendered as a control that does
 * nothing when pressed.
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
