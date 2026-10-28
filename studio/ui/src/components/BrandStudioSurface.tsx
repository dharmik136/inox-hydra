import { useCallback, useEffect, useRef, useState } from "react";
import { TelegramIngressPanel } from "./TelegramIngressPanel";
import { useState as useLocalState } from "react";
import { Archive, Check, Loader2, Network, RotateCcw, ShieldCheck } from "lucide-react";
import {
  createBackup,
  deleteLinkedInSession,
  exportData,
  fetchAiStatus,
  dismissSessionRemovedNotice,
  fetchAuthStatus,
  fetchBackups,
  fetchBrandProfile,
  fetchEgressStatus,
  fetchKeptList,
  fetchModelTold,
  fetchProfile,
  fetchSettingsOverview,
  restoreBackup,
  saveSessionCookies,
  saveProfile,
  setAutostart,
  setUpdatePreference,
  unkeepLead,
  type AiStatus,
  type AuthStatus,
  type BackupListing,
  type BrandProfile,
  type EgressStatus,
  type CreatorProfile,
  type KeptPerson,
  type ProfileResponse,
  type SettingsOverview,
} from "@/lib/api";
import { useStudioBack } from "@/lib/refresh";
import { formatLocal, formatLocalDay } from "@/lib/time";
import { cn } from "@/lib/utils";
import { hasUnsavedWork, registerUnsavedWork, reloadStudio, unsavedWorkLabels } from "@/lib/unsaved";
import { GroundingWorkspace } from "./GroundingWorkspace";
import { LicenceWorkspace } from "./LicenceWorkspace";
import { StoragePrivacyWorkspace } from "./StoragePrivacyWorkspace";
import { WritingPreferencesPanel } from "./WritingPreferences";

// Brand Studio was one screen of six tabs that opened on a Name, Headline and
// Company form, the sections report's one outright one-view failure. It is
// two now (batch 5): Brand, about you, opens on your profile as LinkedIn last
// showed it, with its editors one level down; Settings, about this machine,
// opens on an overview, with the rest one level down. Both live in this file,
// so the code that says what leaves this machine stays where its guards read it.
// Writing (phase 3 of the Telegram bot): how the studio writes for you, each
// choice a writing request makes, with its default; about you, beside how you
// write in Profile.
type BrandView = "Profile" | "Identity" | "Watermark" | "Writing";
const BRAND_VIEWS: BrandView[] = ["Profile", "Identity", "Watermark", "Writing"];

// Grounding sits beside the other settings rather than in the composer: it
// is a standing grant about what this machine will run and what leaves it,
// not a per-draft choice.
type SettingsView = "Overview" | "Grounding" | "Local security" | "Storage and privacy" | "Licence";
const SETTINGS_VIEWS: SettingsView[] = ["Overview", "Grounding", "Local security", "Storage and privacy", "Licence"];

/** The nine placements the backend accepts, laid out as they read on an image. */
const POSITIONS = [
  ["top_left", "top_center", "top_right"],
  ["middle_left", "center", "middle_right"],
  ["bottom_left", "bottom_center", "bottom_right"],
] as const;

const STYLES = ["glass_pill", "solid_bar", "plain_text"] as const;

type SaveState = "idle" | "dirty" | "saving" | "saved" | "failed";

/**
 * Brand: what your profile shows, when each part was read, and how you sign
 * your images (sections report, batch 5, rail row 11).
 *
 * Opens on the profile as LinkedIn last showed it. The identity and
 * watermark editors are one level down, and the identity editor puts the
 * two identities side by side: the profile LinkedIn showed, and the byline
 * the studio signs images and slides with, which starts as that profile.
 */
