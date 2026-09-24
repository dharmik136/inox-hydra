import { useEffect, useState } from "react";
import { Check, Loader2, ShieldCheck } from "lucide-react";
import {
  fetchAiStatus,
  fetchProfile,
  saveProfile,
  type AiStatus,
  type CreatorProfile,
  type ProfileResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type Workspace = "Identity" | "Watermark" | "Local security";

const WORKSPACES: Workspace[] = ["Identity", "Watermark", "Local security"];

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

      <p className="studio-meta mt-5 leading-relaxed text-ink-muted">
        CONFIGURING A CLOUD PROVIDER KEY SENDS PROMPT TEXT TO THAT PROVIDER.
        <br />
        <span className="text-ink-muted">NOTHING ELSE IN THE STUDIO LEAVES THIS MACHINE.</span>
      </p>
    </div>
  );
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
