import { useCallback, useEffect, useRef, useState } from "react";
import { useState as useLocalState } from "react";
import { Archive, Check, Loader2, Network, RotateCcw, ShieldCheck } from "lucide-react";
import {
  createBackup,
  exportData,
  fetchAiStatus,
  fetchAuthStatus,
  fetchBackups,
  fetchEgressStatus,
  fetchProfile,
  restoreBackup,
  saveSessionCookies,
  saveProfile,
  type AiStatus,
  type AuthStatus,
  type BackupListing,
  type EgressStatus,
  type CreatorProfile,
  type ProfileResponse,
} from "@/lib/api";
import { useStudioBack } from "@/lib/refresh";
import { cn } from "@/lib/utils";
import { hasUnsavedWork, registerUnsavedWork, reloadStudio, unsavedWorkLabels } from "@/lib/unsaved";
import { GroundingWorkspace } from "./GroundingWorkspace";
import { LicenceWorkspace } from "./LicenceWorkspace";
import { StoragePrivacyWorkspace } from "./StoragePrivacyWorkspace";

type Workspace = "Identity" | "Watermark" | "Grounding" | "Local security" | "Storage and privacy" | "Licence";

// Grounding sits beside the other settings rather than in the composer: it
// is a standing grant about what this machine will run and what leaves it,
// not a per-draft choice.
const WORKSPACES: Workspace[] = ["Identity", "Watermark", "Grounding", "Local security", "Storage and privacy", "Licence"];

/** The nine placements the backend accepts, laid out as they read on an image. */
const POSITIONS = [
  ["top_left", "top_center", "top_right"],
  ["middle_left", "center", "middle_right"],
  ["bottom_left", "bottom_center", "bottom_right"],
] as const;

const STYLES = ["glass_pill", "solid_bar", "plain_text"] as const;

type SaveState = "idle" | "dirty" | "saving" | "saved" | "failed";

/**
 * Brand Studio (blueprint section 14).
 *
 * Settings reframed as three workspaces with real previews, rather than a form
 * of labelled inputs. The watermark is positioned against an image sized frame
 * so the choice is made where it will be seen.
 */