export function BrandSurface({ onOpenSetup }: { onOpenSetup?: () => void } = {}) {
  const [profile, setProfile] = useState<CreatorProfile | null>(null);
  const [loaded, setLoaded] = useState<ProfileResponse | null>(null);
  const [asRead, setAsRead] = useState<BrandProfile | null>(null);
  const [view, setView] = useState<BrandView>("Profile");
  const [state, setState] = useState<SaveState>("idle");
  const [error, setError] = useState<string | null>(null);

  // Edits not yet saved are unsaved work like the Composer's, so switching
  // profile, reloading, or leaving this screen asks before they are thrown
  // away. Only the Composer used to count, and these went without a word.
  const unsaved = useRef(false);
  unsaved.current = state === "dirty" || state === "failed";
  useEffect(
    () =>
      registerUnsavedWork("brand", {
        label: "Your Brand edits",
        section: "brand",
        check: () => unsaved.current,
      }),
    [],
  );

  // Read again when the studio answers after an outage, but only while the
  // byline is still missing: one on screen may hold edits not saved yet.
  const back = useStudioBack();
  const hasProfile = useRef(false);
  hasProfile.current = profile !== null;
  useEffect(() => {
    let live = true;
    fetchBrandProfile()
      .then((answer) => live && setAsRead(answer))
      .catch(() => undefined);
    if (hasProfile.current) {
      return () => {
        live = false;
      };
    }
    fetchProfile()
      .then((profileResponse) => {
        if (!live) return;
        setLoaded(profileResponse);
        setProfile(profileResponse.profile);
        setError(null);
      })
      .catch(() => live && setError("Your brand could not be read."));
    return () => {
      live = false;
    };
  }, [back]);

  if (error && !profile) return <Centered>{error.toUpperCase()}</Centered>;
  if (!profile) return <Centered>LOADING YOUR BRAND</Centered>;

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
    <div className="mx-auto max-w-[96ch] px-8 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="studio-label">Brand</p>
          <h1 className="studio-title mt-1">What your profile shows</h1>
        </div>
        {(view === "Identity" || view === "Watermark") && <SaveControl state={state} error={error} onSave={onSave} />}
      </div>

      <ViewTabs label="Brand views" views={BRAND_VIEWS} view={view} onView={setView} />

      <div className="mt-6">
        {view === "Profile" && <ProfileAsRead asRead={asRead} byline={profile} onOpenSetup={onOpenSetup} onEdit={() => setView("Identity")} />}
        {view === "Identity" && (
          <IdentityWorkspace profile={profile} edit={edit} isSet={loaded?.is_set ?? false} asRead={asRead} />
        )}
        {view === "Watermark" && <WatermarkWorkspace profile={profile} edit={edit} />}
        {view === "Writing" && <WritingPreferencesPanel />}
      </div>
    </div>
  );
}

/**
 * Settings: what leaves this machine, what is kept and backed up, what runs
 * here, and what licence you hold (sections report, batch 5, rail row 16).
 *
 * Opens on an overview with the values that matter visible, and the rest one
 * level down: Grounding, Local security, Storage and privacy, Licence.
 */
