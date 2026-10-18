import { useEffect, useRef, useState } from "react";
import { ExternalLink, FileArchive, Loader2 } from "lucide-react";
import {
  discardArchive,
  fetchArchiveState,
  importArchive,
  markArchiveRequested,
  previewArchive,
  uploadArchive,
  type ArchiveKindTally,
  type ArchivePreview,
  type ArchiveState,
  type FoundArchive,
} from "@/lib/api";

const LOOK_MS = 4000;

/**
 * Setup, LinkedIn's data archive.
 *
 * The creator's own record, handed over by LinkedIn: years of posts, comments
 * and reactions, their roles and their connections, in one file and with no
 * page reading at all. Every step waits for the creator. They ask LinkedIn for
 * it on a page this opens; once they say they have, the studio looks in their
 * Downloads folder for LinkedIn's export and offers it; and nothing is written
 * until they have seen what it holds and kept ticked what they want.
 */
export function ArchiveImport({
  state,
  onOpenPage,
  opening,
  onChanged,
}: {
  state: ArchiveState;
  onOpenPage: (url: string) => void;
  opening: boolean;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [preview, setPreview] = useState<ArchivePreview | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<Record<string, ArchiveKindTally> | null>(null);
  const [found, setFound] = useState<FoundArchive[]>([]);
  const [waiting, setWaiting] = useState(state.waiting);
  const picker = useRef<HTMLInputElement>(null);
  const chooser = useRef<HTMLButtonElement>(null);
  const previewTitle = useRef<HTMLParagraphElement>(null);
  const resultTitle = useRef<HTMLParagraphElement>(null);

  useEffect(() => setWaiting(state.waiting), [state.waiting]);

  // Downloads is looked in only from here, while this step is on screen and
  // waiting for an archive the creator said they asked for.
  useEffect(() => {
    if (!waiting) {
      setFound([]);
      return;
    }
    let live = true;
    const look = () =>
      fetchArchiveState()
        .then((fresh) => {
          if (!live) return;
          setFound(fresh.found);
          setWaiting(fresh.waiting);
        })
        .catch(() => undefined);
    void look();
    const timer = window.setInterval(look, LOOK_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [waiting]);

  // Focus follows the step: to the preview when it opens, to the result after
  // an import, and back to "Choose the file" when either is closed.
  useEffect(() => {
    if (result) resultTitle.current?.focus();
    else if (preview) previewTitle.current?.focus();
  }, [preview, result]);

  function close() {
    if (preview && !result && preview.source.startsWith("upload:")) void discardArchive(preview.source);
    setPreview(null);
    setResult(null);
    window.requestAnimationFrame(() => chooser.current?.focus());
  }

  async function run(key: string, work: () => Promise<void>) {
    setBusy(key);
    setNote(null);
    try {
      await work();
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "That did not work.");
    } finally {
      setBusy(null);
    }
  }

  function show(found: ArchivePreview) {
    setPreview(found);
    setResult(null);
    setTicked(new Set(found.files.filter((f) => f.importable && f.default).map((f) => f.kind)));
    if (!found.recognised) setNote("This file does not look like LinkedIn's data archive.");
  }


  return (
    <div className="flex flex-col gap-3">
      {!preview && (
        <>
          {state.last_import ? (
            <p className="text-[13px] leading-relaxed text-ink-secondary">
              For a newer copy, ask LinkedIn again on the same page. Importing it again adds only
              what is new.
            </p>
          ) : (
            <p className="text-[13px] leading-relaxed text-ink-secondary">
              LinkedIn will give you a copy of everything it holds about your account. On its page,
              choose <span className="text-ink-primary">Download larger data archive</span>, then{" "}
              <span className="text-ink-primary">Request archive</span>. LinkedIn emails you a link,
              usually within minutes for the first part and within a day for all of it. Download
              it, and come back here.
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => onOpenPage(state.download_page)}
              disabled={opening || busy !== null}
              className="flex items-center gap-1.5 rounded-md bg-signal-orange px-3 py-1.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
            >
              {opening ? (
                <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <ExternalLink className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
              )}
              Open LinkedIn&rsquo;s download page
            </button>
            {!waiting && (
              <button
                type="button"
                disabled={busy !== null}
                onClick={() =>
                  void run("requested", async () => {
                    const fresh = await markArchiveRequested();
                    setFound(fresh.found);
                    setWaiting(fresh.waiting);
                    onChanged();
                  })
                }
                className="rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
              >
                I have asked for it
              </button>
            )}
            <button
              ref={chooser}
              type="button"
              disabled={busy !== null}
              onClick={() => picker.current?.click()}
              className="flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
            >
              {busy === "upload" ? (
                <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <FileArchive className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
              )}
              Choose the file
            </button>
            <input
              ref={picker}
              type="file"
              accept=".zip,application/zip"
              tabIndex={-1}
              className="sr-only"
              aria-label="Choose your LinkedIn data archive"
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) void run("upload", async () => show(await uploadArchive(file)));
              }}
            />
          </div>

          {waiting && (
            <div>
              <p className="studio-meta text-[10px] text-ink-muted">
                IN YOUR DOWNLOADS FOLDER{found.length === 0 ? ": NOTHING FROM LINKEDIN YET" : ""}
              </p>
              {found.length > 0 && (
                <ul className="mt-1.5 flex flex-col gap-1.5">
                  {found.map((hit) => (
                    <li key={hit.path} className="flex items-center justify-between gap-3">
                      <span className="min-w-0 truncate text-[13px] text-ink-secondary">
                        {hit.name}
                        <span className="studio-meta ml-2 text-[10px] text-ink-muted">
                          {readable(hit.bytes)} · {localDate(hit.modified)}
                        </span>
                      </span>
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() =>
                          void run(hit.path, async () => show(await previewArchive(`downloads:${hit.path}`)))
                        }
                        className="shrink-0 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                      >
                        {busy === hit.path ? "Reading" : "See what is in it"}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}

      {preview && !result && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void run("import", async () => {
              const done = await importArchive(preview.source, [...ticked]);
              setResult(done.summary);
              onChanged();
            });
          }}
          className="rounded-md border border-edge-strong p-4"
          aria-label="What to import from the archive"
        >
          <p ref={previewTitle} tabIndex={-1} className="text-[13px] font-medium text-ink-primary outline-none">
            {preview.archive.name}
          </p>
          <p className="studio-meta mt-0.5 text-[10px] text-ink-muted">
            {readable(preview.archive.bytes)} · NOTHING IS IMPORTED UNTIL YOU SAY SO
          </p>
          <fieldset className="mt-3 flex flex-col gap-2">
            <legend className="sr-only">Files to import</legend>
            {preview.files.map((file) => (
              <label key={file.kind} className="flex items-start gap-2 text-[13px] text-ink-secondary">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  disabled={!file.importable}
                  checked={ticked.has(file.kind)}
                  onChange={(event) => {
                    const next = new Set(ticked);
                    if (event.target.checked) next.add(file.kind);
                    else next.delete(file.kind);
                    setTicked(next);
                  }}
                />
                <span>
                  <span className="text-ink-primary">{file.label}</span>
                  <span className="studio-meta ml-2 text-[10px] text-ink-muted">
                    {file.rows === null ? "NOT UNDERSTOOD" : `${file.rows} ROW${file.rows === 1 ? "" : "S"}`}
                  </span>
                  {file.note && <span className="mt-0.5 block text-[12px] text-signal-orange-text">{file.note}</span>}
                </span>
              </label>
            ))}
          </fieldset>
          {preview.not_imported.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-[12px] text-ink-muted">
                {preview.not_imported.length} other file{preview.not_imported.length === 1 ? "" : "s"} stay in the archive
              </summary>
              <ul className="mt-1.5 flex flex-col gap-0.5">
                {preview.not_imported.map((other) => (
                  <li key={other.file} className="text-[12px] text-ink-muted">
                    {other.file}: {other.note}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <p className="mt-3 text-[12px] leading-relaxed text-ink-muted">
            Imported posts arrive without reactions or impressions, because the archive does not
            have them; the bridge fills them in when it next reads your posts. Anything the bridge
            already captured is kept as it is.
          </p>
          <div className="mt-3 flex gap-2">
            <button
              type="submit"
              disabled={busy !== null || ticked.size === 0}
              className="flex items-center gap-1.5 rounded-md bg-signal-orange px-3 py-1.5 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
            >
              {busy === "import" && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
              Import what is ticked
            </button>
            <button
              type="button"
              disabled={busy !== null}
              onClick={close}
              className="rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
            >
              Not now
            </button>
          </div>
        </form>
      )}

      {result && (
        <div className="rounded-md border border-edge p-4" role="status">
          <p ref={resultTitle} tabIndex={-1} className="text-[13px] font-medium text-ink-primary outline-none">
            Imported from {preview?.archive.name}
          </p>
          <ul className="mt-2 flex flex-col gap-0.5">
            {Object.entries(result).map(([kind, tally]) => (
              <li key={kind} className="text-[12px] text-ink-secondary">
                {labelFor(preview, kind)}: {tallyLine(tally)}
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={close}
            className="mt-3 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
          >
            Done
          </button>
        </div>
      )}

      {note && (
        <p role="status" className="text-[12px] text-signal-orange-text">
          {note}
        </p>
      )}
    </div>
  );
}

export function archiveStatus(state: ArchiveState): string {
  if (state.last_import) {
    const posts = state.last_import.summary.posts;
    const added = posts && "added" in posts ? `, ${posts.added} new post${posts.added === 1 ? "" : "s"}` : "";
    return `Imported ${localDate(state.last_import.imported_at)} from ${state.last_import.archive_name}${added}`;
  }
  if (state.requested_at) return `Asked for ${localDate(state.requested_at)}. Waiting for it in your Downloads folder`;
  return "LinkedIn's own copy of your record: years of posts and comments, in one file";
}

/** The day in the creator's own time zone; the server records UTC. */
function localDate(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso.slice(0, 10) : when.toLocaleDateString(undefined, { dateStyle: "medium" });
}

function labelFor(preview: ArchivePreview | null, kind: string): string {
  return preview?.files.find((f) => f.kind === kind)?.label ?? kind;
}

function tallyLine(tally: ArchiveKindTally): string {
  if ("left_out" in tally) return "left out";
  if ("not_understood" in tally) return "not understood, nothing imported";
  if ("filled" in tally) return tally.filled.length ? `filled ${tally.filled.join(", ")}` : "nothing was missing";
  const parts = [`${tally.added} added`];
  if (tally.already_there) parts.push(`${tally.already_there} already here`);
  if (tally.skipped) parts.push(`${tally.skipped} skipped`);
  return parts.join(", ");
}

function readable(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
