import { ArrowLeft, ArrowRight, BookOpen, Search } from "lucide-react";
import type { DocHit, DocLibraryEntry, DocSection } from "@/lib/api";
import { InlineText } from "@/components/DocumentView";
import { readableInline, readableSnippet } from "@/lib/snippet";
import { cn } from "@/lib/utils";

/**
 * The way in, before a document is open.
 *
 * The reader used to open straight onto module 01, and the only route to
 * anything else was a sidebar grouped by the folder each file sits in:
 * "Reference", "Prudent Handoff", "Builder Feedback". Those are facts about
 * the filesystem. Somebody asking what leaves this machine, or how to connect
 * a model, has no reason to guess that the answer is filed under a directory
 * named after a handoff process.
 *
 * So the surface opens on the help itself: seven sections named for what a
 * reader came to do, each with the count and the length of what is actually
 * inside it, and the first steps pulled out on top. Where the sections come
 * from is a written table in docs_engine.py rather than keyword matching on
 * titles, so a document is filed by a decision somebody made and a new one
 * that nobody has filed says exactly that instead of landing somewhere wrong.
 */

/** Same reading speed the composer's dwell figure uses. Labelled as an estimate. */
const WORDS_PER_MINUTE = 200;

function minutes(words: number): number {
  return Math.max(1, Math.round(words / WORDS_PER_MINUTE));
}

export interface HelpHomeProps {
  sections: DocSection[];
  library: Map<string, DocLibraryEntry>;
  query: string;
  onQuery: (value: string) => void;
  onOpenSection: (id: string) => void;
  onOpenDocument: (id: string) => void;
}

