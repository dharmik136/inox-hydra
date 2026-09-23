import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { fetchDocModule, fetchDocModules, searchDocs, type DocHit, type DocModule } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * The offline playbook (blueprint build order phase 4).
 *
 * Search runs against the SQLite FTS5 index the product builds at start up, so
 * it answers without a network and without a model. The results are ranked by
 * the index rather than re-sorted here.
 */
export function DocsSurface() {
  const [modules, setModules] = useState<DocModule[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<DocHit[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [doc, setDoc] = useState<{ title: string; content: string } | null>(null);

  useEffect(() => {
    let live = true;
    fetchDocModules()
      .then((rows) => {
        if (!live) return;
        setModules(rows);
        setOpenId((current) => current ?? rows[0]?.id ?? null);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  // Search after the typing settles. Each keystroke is a query against the
  // index, and the index is fast enough that the delay is about intent rather
  // than cost.
  useEffect(() => {
    const term = query.trim();
    if (!term) {
      setHits(null);
      return;
    }
    let live = true;
    const timer = window.setTimeout(() => {
      searchDocs(term)
        .then((rows) => live && setHits(rows))
        .catch(() => live && setHits([]));
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
    fetchDocModule(openId)
      .then((result) => live && setDoc(result))
      .catch(() => live && setDoc({ title: openId, content: "" }));
    return () => {
      live = false;
    };
  }, [openId]);

  const grouped = useMemo(() => {
    const out = new Map<string, DocModule[]>();
    for (const module of modules ?? []) {
      const list = out.get(module.category) ?? [];
      list.push(module);
      out.set(module.category, list);
    }
    return [...out.entries()];
  }, [modules]);

  if (failed) return <Centered>DOCUMENTATION UNAVAILABLE</Centered>;
  if (!modules) return <Centered>LOADING DOCUMENTATION</Centered>;

  return (
    <div className="flex h-full min-h-0">
      <section aria-label="Playbook" className="flex w-[300px] shrink-0 flex-col border-r border-edge">
        <div className="shrink-0 px-4 pt-4 pb-3">
          <div className="relative">
            <Search
              className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-muted"
              strokeWidth={1.75}
              aria-hidden="true"
            />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search the playbook"
              aria-label="Search the playbook"
              className="w-full rounded-md border border-edge bg-ink py-1.5 pr-3 pl-8 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto" tabIndex={0} role="region" aria-label="Playbook contents">
          {hits ? (
            <div className="px-4 pb-4">
              <p className="studio-label mb-2">
                {hits.length} match{hits.length === 1 ? "" : "es"}
              </p>
              {hits.length === 0 ? (
                <p className="studio-meta text-ink-muted">NOTHING MATCHES THAT</p>
              ) : (
                <ul className="flex flex-col gap-3">
                  {hits.map((hit, index) => (
                    <li key={`${hit.filename}-${index}`} className="border-l border-edge pl-3">
                      <p className="studio-meta text-[10px]">{hit.section.toUpperCase()}</p>
                      {/* The snippet is served with the matched terms wrapped
                          in markers by FTS5. It is rendered as text, never as
                          markup, because it is database content. */}
                      <p className="mt-1 text-[12px] leading-snug text-ink-secondary">{hit.snippet}</p>
                      <p className="studio-meta mt-1 text-[10px] text-ink-muted">{hit.filename}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            grouped.map(([category, entries]) => (
              <div key={category} className="px-2 pb-3">
                <p className="studio-label px-2 pt-3 pb-1">{category}</p>
                <ul>
                  {entries.map((module) => (
                    <li key={module.id}>
                      <button
                        type="button"
                        onClick={() => setOpenId(module.id)}
                        aria-current={openId === module.id ? "page" : undefined}
                        className={cn(
                          "w-full rounded-md px-2 py-1.5 text-left transition-colors duration-(--studio-motion-fast)",
                          openId === module.id ? "bg-soft" : "hover:bg-soft/60",
                        )}
                      >
                        <span className="block truncate text-[12px] text-ink-primary">{module.title}</span>
                        <span className="block truncate text-[10px] text-ink-muted">{module.summary}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </div>
      </section>

      <div className="min-w-0 flex-1 overflow-y-auto" tabIndex={0} role="region" aria-label="Document">
        {doc === null ? (
          <Centered>LOADING</Centered>
        ) : (
          <article className="max-w-[80ch] px-8 py-8">
            <h2 className="studio-title">{doc.title}</h2>
            {doc.content ? (
              /* Rendered as preformatted text rather than parsed as markdown.
                 A renderer is a dependency and an injection surface, and the
                 value here is reading the playbook, not typesetting it. */
              <pre className="mt-6 font-editorial text-[13px] leading-relaxed whitespace-pre-wrap text-ink-secondary">
                {doc.content}
              </pre>
            ) : (
              <p className="studio-meta mt-6 text-ink-muted">THIS DOCUMENT IS EMPTY</p>
            )}
          </article>
        )}
      </div>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}