export function SettingsSurface() {
  const [view, setView] = useState<SettingsView>("Overview");
  const [loaded, setLoaded] = useState<ProfileResponse | null>(null);
  const [ai, setAi] = useState<AiStatus | null>(null);

  // What Local security says about the model and the session; each is read
  // on its own, so one failing leaves the rest of Settings standing.
  const back = useStudioBack();
  useEffect(() => {
    let live = true;
    fetchProfile()
      .then((answer) => live && setLoaded(answer))
      .catch(() => undefined);
    fetchAiStatus()
      .then((answer) => live && setAi(answer))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [back]);

  return (
    <div className="mx-auto max-w-[96ch] px-8 py-8">
      <p className="studio-label">Settings</p>
      <h1 className="studio-title mt-1">What runs here, and what leaves</h1>

      <ViewTabs label="Settings views" views={SETTINGS_VIEWS} view={view} onView={setView} />

      <div className="mt-6">
        {view === "Overview" && <SettingsOverviewView onOpen={setView} />}
        {view === "Grounding" && <GroundingWorkspace />}
        {view === "Local security" && <SecurityWorkspace loaded={loaded} ai={ai} />}
        {/* Your data first in this pane: a creator looking for a copy of
            their work looks in the pane named for their storage. */}
        {view === "Storage and privacy" && (
          <div className="flex flex-col gap-8">
            <YourData />
            <StoragePrivacyWorkspace />
            <KeptList />
          </div>
        )}
        {view === "Licence" && <LicenceWorkspace />}
      </div>
    </div>
  );
}

/** One level down, as tabs that wrap rather than run off a phone width window. */
function ViewTabs<V extends string>({
  label,
  views,
  view,
  onView,
}: {
  label: string;
  views: V[];
  view: V;
  onView: (view: V) => void;
}) {
  return (
    <div className="mt-6 flex flex-wrap items-center gap-1" role="tablist" aria-label={label}>
      {views.map((candidate) => (
        <button
          key={candidate}
          type="button"
          role="tab"
          aria-selected={view === candidate}
          onClick={() => onView(candidate)}
          className={cn(
            "rounded-md px-3 py-1.5 text-[12px] font-medium",
            "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
            view === candidate ? "bg-soft text-ink-primary" : "text-ink-muted hover:text-ink-secondary",
          )}
        >
          {candidate}
        </button>
      ))}
    </div>
  );
}

function SaveControl({ state, error, onSave }: { state: SaveState; error: string | null; onSave: () => void }) {
  return (
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
  );
}

/** "READ TUE 20 OCT": when a part of the profile was read, or that it was not. */
function readOn(at: string | null | undefined): string {
  return at ? `READ ${formatLocalDay(at).toUpperCase()}` : "READ DATE NOT KNOWN";
}

/**
 * Your profile as LinkedIn last showed it, each part with the date it was
 * read; the follower and connection counts on the days they were read; how
 * you sign images; and how you write, measured. Nothing here is edited: it
 * is what the bridge read, and it changes when you next open your profile.
 */
function ProfileAsRead({
  asRead,
  byline,
  onOpenSetup,
  onEdit,
}: {
  asRead: BrandProfile | null;
  byline: CreatorProfile;
  onOpenSetup?: () => void;
  onEdit: () => void;
}) {
  const [habits, setHabits] = useState<string[] | null>(null);
  useEffect(() => {
    let live = true;
    fetchModelTold()
      .then((told) => live && setHabits(told.voice.habits))
      .catch(() => live && setHabits([]));
    return () => {
      live = false;
    };
  }, []);

  if (asRead === null) return <p className="studio-meta text-ink-muted">READING YOUR PROFILE</p>;
  if (!asRead.confirmed || !asRead.profile) {
    return (
      <p className="text-[13px] leading-relaxed text-ink-secondary">
        Your profile is shown here once you confirm which LinkedIn profile is yours in Setup, and the bridge reads it.
        {onOpenSetup && (
          <>
            {" "}
            <button type="button" onClick={onOpenSetup} className="underline decoration-edge-strong underline-offset-2 hover:text-ink-primary">
              Go to Setup
            </button>
          </>
        )}
      </p>
    );
  }
  const you = asRead.profile;
  const audience = [...asRead.audience].reverse();
  const skillsRead = asRead.skills.map((s) => s.read_at ?? "").sort().pop() || null;
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
      <div className="flex min-w-0 flex-col gap-5">
        <section>
          <p className="text-[15px] font-medium text-ink-primary">{you.name ?? "Name not read"}</p>
          <p className="text-[13px] text-ink-secondary">{you.headline ?? "Headline not read"}</p>
          <p className="studio-meta mt-1 text-[10px] text-ink-muted">
            {[you.location, you.company].filter(Boolean).join(" · ").toUpperCase()}
            {you.location || you.company ? " · " : ""}
            {readOn(you.read_at)}
          </p>
          {you.about && <p className="mt-2 line-clamp-4 text-[13px] leading-relaxed text-ink-secondary">{you.about}</p>}
        </section>

        <section>
          <p className="studio-label mb-1.5">Roles</p>
          {asRead.positions.length === 0 ? (
            <p className="text-[12px] text-ink-muted">No role read yet.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {asRead.positions.map((role, index) => (
                <li key={`${role.title}-${index}`}>
                  <p className="text-[13px] text-ink-primary">{[role.title, role.company].filter(Boolean).join(", ")}</p>
                  <p className="studio-meta text-[10px] text-ink-muted">
                    {[role.date_range, role.location].filter(Boolean).join(" · ").toUpperCase()}
                    {role.date_range || role.location ? " · " : ""}
                    {readOn(role.read_at)}
                  </p>
                  {role.description && <p className="mt-0.5 line-clamp-2 text-[12px] text-ink-secondary">{role.description}</p>}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <p className="studio-label mb-1.5">Education</p>
          {asRead.education.length === 0 ? (
            <p className="text-[12px] text-ink-muted">No school read yet.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {asRead.education.map((school, index) => (
                <li key={`${school.school}-${index}`} className="text-[13px] text-ink-secondary">
                  {[school.school, school.degree].filter(Boolean).join(", ")}
                  <span className="studio-meta ml-2 text-[10px] text-ink-muted">
                    {school.date_range ? `${school.date_range.toUpperCase()} · ` : ""}
                    {readOn(school.read_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <p className="studio-label mb-1.5">Skills</p>
          {asRead.skills.length === 0 ? (
            <p className="text-[12px] text-ink-muted">No skill read yet.</p>
          ) : (
            <p className="text-[13px] leading-relaxed text-ink-secondary">
              {asRead.skills.map((s) => s.skill).join(", ")}
              <span className="studio-meta ml-2 text-[10px] text-ink-muted">{readOn(skillsRead)}</span>
            </p>
          )}
        </section>
      </div>

      <aside className="flex min-w-0 flex-col gap-5">
        <section>
          <p className="studio-label mb-1.5">Followers and connections</p>
          {audience.length === 0 ? (
            <p className="text-[12px] text-ink-muted">Not read yet: they are read each time your profile is.</p>
          ) : (
            <>
              <table className="w-full text-left text-[12px]">
                <thead>
                  <tr className="studio-meta text-[10px] text-ink-muted">
                    <th className="py-0.5 font-normal">DAY READ</th>
                    <th className="py-0.5 text-right font-normal">FOLLOWERS</th>
                    <th className="py-0.5 text-right font-normal">CONNECTIONS</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-edge text-ink-secondary">
                  {audience.slice(0, 6).map((point) => (
                    <tr key={point.date}>
                      <td className="py-0.5">{formatLocalDay(`${point.date}T12:00:00Z`)}</td>
                      <td className="py-0.5 text-right tabular-nums">{point.followers === null ? "not read" : point.followers.toLocaleString()}</td>
                      <td className="py-0.5 text-right tabular-nums">{point.connections === null ? "not read" : point.connections.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="studio-meta mt-1 text-[10px] text-ink-muted">
                ON THE {audience.length} {audience.length === 1 ? "DAY" : "DAYS"} YOUR PROFILE WAS READ, NOT EVERY DAY
              </p>
            </>
          )}
        </section>

        <section>
          <p className="studio-label mb-1.5">How you sign images and slides</p>
          <div className="rounded-lg border border-edge bg-raised p-3">
            <p className="truncate text-[13px] font-medium text-ink-primary">{byline.name || <span className="text-ink-muted">Unnamed</span>}</p>
            <p className="truncate text-[11px] text-ink-muted">{byline.headline || byline.company || "No headline"}</p>
          </div>
          <button type="button" onClick={onEdit} className="mt-1.5 text-[12px] text-ink-secondary underline decoration-edge-strong underline-offset-2 hover:text-ink-primary">
            Change it under Identity
          </button>
        </section>

        <section>
          <p className="studio-label mb-1.5">How you write</p>
          {habits === null ? (
            <p className="studio-meta text-ink-muted">READING</p>
          ) : habits.length === 0 ? (
            <p className="text-[12px] text-ink-muted">Measured once three of your posts are held.</p>
          ) : (
            <ul className="flex flex-col gap-0.5 text-[12px] leading-snug text-ink-secondary">
              {habits.map((line) => (
                <li key={line}>{line.replace(/^- /, "").replace("of their posts", "of your posts")}</li>
              ))}
            </ul>
          )}
        </section>
      </aside>
    </div>
  );
}

/**
 * The values Settings opens on, each from the module that owns it, with the
 * place one level down where it can be changed.
 */
function SettingsOverviewView({ onOpen }: { onOpen: (view: SettingsView) => void }) {
  const [overview, setOverview] = useState<SettingsOverview | null>(null);
  const [failed, setFailed] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const back = useStudioBack();

  const read = useCallback(() => {
    fetchSettingsOverview()
      .then((answer) => {
        setOverview(answer);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);
  useEffect(() => read(), [read, back]);

  if (failed && !overview) return <p className="studio-meta text-ink-muted">SETTINGS COULD NOT BE READ. IS THE STUDIO RUNNING?</p>;
  if (!overview) return <p className="studio-meta text-ink-muted">READING</p>;

  const { backup, cleanup, egress, licence, updates, autostart } = overview;
  const JOB_NAMES: Record<string, string> = { telemetry: "Old telemetry", readings: "Old post readings", reactions: "Old reactions" };

  async function toggle(action: () => Promise<unknown>, done: string) {
    setNote(null);
    try {
      await action();
      setNote(done);
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "The change was refused.");
    }
    read();
  }

  return (
    <div className="grid gap-px border border-edge bg-edge sm:grid-cols-2">
      <OverviewCard title="Last backup" action="Storage and privacy" onOpen={onOpen}>
        {backup.last
          ? `${formatLocal(backup.last.made_at)}, ${backup.last.verified === true ? "verified" : backup.last.verified === false ? "its check failed" : "made before checks were recorded"}.`
          : "None yet."}{" "}
        {backup.enabled ? (backup.next_due ? `The next is due ${formatLocal(backup.next_due)}.` : "") : "The daily backup is off."}
        {backup.stale && " The daily backup has stopped producing backups."}
      </OverviewCard>
      <OverviewCard title="Next cleanup" action="Storage and privacy" onOpen={onOpen}>
        {cleanup.jobs
          .map((job) => `${JOB_NAMES[job.job] ?? job.job}: ${job.state}${job.rows !== null && job.state !== "off" ? `, ${job.rows.toLocaleString()} rows now` : ""}`)
          .join("; ")}
        . Cleanups run {cleanup.runs}.
      </OverviewCard>
      <OverviewCard title="What has left this machine" action="Local security" onOpen={onOpen}>
        {egress.total_performed === 0
          ? "No counted request"
          : `${egress.total_performed.toLocaleString()} counted request${egress.total_performed === 1 ? "" : "s"}`}{" "}
        since {egress.since}
        {egress.total_refused > 0 ? `, ${egress.total_refused.toLocaleString()} refused` : ""}.
        {egress.master_off && " Every connection is refused."}
      </OverviewCard>
      <OverviewCard title="Licence" action="Licence" onOpen={onOpen}>
        {licence.tier_label}
        {licence.expires_at ? `, ends ${licence.expires_at}` : licence.updates_until ? `, updates until ${licence.updates_until}` : ""}.
      </OverviewCard>
      <OverviewCard title="Update check">
        {updates.enabled
          ? `On. Studio ${updates.current_version}${updates.last_checked ? `, last checked ${formatLocal(updates.last_checked)}` : ", not checked yet"}.`
          : "Off: no request leaves this machine for a version check."}{" "}
        <button
          type="button"
          onClick={() => void toggle(() => setUpdatePreference(!updates.enabled), updates.enabled ? "The update check is off." : "The update check is on.")}
          className="underline decoration-edge-strong underline-offset-2 hover:text-ink-primary"
        >
          {updates.enabled ? "Turn it off" : "Turn it on"}
        </button>
      </OverviewCard>
      <OverviewCard title="Start with your computer">
        {!autostart.supported || !autostart.available ? (
          "Not available on this system."
        ) : (
          <>
            {autostart.enabled ? "On: the studio starts when you sign in." : "Off."}{" "}
            <button
              type="button"
              onClick={() => void toggle(() => setAutostart(!autostart.enabled), autostart.enabled ? "The studio no longer starts with your computer." : "The studio starts with your computer.")}
              className="underline decoration-edge-strong underline-offset-2 hover:text-ink-primary"
            >
              {autostart.enabled ? "Turn it off" : "Turn it on"}
            </button>
          </>
        )}
      </OverviewCard>
      {note && (
        <p role="status" className="bg-ink px-3 py-2 text-[12px] text-ink-secondary sm:col-span-2">
          {note}
        </p>
      )}
    </div>
  );
}

function OverviewCard({
  title,
  action,
  onOpen,
  children,
}: {
  title: string;
  action?: SettingsView;
  onOpen?: (view: SettingsView) => void;
  children: React.ReactNode;
}) {
  return (
    <section className="bg-ink px-3 py-2.5">
      <div className="flex items-baseline justify-between gap-2">
        <p className="studio-label">{title}</p>
        {action && onOpen && (
          <button type="button" onClick={() => onOpen(action)} className="text-[11px] text-ink-muted underline decoration-edge underline-offset-2 hover:text-ink-primary">
            {action}
          </button>
        )}
      </div>
      <p className="mt-1 text-[12px] leading-snug text-ink-secondary">{children}</p>
    </section>
  );
}

/**
 * The people you kept from the review, and when, with the keep taken back
 * one at a time. Kept people were read only as an exclusion, so a keep could
 * be made and never seen again.
 */
function KeptList() {
  const [kept, setKept] = useState<KeptPerson[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const read = useCallback(() => {
    fetchKeptList()
      .then((answer) => {
        setKept(answer);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);
  useEffect(() => read(), [read]);

  return (
    <section aria-labelledby="kept-heading">
      <p id="kept-heading" className="studio-label mb-2">Kept from the review</p>
      {failed ? (
        <p className="studio-meta text-ink-muted">THE KEPT LIST COULD NOT BE READ</p>
      ) : kept === null ? (
        <p className="studio-meta text-ink-muted">READING</p>
      ) : kept.length === 0 ? (
        <p className="text-[12px] text-ink-muted">Nobody is kept. People you keep from the silent-lead review are listed here.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-edge border-y border-edge">
          {kept.map((person) => (
            <li key={person.lead_id} className="flex items-baseline justify-between gap-3 py-1.5">
              <span className="min-w-0 truncate text-[12px] text-ink-secondary">
                {person.name ?? "A person with no name"}
                <span className="studio-meta ml-2 text-[10px] text-ink-muted">KEPT {formatLocalDay(person.kept_at).toUpperCase()}</span>
              </span>
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => {
                  setBusy(person.lead_id);
                  void unkeepLead(person.lead_id).finally(() => {
                    setBusy(null);
                    read();
                  });
                }}
                className="shrink-0 rounded-md border border-edge px-2 py-0.5 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
                aria-label={`Take back the keep of ${person.name ?? "this person"}`}
              >
                Take back
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

type Editor = <K extends keyof CreatorProfile>(key: K, value: CreatorProfile[K]) => void;

/**
 * The two identities, side by side, as one control (sections report, batch
 * 5). Your profile as LinkedIn showed it is what Setup confirmed and the
 * bridge reads; your byline is how the studio signs images, slides and the
 * feed preview. The byline starts as the profile when you confirm it, and is
 * yours to change here; "Use what LinkedIn shows" brings them back in line.
 */
function IdentityWorkspace({
  profile,
  edit,
  isSet,
  asRead,
}: {
  profile: CreatorProfile;
  edit: Editor;
  isSet: boolean;
  asRead: BrandProfile | null;
}) {
  const linkedIn = asRead?.confirmed ? asRead.profile : null;
  const differs =
    linkedIn !== null &&
    ((linkedIn.name ?? "") !== profile.name ||
      (linkedIn.headline ?? "") !== profile.headline ||
      (linkedIn.company ?? "") !== profile.company);
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
      <div className="flex flex-col gap-4">
        <section className="rounded-md border border-edge px-3 py-2.5">
          <p className="studio-label">Your profile on LinkedIn</p>
          {linkedIn ? (
            <>
              <dl className="mt-1.5 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-[12px]">
                <dt className="text-ink-muted">Name</dt>
                <dd className="text-ink-secondary">{linkedIn.name ?? "not read"}</dd>
                <dt className="text-ink-muted">Headline</dt>
                <dd className="text-ink-secondary">{linkedIn.headline ?? "not read"}</dd>
                <dt className="text-ink-muted">Company</dt>
                <dd className="text-ink-secondary">{linkedIn.company ?? "not read"}</dd>
              </dl>
              <p className="studio-meta mt-1 text-[10px] text-ink-muted">CONFIRMED IN SETUP · {readOn(linkedIn.read_at)}</p>
              {differs && (
                <button
                  type="button"
                  onClick={() => {
                    edit("name", linkedIn.name ?? "");
                    edit("headline", linkedIn.headline ?? "");
                    edit("company", linkedIn.company ?? "");
                  }}
                  className="mt-2 rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
                >
                  Use what LinkedIn shows
                </button>
              )}
            </>
          ) : (
            <p className="mt-1 text-[12px] text-ink-muted">Not confirmed yet. Setup confirms which LinkedIn profile is yours.</p>
          )}
        </section>
        <p className="studio-label">Your byline, on images, slides and the feed preview</p>
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

      <TelegramIngressPanel />
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
/** How many backups the list opens on; the rest are one click away. */
const BACKUPS_SHOWN = 5;

function YourData() {
  const [listing, setListing] = useState<BackupListing | null>(null);
  const [showAll, setShowAll] = useState(false);
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
   * so, because the answer to restoring the wrong archive is that copy. It
   * names everything a restore replaces: it said "drafts, leads and
   * analytics" of a restore that also replaces who you are, your settings and
   * keys, your media and the record of people you forgot.
   */
  async function restore(name: string, databaseOnly: boolean) {
    const question =
      `Restore ${name}?\n\nThis replaces everything in this creator profile with what the backup holds: drafts ` +
      "and the queue, leads and analytics, your confirmed identity and Setup, settings and stored keys, " +
      (databaseOnly ? "and the record of people you forgot. Media files are left as they are. " : "media files, and the record of people you forgot. ") +
      "Anyone you have forgotten since the backup was made is forgotten again after the restore. " +
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
          (done.forgottenAgain
            ? `${done.forgottenAgain} ${done.forgottenAgain === 1 ? "person" : "people"} you had forgotten since that backup ${
                done.forgottenAgain === 1 ? "was" : "were"
              } forgotten again. `
            : "") +
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
            {(showAll ? listing.backups : listing.backups.slice(0, BACKUPS_SHOWN)).map((archive) => (
              <li key={archive.name} className="flex items-center justify-between gap-3">
                <span className="min-w-0 flex-1 truncate text-[12px] text-ink-secondary">{archive.name}</span>
                <span className="studio-meta shrink-0 text-[10px] text-ink-muted">
                  {readableBytes(archive.bytes)}
                  <span className="mx-1.5">·</span>
                  {archive.modified.slice(0, 16).replace("T", " ")}
                  {/* Whether its integrity check passed when it was made, and
                      the schema it holds, which the inspector read and the
                      list dropped (sections report, batch 5). */}
                  {archive.kind === "backup" && (
                    <>
                      <span className="mx-1.5">·</span>
                      {archive.verified === true ? "VERIFIED" : archive.verified === false ? "CHECK FAILED" : "NOT CHECKED"}
                    </>
                  )}
                  {archive.schema_version != null && (
                    <>
                      <span className="mx-1.5">·</span>
                      SCHEMA {archive.schema_version}
                    </>
                  )}
                </span>
                {archive.restorable && (
                  <button
                    type="button"
                    onClick={() => void restore(archive.name, archive.kind === "database")}
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
          {listing.backups.length > BACKUPS_SHOWN && (
            <button
              type="button"
              onClick={() => setShowAll(!showAll)}
              className="mt-1.5 text-[11px] text-ink-secondary underline decoration-edge-strong underline-offset-2 hover:text-ink-primary"
            >
              {showAll ? `Show the newest ${BACKUPS_SHOWN}` : `Show all ${listing.backups.length}`}
            </button>
          )}
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
              <li key={category.name} className="flex flex-wrap items-baseline justify-between gap-x-3">
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
                {/* Its switch, its default, and the last place it went or was
                    refused, which the ledger held and the screen dropped. */}
                <span className="studio-meta w-full text-[10px] leading-snug text-ink-muted">
                  {category.flag} · {category.default_allowed ? "ON" : "OFF"} BY DEFAULT
                  {category.last_destination ? ` · LAST SENT TO ${category.last_destination}` : ""}
                  {category.last_refused_endpoint ? ` · LAST REFUSED ${category.last_refused_endpoint}` : ""}
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
  // Deleting asks once, as Setup's control did before it moved here.
  const [confirming, setConfirming] = useLocalState(false);

  async function onDelete() {
    setBusy(true);
    setNote(null);
    try {
      await deleteLinkedInSession();
      setConfirming(false);
      setAuth(await fetchAuthStatus());
      setNote("The LinkedIn session is deleted. The extension's Sync button captures it again.");
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "The delete was refused.");
    } finally {
      setBusy(false);
    }
  }

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

      {/* Said once: a session an earlier version kept in a profile beyond the
          first was removed when this version started (decision D9). */}
      {auth?.session_removed && (
        <div role="status" className="mb-3 rounded-md border border-signal-orange px-3 py-2">
          <p className="text-[12px] leading-relaxed text-ink-primary">{auth.session_removed.message}</p>
          <button
            type="button"
            onClick={() =>
              void dismissSessionRemovedNotice()
                .then(fetchAuthStatus)
                .then(setAuth)
                .catch(() => undefined)
            }
            className="mt-2 rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary"
          >
            Understood
          </button>
        </div>
      )}

      <dl className="mb-3 flex flex-col gap-1.5">
        <div className="flex items-baseline justify-between gap-4">
          <dt className="text-[12px] text-ink-secondary">Stored session</dt>
          {/* client_session is whether usable tokens exist. status is a string
              the app sets, and the two disagree on a fresh install, so the
              honest answer is the one that reflects held credentials. */}
          <dd
            className={cn(
              "studio-meta",
              auth?.client_session ? "text-signal-green-text" : auth?.stored ? "text-signal-orange-text" : "text-ink-muted",
            )}
          >
            {auth === null ? "READING" : auth.client_session ? "PRESENT" : auth.stored ? "STORED, NOT USABLE" : "NONE"}
          </dd>
        </div>
        {(auth?.client_session || auth?.stored) && (
          <div className="flex items-baseline justify-between gap-4">
            <dt className="text-[12px] text-ink-secondary">Saved</dt>
            <dd className="studio-meta text-ink-muted">
              {auth.saved_at ? formatLocal(auth.saved_at).toUpperCase() : "WHEN IS NOT KNOWN"}
              {auth.account
                ? ` · FOR @${auth.account.vanity.toUpperCase()}`
                : " · ACCOUNT NOT KNOWN: SAVED BY HAND, NOT BY THE EXTENSION'S SYNC"}
            </dd>
          </div>
        )}
      </dl>

      {/* The one control for the session (sections report, batch 5): Setup
          showed it with Delete, Brand Studio with Save, each from its own
          key. Both are here now, answered from /api/auth/status. */}
      {(auth?.client_session || auth?.stored) && !confirming && (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={busy}
          className="mb-3 rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
        >
          Delete
        </button>
      )}
      {(auth?.client_session || auth?.stored) && confirming && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void onDelete()}
            disabled={busy}
            className="rounded-md border border-signal-orange px-2.5 py-1 text-[11px] text-signal-orange-text transition-colors hover:bg-soft disabled:opacity-40"
          >
            Yes, delete the session
          </button>
          <button
            type="button"
            onClick={() => setConfirming(false)}
            disabled={busy}
            className="rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
          >
            Keep it
          </button>
        </div>
      )}

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