export function HelpHome({ sections, library, query, onQuery, onOpenSection, onOpenDocument }: HelpHomeProps) {
  // "Start here" is the section the table puts first, not a hand picked list
  // kept somewhere else that could disagree with it.
  const [first, ...rest] = sections;
  const firstDocuments = (first?.document_ids ?? [])
    .map((id) => library.get(id))
    .filter((entry): entry is DocLibraryEntry => entry !== undefined);

  const total = sections.reduce((sum, section) => sum + section.count, 0);

  return (
    <div className="px-8 pt-10 pb-24">
      <div className="max-w-[78ch]">
        <p className="studio-label">Documentation</p>
        <h1 className="studio-title mt-2 max-w-[22ch] text-balance">What do you need to know?</h1>
        <p className="mt-3 max-w-[62ch] text-[14px] leading-relaxed text-ink-secondary">
          {total} documents, searched offline against an index this machine builds itself. Nothing here
          is fetched and nothing you type is sent anywhere.
        </p>

        <div className="relative mt-6 max-w-[52ch]">
          <Search
            className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-ink-muted"
            strokeWidth={1.75}
            aria-hidden="true"
          />
          <input
            value={query}
            onChange={(event) => onQuery(event.target.value)}
            placeholder="Search every document"
            aria-label="Search the documentation"
            className="w-full rounded-lg border border-edge bg-ink py-2.5 pr-4 pl-10 text-[14px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
          />
        </div>

        {first && firstDocuments.length > 0 && (
          <section aria-labelledby="help-first" className="mt-10">
            <h2 id="help-first" className="studio-label">
              {first.title}
            </h2>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              {firstDocuments.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  onClick={() => onOpenDocument(entry.id)}
                  className="group rounded-md border border-edge bg-raised p-3 text-left transition-colors duration-(--studio-motion-fast) hover:border-edge-strong"
                >
                  <span className="flex items-start gap-2">
                    <BookOpen
                      className="mt-0.5 size-3.5 shrink-0 text-ink-muted transition-colors group-hover:text-signal-orange"
                      strokeWidth={1.75}
                      aria-hidden="true"
                    />
                    <span className="min-w-0">
                      <span className="block text-[13px] leading-snug font-medium text-ink-primary">
                        <InlineText spans={readableInline(entry.title)} />
                      </span>
                      {/* A title is the document's own first heading and one of
                          these is simply "Documentation", which says nothing
                          beside "Getting Started" and "First Run". Renaming it
                          would be the studio deciding what the file is called;
                          its own opening line says what it is without that. */}
                      {entry.excerpt && (
                        <span className="mt-1 line-clamp-2 block text-[11px] leading-snug text-ink-secondary">
                          <InlineText spans={readableInline(entry.excerpt)} />
                        </span>
                      )}
                      <span className="studio-meta mt-1.5 block text-[10px] text-ink-muted">
                        EST {minutes(entry.words)} MIN
                      </span>
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}

        <section aria-labelledby="help-topics" className="mt-10">
          <h2 id="help-topics" className="studio-label">
            Browse by topic
          </h2>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            {rest.map((section) => (
              <button
                key={section.id}
                type="button"
                onClick={() => onOpenSection(section.id)}
                className="group rounded-md border border-edge bg-raised p-4 text-left transition-colors duration-(--studio-motion-fast) hover:border-edge-strong"
              >
                <span className="flex items-baseline justify-between gap-3">
                  <span className="text-[14px] font-medium text-ink-primary">{section.title}</span>
                  <ArrowRight
                    className="size-3.5 shrink-0 translate-x-0 text-ink-muted transition-transform duration-(--studio-motion-fast) group-hover:translate-x-0.5 group-hover:text-signal-orange"
                    strokeWidth={1.75}
                    aria-hidden="true"
                  />
                </span>
                <span className="mt-1.5 block text-[13px] leading-relaxed text-ink-secondary">
                  {section.blurb}
                </span>
                <span className="studio-meta mt-2.5 block text-[10px] text-ink-muted">
                  {section.count} {section.count === 1 ? "DOCUMENT" : "DOCUMENTS"}, EST{" "}
                  {minutes(section.words)} MIN
                </span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

export interface SectionViewProps {
  section: DocSection;
  library: Map<string, DocLibraryEntry>;
  onOpenDocument: (id: string) => void;
  onBack: () => void;
}

/** One topic, and everything filed under it. */
export function SectionView({ section, library, onOpenDocument, onBack }: SectionViewProps) {
  const documents = section.document_ids
    .map((id) => library.get(id))
    .filter((entry): entry is DocLibraryEntry => entry !== undefined);

  return (
    <div className="px-8 pt-6 pb-24">
      <div className="max-w-[78ch]">
        <button
          type="button"
          onClick={onBack}
          className="studio-meta flex items-center gap-1.5 text-ink-muted transition-colors duration-(--studio-motion-fast) hover:text-ink-primary"
        >
          <ArrowLeft className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          ALL TOPICS
        </button>

        <h1 className="studio-title mt-4 max-w-[24ch] text-balance">{section.title}</h1>
        <p className="mt-3 max-w-[62ch] text-[14px] leading-relaxed text-ink-secondary">{section.blurb}</p>

        <ul className="mt-7 flex flex-col">
          {documents.map((entry) => (
            <li key={entry.id}>
              <button
                type="button"
                onClick={() => onOpenDocument(entry.id)}
                className="group w-full border-t border-edge py-3.5 text-left transition-colors duration-(--studio-motion-fast) last:border-b hover:bg-soft/50"
              >
                <span className="flex items-baseline justify-between gap-4">
                  <span className="text-[14px] font-medium text-ink-primary group-hover:text-signal-orange-text">
                    <InlineText spans={readableInline(entry.title)} />
                  </span>
                  <span className="studio-meta shrink-0 text-[10px] text-ink-muted">
                    EST {minutes(entry.words)} MIN
                  </span>
                </span>
                {entry.excerpt && (
                  <span className="mt-1 line-clamp-2 block max-w-[68ch] text-[13px] leading-relaxed text-ink-secondary">
                    <InlineText spans={readableInline(entry.excerpt)} />
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export interface ResultsViewProps {
  query: string;
  searching: boolean;
  hits: DocHit[] | null;
  byName: DocLibraryEntry[];
  onOpenDocument: (id: string, anchor: string | null) => void;
  slugFor: (section: string) => string;
}

/**
 * What a search found, at reading width.
 *
 * Results used to live only in a 300px rail, where a snippet wrapped to five
 * lines and the filename underneath was the only thing saying where the answer
 * was. Here each result names its document and the part of the help it came
 * from, which is the question someone searching for help is actually asking.
 *
 * A name match and a passage match answer different questions, so they are
 * separated rather than merged into one ranked list: the index only answers
 * the second, and a document whose title matches is not competing with a
 * paragraph that mentions the term.
 */
export function ResultsView({ query, searching, hits, byName, onOpenDocument, slugFor }: ResultsViewProps) {
  const sections = hits ?? [];
  const nothing = !searching && hits !== null && sections.length === 0 && byName.length === 0;

  return (
    <div className="px-8 pt-6 pb-24">
      <div className="max-w-[78ch]">
        <p className="studio-label">Search</p>
        <h1 className="mt-2 font-display text-[26px] leading-tight font-semibold tracking-[-0.01em] text-ink-primary">
          {searching && hits === null
            ? "Searching"
            : nothing
              ? "Nothing matches that"
              : `${sections.length + byName.length} ${sections.length + byName.length === 1 ? "result" : "results"} for ${query}`}
        </h1>

        {nothing && (
          <p className="mt-3 max-w-[58ch] text-[14px] leading-relaxed text-ink-secondary">
            The index covers every word of all the documents, so a term that appears nowhere here
            appears nowhere in the documentation.
          </p>
        )}

        {byName.length > 0 && (
          <section aria-labelledby="results-name" className="mt-8">
            <h2 id="results-name" className="studio-label">
              {byName.length} {byName.length === 1 ? "document" : "documents"} by name
            </h2>
            <ul className="mt-2 flex flex-col">
              {byName.map((entry) => (
                <li key={entry.id}>
                  <button
                    type="button"
                    onClick={() => onOpenDocument(entry.id, null)}
                    className="group w-full border-t border-edge py-3 text-left transition-colors duration-(--studio-motion-fast) last:border-b hover:bg-soft/50"
                  >
                    <span className="flex items-baseline justify-between gap-4">
                      <span className="text-[14px] font-medium text-ink-primary group-hover:text-signal-orange-text">
                        <InlineText spans={readableInline(entry.title)} />
                      </span>
                      <span className="studio-meta shrink-0 text-[10px] text-ink-muted">
                        EST {minutes(entry.words)} MIN
                      </span>
                    </span>
                    {entry.excerpt && (
                      <span className="mt-1 line-clamp-2 block text-[13px] leading-relaxed text-ink-secondary">
                        <InlineText spans={readableInline(entry.excerpt)} />
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {sections.length > 0 && (
          <section aria-labelledby="results-passage" className="mt-8">
            <h2 id="results-passage" className="studio-label">
              {sections.length} {sections.length === 1 ? "passage" : "passages"}
            </h2>
            <ul className="mt-2 flex flex-col">
              {sections.map((hit, index) => (
                <li key={`${hit.filename}-${index}`}>
                  <button
                    type="button"
                    onClick={() => onOpenDocument(hit.document_id, slugFor(hit.section))}
                    className={cn(
                      "group w-full border-t border-edge py-3 text-left transition-colors",
                      "duration-(--studio-motion-fast) last:border-b hover:bg-soft/50",
                    )}
                  >
                    <span className="flex flex-wrap items-baseline gap-x-2">
                      <span className="studio-label text-ink-secondary">{hit.help_section}</span>
                      <span className="studio-meta text-[10px] text-ink-muted"><InlineText spans={readableInline(hit.document_title)} /></span>
                    </span>
                    <span className="mt-1 block text-[14px] leading-snug font-medium text-ink-primary group-hover:text-signal-orange-text">
                      <InlineText spans={readableInline(hit.section)} />
                    </span>
                    {/* FTS5 wraps the matched terms in markers. They are parsed
                        into runs rather than handed to the HTML parser, because
                        a snippet is document content and a playbook file may
                        contain markup of its own. */}
                    <span className="mt-1 block max-w-[70ch] text-[13px] leading-relaxed text-ink-secondary">
                      {readableSnippet(hit.snippet).map((run, runIndex) =>
                        run.matched ? (
                          <mark
                            key={runIndex}
                            className="rounded-sm bg-signal-orange-subtle px-0.5 text-ink-primary"
                          >
                            <InlineText spans={run.spans} />
                          </mark>
                        ) : (
                          <InlineText key={runIndex} spans={run.spans} />
                        ),
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
