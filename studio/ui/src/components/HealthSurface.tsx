import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import {
  fetchBackupSchedule,
  fetchExtensionHealth,
  fetchHealthReader,
  fetchHealthReaders,
  fetchPostFieldSightings,
  fetchRecordHealth,
  fetchSchemaStatus,
  fetchUpdateStatus,
  runUpdateCheck,
  setUpdatePreference,
  type BackupSchedule,
  type ExtensionHealth,
  type HealthReader,
  type HealthReaderDetail,
  type HealthReaders,
  type PostFieldSightings,
  type RecordHealth,
  type SchemaStatus,
  type UpdateStatus,
} from "@/lib/api";
import { reportBridge } from "@/lib/bridgeState";
import { useRefresh, type StudioChangeNote } from "@/lib/refresh";
import { formatLocal, formatLocalDay } from "@/lib/time";
import { cn } from "@/lib/utils";

/**
 * Health: is the bridge reading, what did each reader read in the last seven
 * days, and what could it not read?
 *
 * Where a creator looks when the rest of the studio looks wrong. It used to
 * be a block at the foot of Setup, which is a first-run flow rather than a
 * place work happens, and it showed each reader's state and nothing of its
 * runs: a reader was "working" with no way to see how often it ran, how much
 * it saw or how much it kept.
 *
 * Every figure carries its window, because none of them is "ever": the run
 * rows are the capture log, which the studio prunes to seven days, so they
 * say "last 7 days" whether or not anyone would prefer more; the day rows say
 * how long they are kept; waiting captures and refusals are counted since
 * the studio started and say so. What the studio has not been told reads as
 * a sentence, never as a zero.
 */
const POLL_MS = 30_000;

/**
 * The least time between two reads the change stream causes. Health reads six
 * routes, and a feed scroll lands a run every few seconds: fifteen seconds, as
 * Today and the header use, keeps it to four reads a minute however busy the
 * bridge is, and a run after a quiet spell is still read at once.
 */
const CHANGE_GAP_MS = 15_000;

/** A reader's run, or the bridge heard from: the two things this screen counts as they land. */
function healthMayChange(change: StudioChangeNote): boolean {
  return change.kind === "capture" || change.kind === "heartbeat";
}

/** How many day rows a reader opens on; the rest are counted, not listed. */
const DAYS_SHOWN = 14;

