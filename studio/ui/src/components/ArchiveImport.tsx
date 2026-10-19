import { useEffect, useRef, useState } from "react";
import { ExternalLink, FileArchive, FolderOpen, Loader2 } from "lucide-react";
import {
  discardArchive,
  fetchArchiveState,
  importArchive,
  markArchiveNoPosts,
  markArchiveRequested,
  previewArchive,
  undoArchiveImport,
  uploadArchive,
  type ArchiveKindTally,
  type ArchivePreview,
  type ArchiveState,
  type FoundArchive,
} from "@/lib/api";
import { zipFolder } from "@/lib/folderZip";

const LOOK_MS = 4000;

/**
 * The preview also says whose archive it is: the member LinkedIn made it for,
 * from its Profile.csv, and the creator the studio knows. When they are not
 * plainly one person, or no profile is confirmed yet, `needs_confirmation`
 * says so and nothing is imported until the creator ticks `confirm_label`.
 */
type OwnedPreview = ArchivePreview & {
  owner?: { name: string; headline: string | null; profile_url: string | null } | null;
  creator?: { name: string | null; vanity: string } | null;
  needs_confirmation?: string;
  confirm_label?: string;
};

/**
 * Where the step stands. LinkedIn sends its archive in two parts, and only
 * the complete one has the posts, so the step is `complete` once an import
 * brought them (`held_posts`) or the creator said the account has none.
 */