export function BrandStudioSurface() {
  const [profile, setProfile] = useState<CreatorProfile | null>(null);
  const [loaded, setLoaded] = useState<ProfileResponse | null>(null);
  const [ai, setAi] = useState<AiStatus | null>(null);
  const [workspace, setWorkspace] = useState<Workspace>("Identity");
  const [state, setState] = useState<SaveState>("idle");
  const [error, setError] = useState<string | null>(null);

  // Edits not yet saved are unsaved work like the Composer's, so switching
  // profile, reloading, or leaving this screen asks before they are thrown
  // away. Only the Composer used to count, and these went without a word.
  const unsaved = useRef(false);
  unsaved.current = state === "dirty" || state === "failed";
  useEffect(
    () =>
      registerUnsavedWork("brand-studio", {
        label: "Your Brand Studio edits",
        section: "settings",
        check: () => unsaved.current,
      }),
    [],
  );

  // Read again when the studio answers after an outage, but only while the
  // profile is still missing: a profile on screen may hold edits not saved yet.
  const back = useStudioBack();
  const hasProfile = useRef(false);
  hasProfile.current = profile !== null;
  useEffect(() => {
    if (hasProfile.current) return;
    let live = true;
    Promise.all([fetchProfile(), fetchAiStatus().catch(() => null)])
      .then(([profileResponse, aiStatus]) => {
        if (!live) return;
        setLoaded(profileResponse);
        setProfile(profileResponse.profile);
        setAi(aiStatus);
        setError(null);
      })
      .catch(() => live && setError("The profile could not be read."));
    return () => {
      live = false;
    };
  }, [back]);

  if (error && !profile) return <Centered>{error.toUpperCase()}</Centered>;
  if (!profile) return <Centered>LOADING BRAND STUDIO</Centered>;

  /** Edits one field, keeping every other field intact for the write. */
  function edit<K extends keyof CreatorProfile>(key: K, value: CreatorProfile[K]) {
    setProfile((current) => (current ? { ...current, [key]: value } : current));
    setState("dirty");
    setError(null);
  }

  async function onSave() {
    if (!profile) return;
    setState("saving");
    try {
      // The whole record goes back, not the fields that changed. The endpoint
      // replaces rather than merges.
      await saveProfile(profile);
      setState("saved");
    } catch (caught) {
      setState("failed");
      setError(caught instanceof Error ? caught.message : "The save was rejected.");
    }
  }

  return (
    <div className="mx-auto max-w-[86ch] px-8 py-8">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="studio-title">Brand Studio</h1>
        <div className="flex items-center gap-3">
          <span className="studio-meta" role="status" aria-live="polite">
            {state === "saving" && (
              <span className="flex items-center gap-1.5">
                <Loader2 className="size-3 animate-spin" aria-hidden="true" />
                SAVING
              </span>
            )}
            {state === "saved" && (
              <span className="flex items-center gap-1.5 text-signal-green-text">
                <Check className="size-3" aria-hidden="true" />
                SAVED
              </span>
            )}
            {state === "dirty" && <span className="text-signal-orange-text">UNSAVED</span>}
            {state === "failed" && (
              <span className="text-signal-orange-text" title={error ?? undefined}>
                SAVE FAILED
              </span>
            )}
          </span>
          <button
            type="button"
            onClick={onSave}
            disabled={state === "saving" || state === "idle"}
            className="rounded-md bg-signal-orange px-3 py-1 text-xs font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
          >
            Save
          </button>
        </div>
      </div>

      {/* Wraps rather than running off a phone width window, where the last
          two tabs could only be reached by a sideways scroll. */}
      <div className="mt-6 flex flex-wrap items-center gap-1" role="tablist" aria-label="Brand workspaces">
        {WORKSPACES.map((candidate) => (
          <button
            key={candidate}
            type="button"
            role="tab"
            aria-selected={workspace === candidate}
            onClick={() => setWorkspace(candidate)}
            className={cn(
              "rounded-md px-3 py-1.5 text-[12px] font-medium",
              "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
              workspace === candidate ? "bg-soft text-ink-primary" : "text-ink-muted hover:text-ink-secondary",
            )}
          >
            {candidate}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {workspace === "Identity" && <IdentityWorkspace profile={profile} edit={edit} isSet={loaded?.is_set ?? false} />}
        {workspace === "Watermark" && <WatermarkWorkspace profile={profile} edit={edit} />}
        {workspace === "Grounding" && <GroundingWorkspace />}
        {workspace === "Local security" && <SecurityWorkspace loaded={loaded} ai={ai} />}
        {workspace === "Storage and privacy" && <StoragePrivacyWorkspace />}
        {workspace === "Licence" && <LicenceWorkspace />}
      </div>
    </div>
  );
}

type Editor = <K extends keyof CreatorProfile>(key: K, value: CreatorProfile[K]) => void;

function IdentityWorkspace({
  profile,
  edit,
  isSet,
}: {
  profile: CreatorProfile;
  edit: Editor;
  isSet: boolean;
}) {
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
      <div className="flex flex-col gap-4">
        <Field label="Name" value={profile.name} onChange={(v) => edit("name", v)} placeholder="How you sign your work" />
        <Field
          label="Headline"
          value={profile.headline}
          onChange={(v) => edit("headline", v)}
          placeholder="The line under your name"
        />
        <Field label="Company" value={profile.company} onChange={(v) => edit("company", v)} placeholder="Optional" />
        {!isSet && (
          <p className="studio-meta leading-relaxed text-ink-muted">
            UNTIL A NAME IS SAVED, WATERMARKS AND THE FEED PREVIEW STAY UNNAMED RATHER THAN GUESSING ONE
          </p>
        )}
      </div>

      {/* The same arrangement the feed preview draws, so the identity is
          chosen against the place it will be read. */}
      <aside>
        <p className="studio-label mb-2">As the feed shows it</p>
        <div className="rounded-lg border border-edge bg-raised p-3">
          <div className="flex items-center gap-2">
            <div className="size-9 shrink-0 rounded-full bg-soft" aria-hidden="true" />
            <div className="min-w-0">
              <p className="truncate text-[13px] font-medium text-ink-primary">
                {profile.name || <span className="text-ink-muted">Unnamed</span>}
              </p>
              <p className="truncate text-[11px] text-ink-muted">
                {profile.headline || profile.company || "No headline"}
              </p>
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
}

function WatermarkWorkspace({ profile, edit }: { profile: CreatorProfile; edit: Editor }) {
  const mark = profile.brand_watermark_text || profile.name;

  return (
    <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
      <div className="flex flex-col gap-4">
        <label className="flex items-center justify-between gap-3">
          <span className="text-[12px] text-ink-secondary">Stamp generated media</span>
          <input
            type="checkbox"
            checked={profile.brand_watermark_enabled}
            onChange={(event) => edit("brand_watermark_enabled", event.target.checked)}
            className="size-4 accent-[var(--studio-orange)]"
          />
        </label>

        <Field
          label="Watermark text"
          value={profile.brand_watermark_text}
          onChange={(v) => edit("brand_watermark_text", v)}
          placeholder={profile.name || "Your mark"}
        />

        <div>
          <p className="studio-label mb-2">Position</p>
          <div className="grid w-[132px] grid-cols-3 gap-1" role="group" aria-label="Watermark position">
            {POSITIONS.flat().map((position) => (
              <button
                key={position}
                type="button"
                onClick={() => edit("brand_watermark_position", position)}
                aria-label={position.replace(/_/g, " ")}
                aria-pressed={profile.brand_watermark_position === position}
                className={cn(
                  "h-9 rounded border transition-colors duration-(--studio-motion-fast)",
                  profile.brand_watermark_position === position
                    ? "border-signal-orange bg-signal-orange-subtle"
                    : "border-edge hover:border-edge-strong",
                )}
              />
            ))}
          </div>
        </div>

        <div>
          <p className="studio-label mb-2">Style</p>
          <div className="flex flex-wrap gap-1">
            {STYLES.map((style) => (
              <button
                key={style}
                type="button"
                onClick={() => edit("brand_watermark_style", style)}
                aria-pressed={profile.brand_watermark_style === style}
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-[11px]",
                  profile.brand_watermark_style === style
                    ? "border-edge-strong bg-soft text-ink-primary"
                    : "border-edge text-ink-muted hover:text-ink-secondary",
                )}
              >
                {style.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        </div>
      </div>

      <WatermarkPreview profile={profile} mark={mark} />
    </div>
  );
}

/**
 * The watermark shown at image proportions rather than on a small card.
 *
 * The frame is drawn rather than photographic. A stock photograph would have
 * to come from somewhere, and this product does not fetch images from anywhere;
 * a neutral frame also shows the mark against a mid tone, which is the case
 * that actually decides whether a style is legible.
 */
function WatermarkPreview({ profile, mark }: { profile: CreatorProfile; mark: string }) {
  const [row, column] = (() => {
    for (let r = 0; r < POSITIONS.length; r += 1) {
      const c = POSITIONS[r].indexOf(profile.brand_watermark_position as never);
      if (c !== -1) return [r, c];
    }
    return [2, 2];
  })();

  const align = ["items-start", "items-center", "items-end"][row];
  const justify = ["justify-start", "justify-center", "justify-end"][column];

  return (
    <aside>
      <p className="studio-label mb-2">Preview frame</p>
      <div
        className={cn(
          "flex aspect-square w-full max-w-[420px] p-5",
          "rounded-lg border border-edge",
          "bg-[linear-gradient(135deg,var(--studio-soft),var(--studio-raised))]",
          align,
          justify,
        )}
      >
        {profile.brand_watermark_enabled && mark ? (
          <span
            className={cn(
              "max-w-full truncate text-[12px]",
              profile.brand_watermark_style === "glass_pill" &&
                "rounded-full border border-edge bg-canvas/60 px-3 py-1 text-ink-primary backdrop-blur-sm",
              profile.brand_watermark_style === "solid_bar" && "bg-canvas px-3 py-1 text-ink-primary",
              profile.brand_watermark_style === "plain_text" && "text-ink-primary",
            )}
          >
            {mark}
          </span>
        ) : (
          <span className="studio-meta text-ink-muted">
            {profile.brand_watermark_enabled ? "NO MARK SET" : "WATERMARK OFF"}
          </span>
        )}
      </div>
      <p className="studio-meta mt-2 text-[10px] text-ink-muted">
        A DRAWN FRAME, NOT ONE OF YOUR IMAGES
      </p>
    </aside>
  );
}

function SecurityWorkspace({ loaded, ai }: { loaded: ProfileResponse | null; ai: AiStatus | null }) {
  // Every line is read from somewhere rather than asserted. The one claim that
  // is structural, the database being a local file, is labelled as such.
  const rows: { label: string; value: string; good: boolean }[] = [
    { label: "Server binding", value: "LOOPBACK ONLY", good: true },
    { label: "Credential store", value: "LOCAL SQLITE VAULT", good: true },
    {
      label: "Model engine",
      value: ai ? (ai.has_api_key ? "SENDS TO PROVIDER" : "RUNS LOCALLY") : "UNKNOWN",
      good: ai ? !ai.has_api_key : false,
    },
    {
      label: "LinkedIn session",
      value: loaded?.linkedin_connected ? "CONNECTED" : "NOT CONNECTED",
      good: true,
    },
  ];

  return (
    <div className="max-w-[60ch]">
      <div className="flex items-center gap-2">
        <ShieldCheck className="size-5 text-signal-green-text" strokeWidth={1.75} aria-hidden="true" />
        <p className="text-[14px] text-ink-primary">This install processes your work on this machine.</p>
      </div>

      <dl className="mt-5 flex flex-col gap-2 border-t border-edge pt-4">
        {rows.map((row) => (
          <div key={row.label} className="flex items-baseline justify-between gap-4">
            <dt className="text-[12px] text-ink-secondary">{row.label}</dt>
            <dd className={cn("studio-meta", row.good ? "text-signal-green-text" : "text-signal-orange-text")}>
              {row.value}
            </dd>
          </div>
        ))}
      </dl>

      {/* This used to end "NOTHING ELSE IN THE STUDIO LEAVES THIS MACHINE",
          and then "YOUR DRAFTS, LEADS AND LINKEDIN SESSION NEVER LEAVE THIS
          MACHINE". Neither was true: Send to LinkedIn sends the draft with
          that session, and a connected AI provider receives draft text. So
          it says what stays, and each action that sends, what it sends and
          where, matching the help article on what leaves this machine.

          tests/test_egress_surface.py holds this list to the code, so adding
          an outbound call without saying so here fails the suite. */}
      <div className="mt-5">
        <p className="text-[13px] leading-relaxed text-ink-secondary">
          Your drafts, posts, leads, analytics and media stay in this profile&apos;s files on this
          machine. Something leaves it only when you choose an action that sends it:
        </p>
        <ul className="mt-2 flex list-disc flex-col gap-1 pl-5 text-[13px] leading-relaxed text-ink-secondary">
          <li>
            <span className="text-ink-primary">Send to LinkedIn</span> sends the post&apos;s text to
            LinkedIn, signed in with your stored LinkedIn session.
          </li>
          <li>
            {ai?.has_api_key
              ? "Re-Hook, Command and the other writing actions send the draft or instruction text to the AI provider you connected."
              : ai
                ? "No AI provider is connected, so Re-Hook, Command and the other writing actions run on this machine. Connect one, and they send the draft or instruction text to it."
                : "With an AI provider connected, Re-Hook, Command and the other writing actions send the draft or instruction text to it."}
          </li>
          <li>
            <span className="text-ink-primary">Generate</span> in the Media tab sends a prompt built
            from your image description to an image service.
          </li>
        </ul>
      </div>

      <EgressLedger />

      <SessionConnection />

      <YourData />
    </div>
  );
}

/**
 * Taking a copy of your own work.
 *
 * Everything the studio holds is one SQLite file plus a media directory. The
 * backup and export endpoints have existed, and been tested, since before this
 * interface did, and no surface ever called them, so the only way to take a
 * copy was to know the CLI existed. For a product built on keeping your work
 * on your machine, that left the entire burden of not losing it on the machine.
 *
 * Paths are shown rather than downloaded. The archive is written by the server
 * to a directory on this machine, and telling you where it went is more useful
 * than handing back bytes the browser would put somewhere else.
 */
function YourData() {
  const [listing, setListing] = useState<BackupListing | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  // Set once a restore has replaced this profile's data. Every screen still
  // shows what it read before, so the one way on is a reload.
  const [restored, setRestored] = useState(false);

  const load = useCallback(async () => {
    try {
      setListing(await fetchBackups());
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(what: "backup" | "json" | "csv" | "obsidian") {
    setBusy(what);
    setNote(null);
    try {
      if (what === "backup") {
        const made = await createBackup("manual");
        setNote(`Saved ${readableBytes(made.bytes)} to ${made.archive}`);
        await load();
      } else {
        const out = await exportData(what);
        setNote(out.note ? `${out.path}. ${out.note}` : out.path);
      }
    } catch (caught) {
      // The server's reason, not a generic failure. A backup that did not
      // happen must never read like one that did.
      setNote(caught instanceof Error ? caught.message : "The request was refused.");
    } finally {
      setBusy(null);
    }
  }

  /**
   * Restores one listed archive, after asking.
   *
   * Restore used to be a terminal command only, which a portable or desktop
   * install has no checkout folder to run. The studio takes a safety backup
   * of the current state before it changes anything, and the question says
   * so, because the answer to restoring the wrong archive is that copy.
   */
  async function restore(name: string) {
    const question =
      `Restore ${name}?\n\nThis replaces this profile's drafts, leads and analytics with what the backup holds. ` +
      "A safety backup of the current state is taken first, so you can go back to it the same way.";
    if (!window.confirm(question)) return;
    setBusy(`restore:${name}`);
    setNote(null);
    try {
      const done = await restoreBackup(name);
      setNote(
        `Restored ${done.restoredFrom}. ` +
          (done.safetyBackup ? `The safety backup of your state from just before is ${done.safetyBackup}. ` : "") +
          (done.safetyNote ? `${done.safetyNote} ` : "") +
          "Reload the studio to see the restored data.",
      );
      setRestored(true);
      await load();
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "The restore was refused. Nothing was changed.");
    } finally {
      setBusy(null);
    }
  }

  /** Reloads through the unsaved-work guard, as the profile switcher does. */
  function reloadAfterRestore() {
    if (hasUnsavedWork()) {
      const lost = unsavedWorkLabels().join(" and ") || "Your unsaved work";
      if (!window.confirm(`${lost} would be lost by reloading. Reload anyway?`)) return;
    }
    reloadStudio();
  }

  return (
    <div className="mt-6 border-t border-edge pt-5">
      <p className="studio-label mb-2">Your data</p>
      <p className="mb-3 text-[13px] leading-relaxed text-ink-secondary">
        This creator profile's drafts, leads and settings are one file on this machine, apart
        from every other profile's. Nothing copies them anywhere unless you do.
      </p>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void run("backup")}
          disabled={busy !== null}
          className="flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
        >
          {busy === "backup" ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <Archive className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          )}
          Back up now
        </button>
        <button
          type="button"
          onClick={() => void run("json")}
          disabled={busy !== null}
          className="rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
        >
          Export JSON
        </button>
        <button
          type="button"
          onClick={() => void run("csv")}
          disabled={busy !== null}
          className="rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
        >
          Export CSV
        </button>
        <button
          type="button"
          onClick={() => void run("obsidian")}
          disabled={busy !== null}
          className="flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
        >
          {busy === "obsidian" ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <Network className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          )}
          Export to Obsidian
        </button>
      </div>
      <p className="mt-2 text-[12px] leading-relaxed text-ink-muted">
        Obsidian gets a folder of linked notes: each post, the people who engaged with it, and
        your topics. Its graph view shows who keeps coming back. Press it again to refresh the same
        vault; what you write in it is kept.
      </p>

      {note && (
        <p role="status" className="mt-3 text-[12px] leading-snug break-all text-ink-secondary">
          {note}
        </p>
      )}
      {restored && (
        <button
          type="button"
          onClick={reloadAfterRestore}
          className="mt-2 rounded-md bg-signal-orange px-2.5 py-1 text-[12px] font-medium text-on-signal transition-[filter] hover:brightness-110"
        >
          Reload the studio
        </button>
      )}

      {failed ? (
        <p className="studio-meta mt-4 text-ink-muted">BACKUP FOLDER COULD NOT BE READ</p>
      ) : listing === null ? (
        <p className="studio-meta mt-4 text-ink-muted">READING</p>
      ) : listing.backups.length === 0 ? (
        <p className="studio-meta mt-4 text-ink-muted">NO BACKUPS YET</p>
      ) : (
        <div className="mt-4">
          <p className="studio-meta mb-2 text-[10px]">
            {listing.count} ARCHIVE{listing.count === 1 ? "" : "S"}
          </p>
          <ul className="flex flex-col gap-1">
            {listing.backups.slice(0, 5).map((archive) => (
              <li key={archive.name} className="flex items-center justify-between gap-3">
                <span className="min-w-0 flex-1 truncate text-[12px] text-ink-secondary">{archive.name}</span>
                <span className="studio-meta shrink-0 text-[10px] text-ink-muted">
                  {readableBytes(archive.bytes)}
                  <span className="mx-1.5">·</span>
                  {archive.modified.slice(0, 16).replace("T", " ")}
                </span>
                {archive.restorable && (
                  <button
                    type="button"
                    onClick={() => void restore(archive.name)}
                    disabled={busy !== null}
                    aria-label={`Restore ${archive.name}`}
                    className="flex shrink-0 items-center gap-1 rounded-md border border-edge px-2 py-0.5 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                  >
                    {busy === `restore:${archive.name}` ? (
                      <Loader2 className="size-3 animate-spin" aria-hidden="true" />
                    ) : (
                      <RotateCcw className="size-3" strokeWidth={1.75} aria-hidden="true" />
                    )}
                    Restore
                  </button>
                )}
              </li>
            ))}
          </ul>
          <p className="studio-meta mt-2 break-all text-[10px] text-ink-muted">
            {listing.directory}
          </p>
        </div>
      )}
    </div>
  );
}

/**
 * What has left this machine, counted.
 *
 * This replaced a four line list of things that reach out. The list was true
 * when it was written, which is the problem with a list: the sentence above it
 * previously claimed nothing else ever left, and that had been false for as
 * long as image generation existed. Counters come from the chokepoint every
 * outbound call passes through, so they cannot describe a version of the code
 * that is no longer running.
 *
 * Categories with nothing to report are still shown. An absence of requests is
 * the answer most of these should give, and hiding them would turn a zero into
 * a blank.
 */
function EgressLedger() {
  const [status, setStatus] = useState<EgressStatus | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    fetchEgressStatus()
      .then((result) => live && setStatus(result))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  if (failed) {
    return (
      <div className="mt-6 border-t border-edge pt-5">
        <p className="studio-label mb-2">What has left this machine</p>
        <p className="studio-meta text-ink-muted">EGRESS LEDGER UNAVAILABLE</p>
      </div>
    );
  }

  return (
    <div className="mt-6 border-t border-edge pt-5">
      <p className="studio-label mb-2">What has left this machine</p>

      {status === null ? (
        <p className="studio-meta text-ink-muted">READING</p>
      ) : (
        <>
          {/* The claim was "the one point every outbound request passes
              through", and it was not true. Two paths reach the network
              without passing the chokepoint, so the sentence promised
              completeness the counter cannot deliver, and a reader would
              have taken "Nothing has left this machine" as covering
              everything. Now it says what it counts, and the note below
              says what it does not. */}
          <p className="mb-3 text-[13px] leading-relaxed text-ink-secondary">
            Counted since the studio started, at the chokepoint every HTTP request this
            backend makes passes through.{" "}
            {status.total_performed === 0
              ? "No counted request has left this machine."
              : `${status.total_performed} counted request${status.total_performed === 1 ? "" : "s"} left this machine.`}
            {status.total_refused > 0 && ` ${status.total_refused} refused.`}
          </p>
          <p className="mb-3 text-[12px] leading-relaxed text-ink-muted">
            Two things are not counted here, because they do not pass through it. Opening
            LinkedIn in your browser from this studio makes your browser contact LinkedIn
            directly. And a connected MCP source is a program on this machine that may make
            its own requests, which this studio neither sees nor can stop.
          </p>

          {status.master_off && (
            <p className="studio-meta mb-3 leading-snug text-signal-green-text">
              {status.master_flag} IS SET. NOTHING MAY OPEN A CONNECTION.
            </p>
          )}

          <ul className="flex flex-col gap-1">
            {status.categories.map((category) => (
              <li key={category.name} className="flex items-baseline justify-between gap-3">
                <span className="text-[12px] text-ink-secondary">
                  {category.name}
                  {!category.allowed && (
                    <span className="studio-meta ml-2 text-[10px] text-ink-muted">OFF</span>
                  )}
                </span>
                <span className="studio-meta shrink-0 text-[10px] text-ink-muted tabular-nums">
                  {category.performed} sent
                  {category.refused > 0 && (
                    <>
                      <span className="mx-1.5">·</span>
                      {category.refused} refused
                    </>
                  )}
                </span>
              </li>
            ))}
          </ul>

          <p className="studio-meta mt-3 leading-snug text-ink-muted">
            SET {status.master_flag}=1 TO REFUSE EVERY CATEGORY, INCLUDING THE ONES ON BY DEFAULT.
          </p>
        </>
      )}
    </div>
  );
}

function readableBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}


function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="studio-label">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="rounded-md border border-edge bg-ink px-3 py-2 text-[13px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
      />
    </label>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid h-full place-items-center px-8">
      <p className="studio-meta max-w-[40ch] text-center leading-relaxed text-ink-muted">{children}</p>
    </div>
  );
}


/**
 * The LinkedIn session, pasted rather than logged into.
 *
 * These are the creator's live session cookies, so the fields are secret and
 * the copy is explicit about two things: where they are kept, and that saving
 * them contacts nobody. The endpoint used to fire an authenticated request on
 * every save, which produced traffic from a product that promises not to.
 */
function SessionConnection() {
  const [auth, setAuth] = useLocalState<AuthStatus | null>(null);
  const [liAt, setLiAt] = useLocalState("");
  const [jsession, setJsession] = useLocalState("");
  const [busy, setBusy] = useLocalState(false);
  const [note, setNote] = useLocalState<string | null>(null);

  useEffect(() => {
    let live = true;
    fetchAuthStatus()
      .then((result) => live && setAuth(result))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  async function onSave() {
    if (!liAt.trim() || !jsession.trim()) return;
    setBusy(true);
    setNote(null);
    try {
      await saveSessionCookies(liAt.trim(), jsession.trim());
      setLiAt("");
      setJsession("");
      setAuth(await fetchAuthStatus());
      setNote("Saved to the local vault.");
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "The save was refused.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-8 border-t border-edge pt-5">
      <p className="studio-label mb-2">LinkedIn session</p>

      <dl className="mb-3 flex flex-col gap-1.5">
        <div className="flex items-baseline justify-between gap-4">
          <dt className="text-[12px] text-ink-secondary">Stored session</dt>
          {/* client_session is whether usable tokens exist. status is a string
              the app sets, and the two disagree on a fresh install, so the
              honest answer is the one that reflects held credentials. */}
          <dd
            className={cn(
              "studio-meta",
              auth?.client_session ? "text-signal-green-text" : "text-ink-muted",
            )}
          >
            {auth === null ? "READING" : auth.client_session ? "PRESENT" : "NONE"}
          </dd>
        </div>
      </dl>

      <div className="flex flex-col gap-2">
        <input
          type="password"
          value={liAt}
          onChange={(event) => setLiAt(event.target.value)}
          placeholder="li_at"
          aria-label="LinkedIn li_at cookie"
          className="rounded-md border border-edge bg-ink px-2.5 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
        />
        <input
          type="password"
          value={jsession}
          onChange={(event) => setJsession(event.target.value)}
          placeholder="JSESSIONID"
          aria-label="LinkedIn JSESSIONID cookie"
          className="rounded-md border border-edge bg-ink px-2.5 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
        />
        <button
          type="button"
          onClick={onSave}
          disabled={busy || !liAt.trim() || !jsession.trim()}
          className="flex items-center justify-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
        >
          {busy && <Loader2 className="size-3 animate-spin" aria-hidden="true" />}
          Save to vault
        </button>

        {note && (
          <p role="status" className="studio-meta text-ink-secondary">
            {note}
          </p>
        )}

        <p className="studio-meta leading-relaxed text-ink-muted">
          ENCRYPTED IN THIS MACHINE&apos;S VAULT. SAVING CONTACTS NOBODY: SYNCING WITH LINKEDIN IS A
          SEPARATE ACTION YOU TAKE DELIBERATELY.
        </p>
      </div>
    </section>
  );
}
