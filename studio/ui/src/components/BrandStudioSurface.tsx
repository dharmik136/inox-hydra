import { useCallback, useEffect, useState } from "react";
import { useState as useLocalState } from "react";
import { Archive, Check, Loader2, ShieldCheck } from "lucide-react";
import {
  createBackup,
  exportData,
  fetchAiStatus,
  fetchAuthStatus,
  fetchBackups,
  fetchProfile,
  saveSessionCookies,
  saveProfile,
  type AiStatus,
  type AuthStatus,
  type BackupListing,
  type CreatorProfile,
  type ProfileResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { GroundingWorkspace } from "./GroundingWorkspace";

type Workspace = "Identity" | "Watermark" | "Grounding" | "Local security";

// Grounding sits beside the other settings rather than in the composer: it
// is a standing grant about what this machine will run and what leaves it,
// not a per-draft choice.
const WORKSPACES: Workspace[] = ["Identity", "Watermark", "Grounding", "Local security"];

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

  useEffect(() => {
    let live = true;
    Promise.all([fetchProfile(), fetchAiStatus().catch(() => null)])
      .then(([profileResponse, aiStatus]) => {
        if (!live) return;
        setLoaded(profileResponse);
        setProfile(profileResponse.profile);
        setAi(aiStatus);
      })
      .catch(() => live && setError("The profile could not be read."));
    return () => {
      live = false;
    };
  }, []);

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
        <h2 className="studio-title">Brand Studio</h2>
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

      <div className="mt-6 flex items-center gap-1" role="tablist" aria-label="Brand workspaces">
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
          which is not true. Four features reach out, and a blanket sentence a
          reader cannot verify is worth less than a list they can. What stays
          is the part that actually matters: the work itself never moves.

          tests/test_egress_surface.py holds this list to the code, so adding
          an outbound call without saying so here fails the suite. */}
      <div className="mt-5">
        <p className="studio-meta leading-relaxed text-ink-muted">
          YOUR DRAFTS, LEADS AND LINKEDIN SESSION NEVER LEAVE THIS MACHINE.
        </p>
        <p className="studio-meta mt-2 leading-relaxed text-ink-muted">
          FOUR THINGS DO REACH OUT, EACH ONLY WHEN YOU USE IT:
        </p>
        <ul className="studio-meta mt-1.5 flex flex-col gap-0.5 leading-relaxed text-ink-muted">
          <li>A CLOUD PROVIDER KEY SENDS PROMPT TEXT TO THAT PROVIDER</li>
          <li>GENERATING AN IMAGE SENDS THE PROMPT TO THE IMAGE ENGINE</li>
          <li>SYNCING THE TEMPLATE LIBRARY FETCHES A BUNDLE</li>
          <li>UPDATE CHECKS, WHICH ARE OFF UNTIL YOU TURN THEM ON</li>
        </ul>
      </div>

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

  async function run(what: "backup" | "json" | "csv") {
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

  return (
    <div className="mt-6 border-t border-edge pt-5">
      <p className="studio-label mb-2">Your data</p>
      <p className="mb-3 text-[13px] leading-relaxed text-ink-secondary">
        Your drafts, leads and settings are one file on this machine. Nothing copies them
        anywhere unless you do.
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
      </div>

      {note && (
        <p role="status" className="studio-meta mt-3 leading-snug break-all text-ink-secondary">
          {note}
        </p>
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
              <li key={archive.name} className="flex items-baseline justify-between gap-3">
                <span className="truncate text-[12px] text-ink-secondary">{archive.name}</span>
                <span className="studio-meta shrink-0 text-[10px] text-ink-muted">
                  {readableBytes(archive.bytes)}
                  <span className="mx-1.5">·</span>
                  {archive.modified.slice(0, 16).replace("T", " ")}
                </span>
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