type ArchiveProgress = Omit<ArchiveState, "found" | "last_import"> & {
  complete?: boolean;
  no_posts_at?: string | null;
  /** The folders Downloads is looked for in, while the step waits. */
  watching?: string[];
  found: (FoundArchive & { imported?: boolean; downloading?: boolean })[];
  last_import: (NonNullable<ArchiveState["last_import"]> & { held_posts?: boolean }) | null;
};

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
  const [preview, setPreview] = useState<OwnedPreview | null>(null);
  const [ownerAgreed, setOwnerAgreed] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<Record<string, ArchiveKindTally> | null>(null);
  const [found, setFound] = useState<ArchiveProgress["found"]>([]);
  const [watching, setWatching] = useState<string[]>([]);
  const [waiting, setWaiting] = useState(state.waiting);
  const picker = useRef<HTMLInputElement>(null);
  const folderPicker = useRef<HTMLInputElement | null>(null);
  const chooser = useRef<HTMLButtonElement>(null);
  const previewTitle = useRef<HTMLParagraphElement>(null);
  const resultTitle = useRef<HTMLParagraphElement>(null);
  const progress = state as ArchiveProgress;

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
          setWatching((fresh as ArchiveProgress).watching ?? []);
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

  function show(found: OwnedPreview) {
    setPreview(found);
    setResult(null);
    setOwnerAgreed(false);
    setTicked(new Set(found.files.filter((f) => f.importable && f.default).map((f) => f.kind)));
    if (!found.recognised) setNote("This file does not look like LinkedIn's data archive.");
  }


  return (
    <div className="flex flex-col gap-3">
      {!preview && (
        <>
          {progress.last_import && !progress.complete ? (
            <div className="flex flex-col items-start gap-2">
              <p className="text-[13px] leading-relaxed text-ink-secondary">
                {"posts" in progress.last_import.summary
                  ? "Your posts were not imported from that archive. To bring them in, import it again with " +
                    "Posts you wrote ticked."
                  : "That was LinkedIn's first part, which has no posts. The complete archive, with your posts, " +
                    "comments and reactions, usually follows within a day. " +
                    (waiting
                      ? "This step keeps looking for it in your Downloads folder."
                      : "When it arrives, choose it here, or click I have asked for it and this step will look " +
                        "for it in your Downloads folder.")}
              </p>
              <button
                type="button"
                disabled={busy !== null}
                onClick={() =>
                  void run("no-posts", async () => {
                    await markArchiveNoPosts();
                    onChanged();
                  })
                }
                className="rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
              >
                My account has no posts
              </button>
            </div>
          ) : state.last_import ? (
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
                    setWatching((fresh as ArchiveProgress).watching ?? []);
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
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => folderPicker.current?.click()}
              className="flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
            >
              {busy === "folder" ? (
                <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <FolderOpen className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
              )}
              Choose the folder
            </button>
            <input
              ref={(input) => {
                folderPicker.current = input;
                // A folder chooser; React has no prop for it.
                input?.setAttribute("webkitdirectory", "");
              }}
              type="file"
              tabIndex={-1}
              className="sr-only"
              aria-label="Choose the folder your LinkedIn data archive was unpacked into"
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                event.target.value = "";
                if (files.length) void run("folder", async () => show(await uploadArchive(await zipFolder(files))));
              }}
            />
          </div>
          <p className="studio-meta -mt-1 text-[10px] text-ink-muted">
            IF YOUR BROWSER UNPACKED THE ARCHIVE INTO A FOLDER, AS SAFARI DOES, CHOOSE THE FOLDER
          </p>

          {waiting && (
            <div>
              <p className="studio-meta text-[10px] text-ink-muted">
                IN YOUR DOWNLOADS FOLDER{watching.length > 0 ? ` (${watching.join(", ")})` : ""}
                {found.length === 0 ? ": NOTHING FROM LINKEDIN YET" : ""}
              </p>
              {found.length > 0 && (
                <ul className="mt-1.5 flex flex-col gap-1.5">
                  {found.map((hit) => (
                    <li key={hit.path} className="flex items-center justify-between gap-3">
                      <span className="min-w-0 truncate text-[13px] text-ink-secondary">
                        {hit.name}
                        <span className="studio-meta ml-2 text-[10px] text-ink-muted">
                          {readable(hit.bytes)} · {localDate(hit.modified)}
                          {hit.imported ? " · ALREADY IMPORTED" : ""}
                          {hit.downloading ? " · STILL DOWNLOADING" : ""}
                        </span>
                      </span>
                      <button
                        type="button"
                        disabled={busy !== null || hit.downloading}
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

          {state.last_import &&
            (removing ? (
              <div className="rounded-md border border-edge p-3" role="group" aria-label="Remove the last import">
                <p className="text-[13px] leading-relaxed text-ink-secondary">
                  Remove the posts, comments, reactions, roles, skills, connections and profile details that{" "}
                  {state.last_import.archive_name} added? What was in the studio before it, and what the bridge
                  has read since, is kept.
                </p>
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    disabled={busy !== null}
                    onClick={() =>
                      void run("remove", async () => {
                        const done = await undoArchiveImport();
                        setRemoving(false);
                        setNote(removedLine(done.removed));
                        onChanged();
                      })
                    }
                    className="flex items-center gap-1.5 rounded-md border border-edge-strong px-2.5 py-1 text-[12px] text-ink-primary transition-colors hover:bg-soft disabled:opacity-40"
                  >
                    {busy === "remove" && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
                    Remove it
                  </button>
                  <button
                    type="button"
                    disabled={busy !== null}
                    onClick={() => setRemoving(false)}
                    className="rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                  >
                    Keep it
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => setRemoving(true)}
                className="self-start text-[12px] text-ink-muted underline-offset-2 transition-colors hover:text-ink-primary hover:underline disabled:opacity-40"
              >
                Remove what this import added
              </button>
            ))}
        </>
      )}

      {preview && !result && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void run("import", async () => {
              const done = await importArchive(preview.source, [...ticked], ownerAgreed);
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
          {preview.needs_confirmation ? (
            <div className="mt-3 rounded-md border border-signal-orange/40 bg-signal-orange-subtle p-3">
              <p className="text-[13px] leading-relaxed text-signal-orange-text">{preview.needs_confirmation}</p>
              <label className="mt-2 flex items-start gap-2 text-[13px] text-ink-primary">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={ownerAgreed}
                  onChange={(event) => setOwnerAgreed(event.target.checked)}
                />
                <span>{preview.confirm_label}</span>
              </label>
            </div>
          ) : (
            preview.owner && (
              <p className="mt-2 text-[13px] text-ink-secondary">
                This archive belongs to <span className="text-ink-primary">{preview.owner.name}</span>, the
                profile you confirmed.
              </p>
            )
          )}
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
              disabled={busy !== null || ticked.size === 0 || (!!preview.needs_confirmation && !ownerAgreed)}
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
  const progress = state as ArchiveProgress;
  if (progress.last_import && progress.complete === false) {
    return `Imported ${localDate(progress.last_import.imported_at)} from ${progress.last_import.archive_name}, without your posts`;
  }
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

const REMOVED_WORDS: Record<string, [string, string]> = {
  posts: ["post", "posts"],
  comments: ["comment", "comments"],
  reactions: ["reaction", "reactions"],
  positions: ["role", "roles"],
  education: ["school", "schools"],
  skills: ["skill", "skills"],
  connections: ["connection", "connections"],
  profile: ["profile detail", "profile details"],
};

function removedLine(removed: Record<string, number>): string {
  const parts = Object.entries(REMOVED_WORDS)
    .filter(([kind]) => (removed[kind] ?? 0) > 0)
    .map(([kind, [one, many]]) => `${removed[kind]} ${removed[kind] === 1 ? one : many}`);
  if (parts.length === 0) return "Removed the record of that import. Nothing it added was still in the studio.";
  const list = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}` : parts[0];
  return `Removed what that import added: ${list}.`;
}

function readable(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
