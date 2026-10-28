import { useEffect, useRef, useState, useCallback } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Check, Plus, Trash2, Users, X } from "lucide-react";
import {
  fetchAccounts,
  createAccount,
  switchAccount,
  deleteAccount,
  type CreatorAccount,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { reloadStudio, unsavedWorkLabels } from "@/lib/unsaved";
import { useModalFocus } from "@/lib/modalFocus";

const LICENCE_CHANGED = "inox:licence-changed";

/**
 * Each profile is its own database, so switching reloads the studio. Asks
 * first if that would lose work, naming whose: the Composer was the only one
 * it knew of, so Brand Studio edits went without a question.
 */
function mayReload(): boolean {
  const lost = unsavedWorkLabels();
  return (
    lost.length === 0 ||
    window.confirm(
      `${lost.join(" and ")} ${lost.length === 1 ? "has" : "have"} unsaved changes. Switching profile reloads the studio and discards them. Switch anyway?`,
    )
  );
}

interface AccountSwitcherProps {
  onAccountSwitched?: (account: CreatorAccount) => void;
  className?: string;
  condensed?: boolean;
  /**
   * Which side of the trigger the panel opens on. The rail's avatar sits at
   * the bottom of the window, so its panel opens upward; the tray's card sits
   * at the top, where opening upward drew the panel above the window.
   */
  placement?: "above" | "below";
}

export function AccountSwitcher({
  onAccountSwitched,
  className,
  condensed = true,
  placement = "above",
}: AccountSwitcherProps) {
  const [open, setOpen] = useState(false);
  const [accounts, setAccounts] = useState<CreatorAccount[]>([]);
  const [activeId, setActiveId] = useState<string>("default");
  const [error, setError] = useState<string | null>(null);

  // Form state for creating a new profile
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newHeadline, setNewHeadline] = useState("");
  const [newVanity, setNewVanity] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [limit, setLimit] = useState(1);
  // Whether the profiles and the licence have been read. Before the first
  // answer the switcher held no profiles against a limit of one, so it offered
  // Add Creator Profile, which a one-profile licence refuses, and took the
  // button away when the answer came: focus on it fell to the page behind.
  const [loaded, setLoaded] = useState(false);

  // Deleting removes the profile's folder, database and media, so it asks for
  // the profile's name first. One row at a time.
  const [deleting, setDeleting] = useState<CreatorAccount | null>(null);
  const [confirmText, setConfirmText] = useState("");

  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  const loadAccounts = useCallback(async () => {
    try {
      setError(null);
      const res = await fetchAccounts();
      setAccounts(res.accounts);
      setActiveId(res.active_account_id);
      setLimit(res.profile_limit ?? 1);
      setLoaded(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load profiles");
    }
  }, []);

  useEffect(() => {
    loadAccounts();
    // A licence entered or removed in Settings changes how many profiles fit.
    const onLicence = () => void loadAccounts();
    window.addEventListener(LICENCE_CHANGED, onLicence);
    return () => window.removeEventListener(LICENCE_CHANGED, onLicence);
  }, [loadAccounts]);

  // Read again on every open, so a licence entered in another tab, or straight
  // through the API, is reflected in whether a profile can be added.
  useEffect(() => {
    if (open) void loadAccounts();
  }, [open, loadAccounts]);

  const activeAccount = accounts.find((a) => a.id === activeId) ?? accounts[0];
  const atLimit = accounts.length >= limit;

  const handleSwitch = async (account: CreatorAccount) => {
    if (account.id === activeId) {
      setOpen(false);
      return;
    }
    if (!mayReload()) return;
    try {
      await switchAccount(account.id);
      setActiveId(account.id);
      setOpen(false);
      if (onAccountSwitched) {
        onAccountSwitched(account);
      }
      // Each profile is its own database, so every screen has to read again.
      // A reload is the one way to be sure none keeps the last profile's data.
      reloadStudio();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to switch profile");
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    if (!mayReload()) return;

    try {
      setSubmitting(true);
      setError(null);
      const res = await createAccount({
        name: newName.trim(),
        headline: newHeadline.trim(),
        vanity: newVanity.trim(),
      });
      setNewName("");
      setNewHeadline("");
      setNewVanity("");
      setCreating(false);

      // Switch to newly created account immediately
      if (res.account) {
        await switchAccount(res.account.id);
        setActiveId(res.account.id);
        setOpen(false);
        if (onAccountSwitched) {
          onAccountSwitched(res.account);
        }
        reloadStudio();
        return;
      }
      await loadAccounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create profile");
    } finally {
      setSubmitting(false);
    }
  };

  const askDelete = (account: CreatorAccount, e: React.MouseEvent) => {
    e.stopPropagation();
    if (account.is_default || account.id === activeId) return;
    setDeleting(account);
    setConfirmText("");
    setError(null);
  };

  const handleDelete = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!deleting) return;
    try {
      await deleteAccount(deleting.id, confirmText.trim());
      setDeleting(null);
      setConfirmText("");
      await loadAccounts();
      closeRef.current?.focus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove profile");
    }
  };

  // Focus moves into the panel, Tab stays in it, and Escape closes it and
  // returns focus to the trigger. Tab used to walk out into the page.
  useModalFocus(panelRef, open, () => setOpen(false));

  const cancelCreate = () => {
    setCreating(false);
    closeRef.current?.focus();
  };

  return (
    <div className={cn("relative", className)}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label={`Current profile: ${activeAccount?.name || "loading"}`}
        title={`Profile: ${activeAccount?.name || "loading"} (Click to switch)`}
        className={cn(
          "group relative flex items-center justify-center rounded-md transition-all",
          condensed
            ? "size-9 hover:bg-soft"
            : "w-full gap-2.5 rounded-lg border border-edge bg-soft/50 p-2 text-left hover:bg-soft",
        )}
      >
        <span
          className={cn(
            "grid size-7 place-items-center rounded-full bg-raised font-mono text-xs font-semibold text-ink-primary shadow-xs ring-1 ring-edge",
            "transition-transform group-hover:scale-105",
          )}
        >
          {activeAccount?.avatar_initials || ""}
        </span>

        {!condensed && (
          <span className="min-w-0 flex-1">
            <span className="block truncate text-xs font-medium text-ink-primary">
              {activeAccount?.name || ""}
            </span>
            {activeAccount?.headline && (
              <span className="block truncate text-[11px] text-ink-muted">{activeAccount.headline}</span>
            )}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <>
            {/* Backdrop click dismiss */}
            <div
              className="fixed inset-0 z-40 bg-canvas/40 backdrop-blur-[1px]"
              onClick={() => setOpen(false)}
              aria-hidden="true"
            />

            <motion.div
              ref={panelRef}
              role="dialog"
              aria-modal="true"
              aria-label="Manage creator profiles"
              initial={{ opacity: 0, scale: 0.96, y: -4 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: -4 }}
              transition={{ duration: 0.16, ease: [0.32, 0.72, 0.24, 1] }}
              className={cn(
                "absolute left-0 z-50 rounded-xl border border-edge bg-raised p-3 shadow-2xl outline-none",
                placement === "above" ? "bottom-11 w-84 origin-bottom-left" : "top-full right-0 mt-1.5 origin-top-left",
              )}
            >
              {/* Header */}
              <div className="flex items-center justify-between border-b border-edge pb-2">
                <div className="flex items-center gap-2">
                  <Users className="size-4 text-signal-orange-text" aria-hidden="true" />
                  <span className="text-xs font-semibold tracking-wide uppercase text-ink-primary">
                    Creator Profiles
                  </span>
                </div>
                <button
                  ref={closeRef}
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="Close profile switcher"
                  className="rounded-md p-1 text-ink-muted hover:bg-soft hover:text-ink-primary"
                >
                  <X className="size-3.5" aria-hidden="true" />
                </button>
              </div>

              <p className="mt-2 text-[11px] leading-snug text-ink-muted">
                Each profile has its own database, media and backups. Nothing one profile holds
                appears in another.
              </p>

              {error && (
                <div role="alert" className="my-2 rounded-md bg-signal-orange/10 px-2.5 py-1.5 text-xs text-signal-orange-text">
                  {error}
                </div>
              )}

              {deleting && (
                <form
                  onSubmit={handleDelete}
                  className="my-2 rounded-lg border border-signal-orange/40 bg-soft/40 p-2.5"
                  aria-label={`Delete ${deleting.name}`}
                >
                  <label htmlFor="confirm-delete-profile" className="block text-xs text-ink-primary">
                    This deletes {deleting.name}'s database, media and backups from this machine.
                    Type <span className="font-semibold">{deleting.name}</span> to confirm.
                  </label>
                  <input
                    id="confirm-delete-profile"
                    type="text"
                    autoFocus
                    value={confirmText}
                    onChange={(e) => setConfirmText(e.target.value)}
                    autoComplete="off"
                    className="mt-2 w-full rounded border border-edge bg-ink px-2 py-1 text-xs text-ink-primary focus:border-signal-orange focus:outline-none"
                  />
                  <div className="mt-2 flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setDeleting(null);
                        closeRef.current?.focus();
                      }}
                      className="rounded px-2 py-1 text-xs text-ink-muted hover:text-ink-primary"
                    >
                      Keep it
                    </button>
                    <button
                      type="submit"
                      disabled={confirmText.trim() !== deleting.name && confirmText.trim() !== deleting.id}
                      className="rounded bg-signal-orange px-3 py-1 text-xs font-medium text-on-signal disabled:opacity-40"
                    >
                      Delete profile
                    </button>
                  </div>
                </form>
              )}

              {/* Account list */}
              <div className="my-2 max-h-64 space-y-1 overflow-y-auto pr-0.5">
                {!loaded && !error && (
                  <p role="status" className="text-[11px] leading-snug text-ink-muted">
                    Reading your profiles and licence.
                  </p>
                )}
                {accounts.map((acc) => {
                  const isActive = acc.id === activeId;
                  return (
                    <div
                      key={acc.id}
                      className={cn(
                        "group relative flex items-start gap-2.5 rounded-lg border p-2 transition-colors",
                        isActive
                          ? "border-signal-orange/40 bg-soft/70 shadow-xs"
                          : "border-transparent hover:border-edge hover:bg-soft/40",
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => handleSwitch(acc)}
                        aria-current={isActive ? "true" : undefined}
                        className="flex min-w-0 flex-1 cursor-pointer items-start gap-2.5 text-left"
                      >
                      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-ink font-mono text-xs font-semibold text-ink-primary ring-1 ring-edge">
                        {acc.avatar_initials}
                      </span>

                      <span className="block min-w-0 flex-1">
                        <span className="flex items-center gap-1.5">
                          <span className="truncate text-xs font-medium text-ink-primary">
                            {acc.name}
                          </span>
                          {acc.is_default && (
                            <span className="studio-meta rounded bg-soft px-1 py-0.2 text-[9px] text-ink-muted">
                              DEFAULT
                            </span>
                          )}
                          {isActive && (
                            <span className="studio-meta rounded border border-signal-orange/50 px-1 py-0.2 text-[9px] font-semibold text-ink-primary">
                              ACTIVE
                            </span>
                          )}
                        </span>

                        {acc.headline && (
                          <span className="block truncate text-[11px] text-ink-muted">{acc.headline}</span>
                        )}

                        <span className="mt-1 flex items-center gap-2 studio-meta text-[10px] text-ink-muted">
                          <span>{acc.drafts_count ?? 0} drafts</span>
                          <span>·</span>
                          <span>{acc.posts_count ?? 0} posts</span>
                          <span>·</span>
                          <span>{acc.leads_count ?? 0} leads</span>
                        </span>
                      </span>
                      </button>

                      <div className="flex shrink-0 items-center gap-1">
                        {isActive ? (
                          <Check className="size-4 text-signal-orange-text" aria-hidden="true" />
                        ) : !acc.is_default ? (
                          <button
                            type="button"
                            onClick={(e) => askDelete(acc, e)}
                            aria-label={`Delete ${acc.name} profile`}
                            title="Delete profile"
                            className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 rounded p-1 text-ink-muted hover:bg-soft hover:text-signal-orange-text transition-opacity"
                          >
                            <Trash2 className="size-3.5" aria-hidden="true" />
                          </button>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Add account section. At the licence's limit the form is not
                  offered: it used to take a name, headline and vanity and only
                  then refuse, so the limit is explained up front instead.
                  Neither is shown until the profiles and licence are read. */}
              {!creating && loaded && atLimit && (
                <p className="mt-1 text-[11px] leading-snug text-ink-muted">
                  {limit === 1
                    ? "Your licence covers one creator profile. More than one needs the Agency licence, entered in Settings, Licence."
                    : `Your licence covers ${limit} creator profiles, and all ${limit} are in use.`}
                </p>
              )}
              {creating ? (
                <form onSubmit={handleCreate} className="mt-2 rounded-lg border border-edge bg-soft/30 p-2.5">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-medium text-ink-primary">New Creator Profile</span>
                    <button
                      type="button"
                      onClick={cancelCreate}
                      aria-label="Cancel new profile creation"
                      className="text-ink-muted hover:text-ink-primary"
                    >
                      <X className="size-3" aria-hidden="true" />
                    </button>
                  </div>

                  <div className="space-y-2">
                    <div>
                      <input
                        type="text"
                        placeholder="Profile Name (e.g. Elena Rostova)"
                        // The button that opened the form is gone, so focus
                        // goes to the first field rather than to the page.
                        autoFocus
                        value={newName}
                        onChange={(e) => setNewName(e.target.value)}
                        required
                        className="w-full rounded border border-edge bg-ink px-2 py-1 text-xs text-ink-primary placeholder:text-ink-muted focus:border-signal-orange focus:outline-none"
                      />
                    </div>
                    <div>
                      <input
                        type="text"
                        placeholder="Headline (e.g. VP of Product Architecture)"
                        value={newHeadline}
                        onChange={(e) => setNewHeadline(e.target.value)}
                        className="w-full rounded border border-edge bg-ink px-2 py-1 text-xs text-ink-primary placeholder:text-ink-muted focus:border-signal-orange focus:outline-none"
                      />
                    </div>
                    <div>
                      <input
                        type="text"
                        placeholder="LinkedIn Vanity (e.g. elena-rostova)"
                        value={newVanity}
                        onChange={(e) => setNewVanity(e.target.value)}
                        className="w-full rounded border border-edge bg-ink px-2 py-1 text-xs text-ink-primary placeholder:text-ink-muted focus:border-signal-orange focus:outline-none"
                      />
                    </div>

                    <div className="flex justify-end gap-2 pt-1">
                      <button
                        type="button"
                        onClick={cancelCreate}
                        className="rounded px-2 py-1 text-xs text-ink-muted hover:text-ink-primary"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={submitting || !newName.trim()}
                        className="rounded bg-signal-orange px-3 py-1 text-xs font-medium text-on-signal transition-opacity disabled:opacity-50"
                      >
                        {submitting ? "Adding..." : "Add Profile"}
                      </button>
                    </div>
                  </div>
                </form>
              ) : !loaded || atLimit ? null : (
                <button
                  type="button"
                  onClick={() => setCreating(true)}
                  className="mt-1 flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-edge py-2 text-xs font-medium text-ink-muted hover:border-signal-orange/40 hover:bg-soft/40 hover:text-ink-primary transition-colors"
                >
                  <Plus className="size-3.5" aria-hidden="true" />
                  Add Creator Profile
                </button>
              )}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
