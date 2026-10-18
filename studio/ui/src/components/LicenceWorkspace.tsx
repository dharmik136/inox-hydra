import { useCallback, useEffect, useState } from "react";
import { KeyRound, Loader2 } from "lucide-react";
import { fetchLicence, installLicence, removeLicence, type LicenceState } from "@/lib/api";

/**
 * Brand Studio, Licence.
 *
 * The licence is a signed key checked on this machine against the vendor's
 * public key. Nothing is sent anywhere to check it, which is why it can be
 * pasted rather than signed in to. What the tiers cost is shown here because
 * this is where someone looks for it, and it says plainly what the licence
 * changes today: the number of creator profiles, while every Creator feature
 * is open during the beta.
 */
export function LicenceWorkspace() {
  const [state, setState] = useState<LicenceState | null>(null);
  const [failed, setFailed] = useState(false);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setState(await fetchLicence());
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onInstall(event: React.FormEvent) {
    event.preventDefault();
    if (!key.trim()) return;
    setBusy(true);
    setNote(null);
    try {
      const result = await installLicence(key.trim());
      setState(result.licence);
      setKey("");
      setNote("Licence accepted.");
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "The licence was refused.");
    } finally {
      setBusy(false);
    }
  }

  async function onRemove() {
    setBusy(true);
    setNote(null);
    try {
      setState((await removeLicence()).licence);
      setNote("Licence removed from this machine.");
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "The licence could not be removed.");
    } finally {
      setBusy(false);
    }
  }

  if (failed) return <p className="studio-meta text-ink-muted">THE LICENCE COULD NOT BE READ</p>;
  if (!state) return <p className="studio-meta text-ink-muted">READING</p>;

  const held = state.licence;

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="licence-now">
        <h2 id="licence-now" className="studio-label mb-2">
          This machine
        </h2>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 text-[13px]">
          <dt className="text-ink-muted">Tier</dt>
          <dd className="text-ink-primary">{state.tier_label}</dd>
          <dt className="text-ink-muted">Licence</dt>
          <dd className="text-ink-secondary">
            {state.status === "none" && "None entered"}
            {state.status === "active" && held && `${held.kind === "lifetime" ? "Lifetime" : "Annual"}, for ${held.email}`}
            {state.status === "expired" && held && `Expired ${held.expires_at}, for ${held.email}`}
            {state.status === "invalid" && "Not accepted"}
          </dd>
          {held?.expires_at && state.status === "active" && (
            <>
              <dt className="text-ink-muted">Renews</dt>
              <dd className="text-ink-secondary">{held.expires_at}</dd>
            </>
          )}
          {held?.kind === "lifetime" && held.updates_until && (
            <>
              <dt className="text-ink-muted">Updates until</dt>
              <dd className="text-ink-secondary">{held.updates_until}</dd>
            </>
          )}
          <dt className="text-ink-muted">Creator profiles</dt>
          <dd className="text-ink-secondary">
            {state.profile_limit === 1 ? "1" : `Up to ${state.profile_limit}`}, each with its own database
          </dd>
        </dl>
        {state.reason && <p className="mt-2 text-[13px] text-signal-orange-text">{state.reason}</p>}
        {state.beta_open && (
          <p className="mt-3 text-[13px] leading-relaxed text-ink-secondary">
            During the beta every Creator feature is open on every install, licensed or not. A
            licence changes one thing today: more than one creator profile needs the Agency tier.
          </p>
        )}
      </section>

      <section aria-labelledby="licence-enter" className="border-t border-edge pt-5">
        <h2 id="licence-enter" className="studio-label mb-2">
          Enter a licence
        </h2>
        <form onSubmit={onInstall} className="flex flex-col gap-2">
          <label htmlFor="licence-key" className="text-[13px] text-ink-secondary">
            Paste the key from your purchase email. It is checked here, on this machine; nothing
            is sent anywhere.
          </label>
          <textarea
            id="licence-key"
            value={key}
            onChange={(event) => setKey(event.target.value)}
            rows={3}
            spellCheck={false}
            className="w-full resize-y rounded-md border border-edge bg-canvas px-2.5 py-2 font-mono text-[12px] text-ink-primary placeholder:text-ink-muted focus:border-signal-orange focus:outline-none"
            placeholder="IHL1."
          />
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="submit"
              disabled={busy || !key.trim()}
              className="flex items-center gap-1.5 rounded-md bg-signal-orange px-3 py-1 text-xs font-medium text-on-signal transition-[filter] hover:brightness-110 disabled:opacity-40"
            >
              {busy ? (
                <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <KeyRound className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
              )}
              Use this licence
            </button>
            {state.status !== "none" && (
              <button
                type="button"
                onClick={() => void onRemove()}
                disabled={busy}
                className="rounded-md border border-edge px-2.5 py-1 text-[12px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
              >
                Remove licence
              </button>
            )}
          </div>
        </form>
        {note && (
          <p role="status" className="mt-2 text-[13px] text-ink-secondary">
            {note}
          </p>
        )}
      </section>

      <section aria-labelledby="licence-prices" className="border-t border-edge pt-5">
        <h2 id="licence-prices" className="studio-label mb-2">
          Prices
        </h2>
        <ul className="flex flex-col gap-2">
          <li className="text-[13px] text-ink-secondary">
            <span className="text-ink-primary">Free.</span> The composer, the fold simulator, the
            audit, hooks from templates, and export.
          </li>
          {state.prices.map((price) => (
            <li key={price.tier} className="text-[13px] text-ink-secondary">
              <span className="text-ink-primary">{price.label}.</span> {price.price}, or {price.or}.
              {price.tier === "creator" &&
                " Analytics, leads, Today, patterns, AI with your own key, the Obsidian export and the LinkedIn archive import."}
              {price.tier === "agency" && " Every Creator feature, for each profile."}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[12px] leading-relaxed text-ink-muted">
          An annual licence that ends returns this machine to the free tier. Nothing is deleted,
          and everything stays readable and exportable.
        </p>
      </section>
    </div>
  );
}