export function HealthSurface({ onOpenSetup }: { onOpenSetup?: () => void } = {}) {
  const [readers, setReaders] = useState<HealthReaders | null>(null);
  const [extension, setExtension] = useState<ExtensionHealth | null>(null);
  const [schema, setSchema] = useState<SchemaStatus | null>(null);
  const [backups, setBackups] = useState<BackupSchedule | null>(null);
  const [updates, setUpdates] = useState<UpdateStatus | null>(null);
  const [sightings, setSightings] = useState<PostFieldSightings | null>(null);
  const [record, setRecord] = useState<RecordHealth | null>(null);
  /** The parts of the screen whose route did not answer on the last read. */
  const [unanswered, setUnanswered] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [updateBusy, setUpdateBusy] = useState(false);
  const [updateNote, setUpdateNote] = useState<string | null>(null);

  // Five routes, read together. One failing leaves the others on screen and
  // its own block saying so, rather than blanking the whole section.
  const load = useCallback(async () => {
    const [r, e, s, b, u, f, d] = await Promise.allSettled([
      fetchHealthReaders(),
      fetchExtensionHealth(),
      fetchSchemaStatus(),
      fetchBackupSchedule(),
      fetchUpdateStatus(),
      fetchPostFieldSightings(),
      fetchRecordHealth(),
    ]);
    const missing: string[] = [];
    if (r.status === "fulfilled") setReaders(r.value);
    else missing.push("readers");
    if (e.status === "fulfilled") {
      setExtension(e.value);
      reportBridge(e.value.bridge.connected);
    } else missing.push("bridge");
    if (s.status === "fulfilled") setSchema(s.value);
    else missing.push("schema");
    if (b.status === "fulfilled") setBackups(b.value);
    else missing.push("backups");
    if (u.status === "fulfilled") setUpdates(u.value);
    else missing.push("updates");
    if (f.status === "fulfilled") setSightings(f.value);
    else missing.push("post analytics fields");
    if (d.status === "fulfilled") setRecord(d.value);
    else missing.push("From your record");
    setUnanswered(missing);
    setLoaded(true);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);
  // When a reader runs or the bridge is heard from (studio/backend/changes.py),
  // as Setup read the readers' lines before they moved here, and every
  // POLL_MS while in view, for the bridge going quiet, which nothing announces.
  useRefresh(load, POLL_MS, { gapMs: CHANGE_GAP_MS, matters: healthMayChange });

  async function chooseUpdates(enabled: boolean) {
    setUpdateBusy(true);
    setUpdateNote(null);
    try {
      await setUpdatePreference(enabled);
      setUpdates(await fetchUpdateStatus());
      setUpdateNote(enabled ? "On. A version check is a request to GitHub; nothing is downloaded or installed." : "Off. Nothing is sent.");
    } catch (caught) {
      setUpdateNote(caught instanceof Error ? caught.message : "The preference could not be saved.");
    } finally {
      setUpdateBusy(false);
    }
  }

  async function checkNow() {
    setUpdateBusy(true);
    setUpdateNote(null);
    try {
      const result = await runUpdateCheck();
      if (!result.checked) setUpdateNote(result.reason ?? result.error ?? "No check was made.");
      else if (result.error) setUpdateNote(result.error);
      else if (result.update_available) setUpdateNote(`Version ${result.latest_version} is available. ${result.notes ?? ""}`.trim());
      else setUpdateNote(`You have the newest version${result.latest_version ? ` (${result.latest_version})` : ""}.`);
      setUpdates(await fetchUpdateStatus());
    } catch (caught) {
      setUpdateNote(caught instanceof Error ? caught.message : "The check could not be made.");
    } finally {
      setUpdateBusy(false);
    }
  }

  if (!loaded) {
    return (
      <div className="grid h-full place-items-center px-8">
        <div className="flex items-center gap-2 text-ink-muted">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          <span className="studio-meta text-[11px]">READING THE BRIDGE</span>
        </div>
      </div>
    );
  }

  if (!readers && !extension) {
    return (
      <div className="grid h-full place-items-center px-8">
        <div className="max-w-[44ch] text-center">
          <p className="studio-label text-signal-orange-text">HEALTH IS UNAVAILABLE</p>
          <p className="mt-2 text-[13px] text-ink-muted">
            The studio is not answering, or refused this screen&apos;s requests. Check that it is still running, then retry.
          </p>
          <button
            type="button"
            onClick={() => void load()}
            className="mt-4 rounded-md border border-edge bg-soft px-3 py-1.5 text-[12px] font-medium text-ink-primary hover:bg-raised"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const listed = readers?.readers ?? [];
  const working = listed.filter((r) => r.state === "working").length;
  const drifting = listed.filter((r) => r.state === "drifting").length;
  const reading = readers?.network_reading ?? null;
  const bridge = extension?.bridge ?? null;

  return (
    // tabIndex, because at phone width this screen is taller than the window
    // and a region that scrolls with nothing focusable in it cannot be
    // scrolled by keyboard (axe: scrollable-region-focusable).
    <div className="px-6 py-6 lg:px-8" tabIndex={0} aria-labelledby="health-title">
      <header className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
        <div>
          <p className="studio-label">Health</p>
          <h1 id="health-title" className="studio-title mt-1">Is the bridge reading?</h1>
        </div>
        <div className="max-w-[62ch] text-[12px] leading-snug text-ink-secondary">
          {bridge ? (
            <p>
              <span className={cn("mr-1.5 inline-block size-1.5 rounded-full align-middle", bridge.connected ? "bg-signal-green" : "bg-edge-strong")} aria-hidden="true" />
              {bridgeSentence(bridge)}
              {/* Only once the bridge has been heard from: with no heartbeat at all the
                  handshake has nothing to judge, and "older than the studio" would be a guess. */}
              {bridge.last_seen_at && extension?.contract.reload_required && extension.contract.message ? ` ${extension.contract.message}` : ""}
            </p>
          ) : (
            <p>The bridge&apos;s state was not answered by the studio on the last read.</p>
          )}
        </div>
      </header>

      {unanswered.length > 0 && (
        <p role="status" className="mt-3 text-[12px] text-signal-orange-text">
          The studio did not answer for: {unanswered.join(", ")}. Those blocks show nothing rather than a guess.
        </p>
      )}

      {/* Four figures, each a count of rows, with the window each one covers. */}
      <dl className="mt-4 grid grid-cols-2 gap-px border border-edge bg-edge sm:grid-cols-4">
        <Figure label={`Readers working, of ${listed.length}`} value={readers ? String(working) : "not answered"} />
        <Figure label="Readers that cannot read" value={readers ? String(drifting) : "not answered"} />
        <Figure
          label="Captures waiting, as last reported"
          value={extension ? (extension.waiting_captures.measured ? String(extension.waiting_captures.waiting ?? 0) : "not reported") : "not answered"}
        />
        <Figure
          label={`Heartbeats, ${readers?.heartbeats.label ?? "last 7 days"}`}
          value={readers ? readers.heartbeats.count.toLocaleString() : "not answered"}
        />
      </dl>

      <div className="mt-4 grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        {/* The readers, with their runs inside the prune's window. */}
        <section aria-labelledby="readers-heading">
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <p id="readers-heading" className="studio-label">Readers, {readers?.window.label ?? "last 7 days"}</p>
            <p className="studio-meta text-[10px] text-ink-muted">
              THE STUDIO KEEPS A WEEK OF RUNS, AND A ROW PER READER PER DAY {readers ? readers.days_window.label.toUpperCase() : ""}
            </p>
          </div>
          {readers && (
            // Network reading in its three honest states, in the studio's one
            // sentence (onboarding.network_reading_sentence): off, on and
            // seeing LinkedIn's data calls, or on and matching nothing. It sits
            // over the readers because its two readers are listed only while
            // it is on or once they have run (onboarding.listed_health).
            <p className={cn("mb-2 text-[12px] leading-snug", reading?.state === "matching_nothing" ? "text-signal-orange-text" : "text-ink-secondary")}>
              <span
                aria-hidden="true"
                className={cn(
                  "mr-1.5 inline-block size-1.5 rounded-full align-middle",
                  reading?.state === "seeing" && "bg-signal-green",
                  reading?.state === "matching_nothing" && "bg-signal-orange",
                  (!reading || reading.state === "off") && "bg-edge-strong",
                )}
              />
              {reading ? reading.sentence : "Whether network reading is on is not reported by this extension version."}
            </p>
          )}
          {!readers ? (
            <p className="text-[13px] text-ink-muted">The readers were not answered by the studio on the last read.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[12px]">
                <thead>
                  <tr className="studio-meta text-[10px] text-ink-muted">
                    <th className="py-1 font-normal">READER</th>
                    <th className="py-1 font-normal">STATE</th>
                    <th className="py-1 pl-3 text-right font-normal">RUNS</th>
                    <th className="py-1 pl-3 text-right font-normal">SEEN</th>
                    <th className="py-1 pl-3 text-right font-normal">KEPT</th>
                    <th className="py-1 pl-3 text-right font-normal">DRIFTED</th>
                    <th className="py-1 pl-3 text-right font-normal whitespace-nowrap">LAST READ</th>
                    <th className="py-1 pl-3 text-right font-normal whitespace-nowrap">LAST WORKED</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-edge border-y border-edge">
                  {readers.readers.map((reader) => (
                    <ReaderRows
                      key={reader.extractor}
                      reader={reader}
                      open={open === reader.extractor}
                      onToggle={() => setOpen(open === reader.extractor ? null : reader.extractor)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {drifting > 0 && (
            <p className="mt-2 text-[12px] leading-snug text-ink-muted">
              A reader that cannot read found the page but not the fields it needs, which usually means LinkedIn has
              changed how the page is built. Nothing from that part is being captured until the extension is updated.
            </p>
          )}
          {listed.some((r) => r.state === "refused" && r.refused === "identity") && (
            <p className="mt-2 text-[12px] leading-snug text-ink-muted">
              A reader REFUSED for IDENTITY ran, and the studio refused what it read: the LinkedIn account signed in to
              the bridge browser is not the profile confirmed in Setup, or has not been noted yet. Open your own profile
              in that browser once.
            </p>
          )}

          {readers && (
            <div className="mt-5">
              <p className="studio-label mb-2">All readers by day, {readers.by_day.label}</p>
              <table className="w-full text-left text-[12px]">
                <thead>
                  <tr className="studio-meta text-[10px] text-ink-muted">
                    <th className="py-1 font-normal">DAY (UTC)</th>
                    <th className="py-1 pl-3 text-right font-normal">RUNS</th>
                    <th className="py-1 pl-3 text-right font-normal">SEEN</th>
                    <th className="py-1 pl-3 text-right font-normal">KEPT</th>
                    <th className="py-1 pl-3 text-right font-normal">DRIFTED</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-edge border-y border-edge">
                  {readers.by_day.rows.map((row) => (
                    <tr key={row.day}>
                      <td className="py-0.5 text-ink-secondary">{formatLocalDay(`${row.day}T12:00:00Z`)}</td>
                      {row.state === "read" ? (
                        <>
                          <td className="py-0.5 pl-3 text-right tabular-nums">{(row.runs ?? 0).toLocaleString()}</td>
                          <td className="py-0.5 pl-3 text-right tabular-nums whitespace-nowrap">{measured(row.items_seen)}</td>
                          <td className="py-0.5 pl-3 text-right tabular-nums whitespace-nowrap">{measured(row.items_kept)}</td>
                          <td className="py-0.5 pl-3 text-right tabular-nums">{(row.drift_runs ?? 0).toLocaleString()}</td>
                        </>
                      ) : (
                        <td colSpan={4} className="py-0.5 pl-3 text-right text-ink-muted">
                          {row.state === "nothing_read" ? "nothing read" : "before the studio kept days"}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {listed.length > 0 && listed.every((r) => r.state === "never_run") && onOpenSetup && (
            <p className="mt-2 text-[12px] leading-snug text-ink-muted">
              No reader has run yet. Setup connects the bridge browser and opens the pages the readers read.{" "}
              <button type="button" onClick={onOpenSetup} className="underline decoration-edge-strong underline-offset-2 hover:text-ink-primary">
                Go to Setup
              </button>
            </p>
          )}
        </section>

        <div className="flex flex-col gap-5">
          <Block title={`Bridge heartbeats, ${readers?.heartbeats.label ?? "last 7 days"}`}>
            {!readers ? (
              <Muted>Not answered on the last read.</Muted>
            ) : readers.heartbeats.count === 0 ? (
              <Muted>No heartbeat in the {readers.heartbeats.label}. The extension sends one a minute while a LinkedIn tab is open.</Muted>
            ) : (
              <dl className="flex flex-col gap-1">
                <Row label="Heard from" value={`${readers.heartbeats.count.toLocaleString()} times, first ${formatLocal(readers.heartbeats.first_seen_at)}, last ${formatLocal(readers.heartbeats.last_seen_at)}`} />
                <Row
                  label="Longest silence"
                  value={
                    readers.heartbeats.longest_silence_minutes === null
                      ? "not measurable from one heartbeat"
                      : `${minutes(readers.heartbeats.longest_silence_minutes)}, ending ${formatLocal(readers.heartbeats.longest_silence_ended_at)}`
                  }
                />
                {readers.heartbeats.versions.map((version) => (
                  <Row
                    key={version.extension_version ?? "unknown"}
                    label={`Extension ${version.extension_version ?? "of unknown version"}`}
                    value={`${version.count.toLocaleString()} heartbeats, ${formatLocal(version.first_seen_at)} to ${formatLocal(version.last_seen_at)}`}
                  />
                ))}
              </dl>
            )}
          </Block>

          <Block title="Waiting captures and refusals, since the studio started">
            {!extension ? (
              <Muted>Not answered on the last read.</Muted>
            ) : (
              <dl className="flex flex-col gap-1">
                <Row
                  label="Waiting"
                  value={
                    extension.waiting_captures.measured
                      ? `${(extension.waiting_captures.waiting ?? 0).toLocaleString()} captures held by the extension${extension.waiting_captures.oldest_at ? `, oldest ${formatLocal(extension.waiting_captures.oldest_at)}` : ""}, as it last said ${formatLocal(extension.waiting_captures.reported_at)}`
                      : extension.waiting_captures.message ?? "The extension has not reported since the studio started."
                  }
                />
                {Object.keys(extension.refusals.refusals).length === 0 ? (
                  <Row label="Refused" value="no capture refused since the studio started" />
                ) : (
                  Object.entries(extension.refusals.refusals)
                    .sort((a, b) => b[1] - a[1])
                    .map(([reason, count]) => (
                      <Row key={reason} label={`Refused: ${reason.replace(/_/g, " ")}`} value={`${count.toLocaleString()} captures`} />
                    ))
                )}
              </dl>
            )}
          </Block>

          <Block title="Network reading and drift">
            {!extension ? (
              <Muted>Not answered on the last read.</Muted>
            ) : extension.recent_drift.length === 0 ? (
              <Muted>{driftEmptyLine(extension)}</Muted>
            ) : (
              <ul className="flex flex-col gap-1 text-[12px] text-ink-secondary">
                {extension.recent_drift.map((event, index) => (
                  <li key={`${event.schema_name}-${event.observed_at}-${index}`} className="flex items-baseline justify-between gap-3">
                    <span className="truncate">
                      {event.schema_name} {event.schema_version}: {event.drift_fields.length ? event.drift_fields.join(", ") : "no field named"}
                    </span>
                    <span className="studio-meta shrink-0 text-[10px] text-ink-muted">{formatLocal(event.observed_at).toUpperCase()}</span>
                  </li>
                ))}
              </ul>
            )}
          </Block>

          {/* Post analytics fields (track 5): for each figure the post
              analytics reader added in cycle 4, when a post analytics page
              last carried it, or on how many pages it was not read. A figure
              LinkedIn does not show on every post is not drift, so this is
              where one that never appears shows. The sentences are the
              studio's own (onboarding.post_analytics_sightings). */}
          <Block title="Post analytics fields">
            {!sightings ? (
              <Muted>Not answered on the last read.</Muted>
            ) : (
              <>
                <ul className="flex flex-col gap-0.5 text-[12px] leading-snug text-ink-secondary">
                  {sightings.fields.map((field) => (
                    <li key={field.field}>{field.sentence}</li>
                  ))}
                </ul>
                <p className="mt-1.5 text-[11px] leading-snug text-ink-muted">{sightings.meaning}</p>
              </>
            )}
          </Block>

          <Block title="Database schema">
            {!schema ? (
              <Muted>Not answered on the last read.</Muted>
            ) : (
              <dl className="flex flex-col gap-1">
                <Row label="Schema" value={`${schema.current_version} of ${schema.target_version}, studio ${schema.app_version}`} />
                <Row label="State" value={schema.advice} />
                {schema.pending.length > 0 && (
                  <Row label="Pending" value={schema.pending.map((p) => p.description).join("; ")} />
                )}
              </dl>
            )}
          </Block>

          <Block title="Backup schedule">
            {!backups ? (
              <Muted>Not answered on the last read.</Muted>
            ) : (
              <dl className="flex flex-col gap-1">
                <Row label="Daily backup" value={backups.enabled ? "on" : "off"} />
                <Row
                  label="Newest backup"
                  value={backups.never || !backups.last ? "none yet" : `${formatLocal(backups.last.made_at)}, ${backups.last.name}`}
                />
                {backups.enabled && <Row label="Next due" value={formatLocal(backups.next_due, "now")} />}
                {backups.stale && (
                  <Row
                    label="Schedule"
                    value={`stopped: no backup for ${Math.round(backups.age_hours ?? 0)} hours, while the daily backup is on`}
                  />
                )}
              </dl>
            )}
          </Block>

          {/* From your record (track 7): the daily job's last run and whether it
              carried forward, the model stage's spend against its ceiling, and
              the library's signature, each in the studio's own sentence
              (record_health.py). */}
          <Block title="From your record, the daily cards">
            {!record ? (
              <Muted>Not answered on the last read.</Muted>
            ) : (
              <dl className="flex flex-col gap-1">
                <Row label="Daily batch" value={record.job.sentence} />
                <Row label="Model stage" value={record.model.sentence} />
                <Row label="Inox library" value={record.library.sentence} />
              </dl>
            )}
          </Block>

          <Block title="Update check">
            {!updates ? (
              <Muted>Not answered on the last read.</Muted>
            ) : (
              <div className="flex flex-col gap-2">
                {/* Off by default, and the only outbound request the product
                    makes. The switch shows what the studio holds; it never
                    assumes on. */}
                <label className="flex items-start gap-2 text-[13px] text-ink-secondary">
                  <input
                    type="checkbox"
                    checked={updates.enabled}
                    disabled={updateBusy}
                    onChange={(event) => void chooseUpdates(event.target.checked)}
                    className="mt-0.5"
                  />
                  <span>
                    Check GitHub for a newer version. {updates.enabled ? "On." : "Off."} Studio {updates.current_version}.
                    {updates.last_checked ? ` Last checked ${formatLocal(updates.last_checked)}.` : " Never checked."}
                    {updates.last_seen_version ? ` Newest seen ${updates.last_seen_version}.` : ""}
                  </span>
                </label>
                {updates.enabled ? (
                  <button
                    type="button"
                    onClick={() => void checkNow()}
                    disabled={updateBusy}
                    className="w-fit rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                  >
                    Check now
                  </button>
                ) : (
                  <Muted>While this is off, no request leaves this machine for a version check.</Muted>
                )}
                {updateNote && <p role="status" className="text-[12px] leading-snug text-ink-muted">{updateNote}</p>}
              </div>
            )}
          </Block>
        </div>
      </div>
    </div>
  );
}

function ReaderRows({
  reader,
  open,
  onToggle,
}: {
  reader: HealthReader;
  open: boolean;
  onToggle: () => void;
}) {
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <>
      <tr className={cn((reader.state === "drifting" || reader.state === "refused") && "text-signal-orange-text")}>
        <td className="py-1 text-ink-primary">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={open}
            className="flex items-center gap-1 text-left hover:text-signal-orange-text"
          >
            <Chevron className="size-3.5 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
            {reader.label}
          </button>
        </td>
        <td className="studio-meta py-1 text-[10px]">{stateWords(reader)}</td>
        <td className="py-1 pl-3 text-right tabular-nums">{reader.runs.toLocaleString()}</td>
        <td className="py-1 pl-3 text-right tabular-nums whitespace-nowrap">{measured(reader.items_seen)}</td>
        <td className="py-1 pl-3 text-right tabular-nums whitespace-nowrap">{measured(reader.items_kept)}</td>
        <td className="py-1 pl-3 text-right tabular-nums">{reader.drift_runs.toLocaleString()}</td>
        <td className="py-1 pl-3 text-right text-ink-secondary whitespace-nowrap">{formatLocal(reader.last_run_at, "never")}</td>
        <td className="py-1 pl-3 text-right text-ink-secondary whitespace-nowrap">{formatLocal(reader.last_good_at, "never")}</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={8} className="bg-canvas px-3 py-2">
            <ReaderDetail extractor={reader.extractor} />
          </td>
        </tr>
      )}
    </>
  );
}

/** One reader one level down, read when it is opened rather than with the first view. */
function ReaderDetail({ extractor }: { extractor: string }) {
  const [detail, setDetail] = useState<HealthReaderDetail | null>(null);
  const [failed, setFailed] = useState(false);
  const [allDays, setAllDays] = useState(false);

  useEffect(() => {
    let live = true;
    fetchHealthReader(extractor)
      .then((answer) => live && setDetail(answer))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [extractor]);

  if (failed) return <Muted>This reader&apos;s runs were not answered by the studio.</Muted>;
  if (!detail) return <Muted>Reading this reader&apos;s runs.</Muted>;
  return (
    <>
      {detail.rows.length === 0 ? (
        <Muted>No run in the {detail.window.label}.</Muted>
      ) : (
        <ul className="flex flex-col gap-0.5 text-[11px] text-ink-secondary">
          {detail.rows.map((run) => (
            <li key={run.observed_at} className="flex flex-wrap items-baseline gap-x-3">
              <span className="studio-meta w-[18ch] text-[10px] text-ink-muted">{formatLocal(run.observed_at).toUpperCase()}</span>
              <span>{run.page_kind ?? "page not named"}</span>
              <span className="tabular-nums">seen {measured(run.items_seen)}, kept {measured(run.items_kept)}</span>
              {run.drift.length > 0 && <span className="text-signal-orange-text">could not read {run.drift.join(", ")}</span>}
              {run.refused && <span className="text-signal-orange-text">refused: {run.refused}</span>}
              {run.extension_version && <span className="text-ink-muted">extension {run.extension_version}</span>}
            </li>
          ))}
          {detail.runs > detail.rows.length && (
            <li className="text-ink-muted">
              The newest {detail.rows.length} of {detail.runs.toLocaleString()} runs in the {detail.window.label}.
            </li>
          )}
        </ul>
      )}
      <p className="studio-meta mt-2 text-[10px] text-ink-muted">BY DAY, {detail.days_window.label.toUpperCase()}</p>
      {detail.days.length === 0 ? (
        <Muted>No day rows yet.</Muted>
      ) : (
        <ul className="mt-0.5 flex flex-col gap-0.5 text-[11px] text-ink-secondary">
          {(allDays ? detail.days : detail.days.slice(0, DAYS_SHOWN)).map((day) => (
            <li key={day.day} className="flex flex-wrap items-baseline gap-x-3">
              <span className="studio-meta w-[12ch] text-[10px] text-ink-muted">{day.day}</span>
              <span className="tabular-nums">
                {day.runs.toLocaleString()} {day.runs === 1 ? "run" : "runs"}, seen {measured(day.items_seen)}, kept {measured(day.items_kept)}
                {day.drift_runs > 0 ? `, ${day.drift_runs} drifted` : ""}
              </span>
            </li>
          ))}
          {detail.days.length > DAYS_SHOWN && (
            <li className="text-ink-muted">
              {allDays ? `All ${detail.days.length.toLocaleString()} days held. ` : `The newest ${DAYS_SHOWN} of ${detail.days.length.toLocaleString()} days held. `}
              <button
                type="button"
                onClick={() => setAllDays(!allDays)}
                className="underline decoration-edge-strong underline-offset-2 hover:text-ink-primary"
              >
                {allDays ? `Show the newest ${DAYS_SHOWN}` : "Show every day"}
              </button>
            </li>
          )}
        </ul>
      )}
    </>
  );
}

/**
 * Each of capture_health's five states (onboarding.CAPTURE_STATES), in the
 * words Setup used before the block moved here. A run that read nothing and a
 * run the studio refused are runs, and used to read WORKING. LAST READ and
 * LAST WORKED are columns of their own, so the words do not repeat them.
 */
function stateWords(reader: HealthReader): string {
  switch (reader.state) {
    case "never_run":
      return "NOT SEEN YET";
    case "working":
      return "WORKING";
    case "read_nothing":
      return "READ NOTHING";
    case "drifting":
      return `CANNOT READ ${reader.drift.join(", ").toUpperCase().replace(/_/g, " ")}`;
    case "refused":
      return `REFUSED: ${(reader.refused ?? "reason not given").toUpperCase()}`;
  }
}

function bridgeSentence(bridge: ExtensionHealth["bridge"]): string {
  if (bridge.connected) {
    return `Connected${bridge.extension_version ? `, extension ${bridge.extension_version}` : ""}${bridge.seconds_ago !== null ? `, heard from ${ago(bridge.seconds_ago)}` : ""}.`;
  }
  if (bridge.seconds_ago !== null) return `Last heard from ${ago(bridge.seconds_ago)}. Open a LinkedIn tab in the bridge browser.`;
  return "Not seen yet. Open a LinkedIn tab in the bridge browser with the extension loaded.";
}

function driftEmptyLine(extension: ExtensionHealth): string {
  const reading = extension.bridge.network_reading;
  if (reading && reading.switch === false) return "Network reading is off, so there are no drift events: the page readers report what they cannot read in the table.";
  if (reading && reading.switch === true) return "Network reading is on and no drift event has been recorded.";
  return "No drift event is held. Whether network reading is on is not reported by this extension version.";
}

function measured(value: number | null | undefined): string {
  return value === null || value === undefined ? "not measured" : value.toLocaleString();
}

function minutes(total: number): string {
  if (total < 90) return `${total} min`;
  if (total < 2880) return `${Math.round(total / 60)} h`;
  return `${Math.round(total / 1440)} days`;
}

function ago(seconds: number): string {
  if (seconds < 90) return `${seconds} s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} days ago`;
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-ink px-3 py-1.5">
      <dt className="studio-meta text-[10px] text-ink-muted">{label.toUpperCase()}</dt>
      <dd className={cn("tabular-nums text-ink-primary", value.startsWith("not") ? "text-[12px] text-ink-muted" : "text-[14px]")}>{value}</dd>
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-md border border-edge px-3 py-2">
      <p className="studio-label mb-1.5">{title}</p>
      {children}
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="shrink-0 text-[12px] text-ink-muted">{label}</dt>
      <dd className="text-right text-[12px] leading-snug text-ink-secondary">{value}</dd>
    </div>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <p className="text-[12px] leading-snug text-ink-muted">{children}</p>;
}
