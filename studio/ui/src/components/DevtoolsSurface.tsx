import { useCallback, useEffect, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import {
  INTERNAL_SHEET_CSV_URL,
  createInternalIssue,
  fetchDevtoolsStatus,
  fetchInternalSheet,
  setInternalIssueStatus,
  type DevtoolsStatus,
  type InternalSheet,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const SEVERITIES = ["low", "medium", "high", "critical"] as const;

/**
 * The maintainer surface (internal sheet and screen registry).
 *
 * Carried across from the vanilla page, which kept it hidden in the markup and
 * revealed it only when devtools mode was on. Every route behind it answers
 * 404 in a consumer build, so the whole surface asks /devtools/status first
 * rather than calling anything and interpreting the 404 as an error.
 */
export function DevtoolsSurface() {
  const [status, setStatus] = useState<DevtoolsStatus | null>(null);
  const [sheet, setSheet] = useState<InternalSheet | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [selector, setSelector] = useState("");
  const [severity, setSeverity] = useState<string>("medium");

  const load = useCallback(async () => {
    const current = await fetchDevtoolsStatus();
    setStatus(current);
    if (current.dev_mode) {
      setSheet(await fetchInternalSheet().catch(() => null));
    }
  }, []);

  useEffect(() => {
    load().catch(() => setStatus(null));
  }, [load]);

  async function onCreate() {
    if (!title.trim() || !description.trim() || !selector.trim()) return;
    setBusy(true);
    setNote(null);
    try {
      await createInternalIssue({
        title: title.trim(),
        description: description.trim(),
        target_selector: selector.trim(),
        severity,
      });
      setTitle("");
      setDescription("");
      setSelector("");
      await load();
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "The issue was refused.");
    } finally {
      setBusy(false);
    }
  }

  if (status === null) return <Centered>READING DEVTOOLS STATUS</Centered>;

  if (!status.dev_mode) {
    return (
      <Centered>
        MAINTAINER SURFACE IS OFF
        <br />
        <span className="text-ink-muted">
          SET {status.env_flag || "THE DEV MODE FLAG"} TO TURN IT ON. EVERY ROUTE BEHIND IT ANSWERS
          404 UNTIL THEN.
        </span>
      </Centered>
    );
  }

  return (
    <div className="mx-auto max-w-[96ch] px-8 py-8">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h2 className="studio-title">Devtools</h2>
        <a
          href={INTERNAL_SHEET_CSV_URL}
          className="studio-meta flex items-center gap-1 text-[10px] text-ink-muted transition-colors hover:text-ink-primary"
        >
          <Download className="size-3" strokeWidth={2} aria-hidden="true" />
          CSV
        </a>
      </div>

      {sheet && (
        <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-2 border-y border-edge py-4 sm:grid-cols-4">
          <Stat label="Issues" value={String(sheet.summary.total)} />
          <Stat label="Open" value={String(sheet.summary.open)} />
          <Stat label="Resolved" value={String(sheet.summary.resolved)} />
          <Stat label="Critical" value={String(sheet.summary.critical)} bad={sheet.summary.critical > 0} />
        </dl>
      )}

      <section className="mt-8 grid gap-6 lg:grid-cols-[300px_1fr]">
        <div className="flex flex-col gap-2">
          <p className="studio-label">Record an issue</p>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Title"
            aria-label="Issue title"
            className="rounded-md border border-edge bg-ink px-2.5 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
          />
          <input
            value={selector}
            onChange={(event) => setSelector(event.target.value)}
            placeholder="Target selector, for example .studio-rail"
            aria-label="Target selector"
            className="rounded-md border border-edge bg-ink px-2.5 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
          />
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={3}
            placeholder="What is wrong, and how to see it"
            aria-label="Issue description"
            className="resize-none rounded-md border border-edge bg-ink px-2.5 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
          />
          <div className="flex flex-wrap gap-1">
            {SEVERITIES.map((candidate) => (
              <button
                key={candidate}
                type="button"
                onClick={() => setSeverity(candidate)}
                aria-pressed={severity === candidate}
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-[10px] uppercase",
                  severity === candidate
                    ? "border-edge-strong bg-soft text-ink-primary"
                    : "border-edge text-ink-muted hover:text-ink-secondary",
                )}
              >
                {candidate}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={onCreate}
            disabled={busy || !title.trim() || !description.trim() || !selector.trim()}
            className="flex items-center justify-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
          >
            {busy && <Loader2 className="size-3 animate-spin" aria-hidden="true" />}
            Record
          </button>
          {note && (
            <p role="status" className="studio-meta leading-snug text-signal-orange-text">
              {note}
            </p>
          )}
        </div>

        <div>
          <p className="studio-label mb-2">Sheet</p>
          {!sheet || sheet.issues.length === 0 ? (
            <p className="studio-meta text-ink-muted">NOTHING RECORDED</p>
          ) : (
            <ul className="flex flex-col">
              {sheet.issues.map((issue) => (
                <li key={issue.id} className="flex items-start gap-3 border-b border-edge py-2">
                  <span
                    className={cn(
                      "studio-meta shrink-0 text-[10px]",
                      issue.severity === "critical" ? "text-signal-orange-text" : "text-ink-muted",
                    )}
                  >
                    {issue.severity.toUpperCase()}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[12px] text-ink-primary">{issue.title}</p>
                    <p className="truncate text-[11px] text-ink-muted">{issue.description}</p>
                  </div>
                  <button
                    type="button"
                    onClick={async () => {
                      const next = issue.status === "resolved" ? "open" : "resolved";
                      await setInternalIssueStatus(issue.id, next).catch(() => undefined);
                      await load();
                    }}
                    className="studio-meta shrink-0 text-[10px] text-ink-muted transition-colors hover:text-ink-primary"
                  >
                    {issue.status === "resolved" ? "REOPEN" : "RESOLVE"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="mt-8">
        <p className="studio-label mb-2">Screen registry</p>
        {/* The registry names the screens the backend believes exist. It is
            here because it used to be checked against the vanilla markup, and
            a rename on one side with no change on the other is exactly what
            that check existed to notice. */}
        <ul className="flex flex-wrap gap-1">
          {status.screens.map((screen) => (
            <li
              key={screen.key}
              className="rounded border border-edge px-1.5 py-0.5 text-[10px] text-ink-secondary"
            >
              {screen.label}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function Stat({ label, value, bad }: { label: string; value: string; bad?: boolean }) {
  return (
    <div>
      <dt className="text-[11px] text-ink-muted">{label}</dt>
      <dd className={cn("studio-meta mt-0.5 text-[13px]", bad ? "text-signal-orange-text" : "text-ink-primary")}>
        {value}
      </dd>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[46ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}
