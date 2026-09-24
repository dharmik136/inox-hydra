import { useEffect, useState } from "react";
import { fetchProfile, type ProfileResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * The brand inspector (blueprint section 10).
 *
 * Reports the identity and watermark this install will stamp on generated
 * media. It reads rather than edits: blueprint section 14 puts the controls in
 * Brand Studio, where a watermark can be positioned against a real image
 * canvas instead of a 380px strip.
 */
export function BrandPanel() {
  const [data, setData] = useState<ProfileResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    fetchProfile()
      .then((result) => live && setData(result))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  if (failed) return <p className="studio-meta pt-8 text-center text-ink-muted">PROFILE UNAVAILABLE</p>;
  if (!data) return <p className="studio-meta pt-8 text-center text-ink-muted">LOADING PROFILE</p>;

  const { profile, is_set: identitySet } = data;

  return (
    <div className="flex flex-col gap-5">
      <section>
        <p className="studio-label mb-2">Identity</p>
        {identitySet ? (
          <dl className="flex flex-col gap-1.5">
            <Row label="Name" value={profile.name} />
            <Row label="Headline" value={profile.headline} />
            <Row label="Company" value={profile.company} />
          </dl>
        ) : (
          /* is_set distinguishes "never configured" from "configured to an
             empty string". Only the first should read as unconfigured, and a
             fresh install is always in it. */
          <p className="studio-meta leading-relaxed text-ink-muted">
            THIS INSTALL HAS NO CREATOR IDENTITY YET
            <br />
            <span className="text-ink-muted">WATERMARKS AND THE FEED PREVIEW STAY UNNAMED UNTIL IT IS SET</span>
          </p>
        )}
      </section>

      <section>
        <p className="studio-label mb-2">Watermark</p>
        <dl className="flex flex-col gap-1.5">
          <Row
            label="State"
            value={profile.brand_watermark_enabled ? "ENABLED" : "DISABLED"}
            tone={profile.brand_watermark_enabled ? "text-signal-green-text" : "text-ink-muted"}
          />
          <Row label="Text" value={profile.brand_watermark_text || "NOT SET"} />
          <Row label="Position" value={profile.brand_watermark_position.replace(/_/g, " ")} />
          <Row label="Style" value={profile.brand_watermark_style.replace(/_/g, " ")} />
        </dl>
      </section>

      <section>
        <p className="studio-label mb-2">Session</p>
        <dl className="flex flex-col gap-1.5">
          <Row
            label="LinkedIn"
            value={data.linkedin_connected ? "CONNECTED" : "NOT CONNECTED"}
            tone={data.linkedin_connected ? "text-signal-green-text" : "text-ink-muted"}
          />
        </dl>
      </section>

      <p className="studio-meta border-t border-edge pt-3 text-ink-muted">
        EDITED IN BRAND STUDIO, WHICH IS NOT BUILT YET
      </p>
    </div>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-[11px] text-ink-muted">{label}</dt>
      <dd className={cn("studio-meta truncate text-right uppercase", tone ?? "text-ink-secondary")}>{value}</dd>
    </div>
  );
}
