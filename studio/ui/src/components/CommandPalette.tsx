import { useEffect } from "react";
import { Command } from "cmdk";
import { AnimatePresence, motion } from "motion/react";
import { STUDIO_SECTIONS, type SectionId } from "@/lib/navigation";

/** Blueprint section 5: actions are grouped by intent, not by feature area. */
type Intent = "Write" | "Review" | "Publish" | "Research" | "Organize" | "Inspect";

interface PaletteAction {
  id: string;
  label: string;
  intent: Intent;
  hint?: string;
  run: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onNavigate: (id: SectionId) => void;
  onToggleTheme: () => void;
  onToggleInspector: () => void;
}

export function CommandPalette({
  open,
  onOpenChange,
  onNavigate,
  onToggleTheme,
  onToggleInspector,
}: CommandPaletteProps) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      // metaKey covers macOS, ctrlKey covers Windows and Linux. Checking only
      // one of them leaves half the users without the palette.
      if (event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        onOpenChange(!open);
        return;
      }

      // Escape has to be handled here. cmdk ships this behaviour in
      // Command.Dialog, but this palette renders a bare Command inside its own
      // overlay so it can be animated, and a bare Command binds nothing. Without
      // this the only way out is clicking the scrim, which leaves keyboard users
      // stuck behind a full screen overlay.
      if (event.key === "Escape" && open) {
        event.preventDefault();
        onOpenChange(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  const actions: PaletteAction[] = [
    ...STUDIO_SECTIONS.map<PaletteAction>((section) => ({
      id: `go-${section.id}`,
      label: `Go to ${section.label}`,
      intent: "Organize",
      hint: section.blurb,
      run: () => onNavigate(section.id),
    })),
    { id: "hooks", label: "Generate 5 hooks", intent: "Write", hint: "Re-open the first paragraph", run: () => onNavigate("composer") },
    { id: "sharper", label: "Make sharper", intent: "Write", hint: "Tighten without changing the claim", run: () => onNavigate("composer") },
    { id: "contrarian", label: "Add contrarian angle", intent: "Write", run: () => onNavigate("composer") },
    { id: "audit", label: "Audit for reach", intent: "Review", hint: "Outbound links, hashtags, dwell", run: onToggleInspector },
    { id: "fold", label: "Check fold safety", intent: "Review", run: onToggleInspector },
    { id: "carousel", label: "Turn into carousel", intent: "Publish", run: () => onNavigate("composer") },
    { id: "schedule", label: "Schedule at peak slot", intent: "Publish", hint: "Next local peak window", run: () => onNavigate("queue") },
    { id: "playbook", label: "Search the playbook", intent: "Research", hint: "Offline FTS5 index", run: () => onNavigate("docs") },
    { id: "swipe", label: "Find a similar specimen", intent: "Research", run: () => onNavigate("swipe") },
    { id: "theme", label: "Switch theme", intent: "Inspect", hint: "Light and dark", run: onToggleTheme },
    { id: "inspector", label: "Toggle inspector", intent: "Inspect", run: onToggleInspector },
  ];

  const intents: Intent[] = ["Write", "Review", "Publish", "Research", "Organize", "Inspect"];

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.12 }}
          className="fixed inset-0 z-50 grid place-items-start justify-center bg-canvas/70 p-4 pt-[14vh] backdrop-blur-sm"
          onClick={() => onOpenChange(false)}
        >
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.22, ease: [0.32, 0.72, 0.24, 1] }}
            onClick={(event) => event.stopPropagation()}
            className="w-full max-w-lg overflow-hidden rounded-lg border border-edge bg-raised shadow-2xl"
          >
            <Command label="Studio command palette" loop>
              <Command.Input
                autoFocus
                placeholder="Search actions"
                className="w-full border-b border-edge bg-transparent px-4 py-3 text-sm text-ink-primary outline-none placeholder:text-ink-muted"
              />
              <Command.List className="max-h-80 overflow-y-auto p-2">
                <Command.Empty className="px-2 py-6 text-center text-xs text-ink-muted">
                  Nothing matches that.
                </Command.Empty>

                {intents.map((intent) => {
                  const group = actions.filter((action) => action.intent === intent);
                  if (group.length === 0) return null;
                  return (
                    <Command.Group
                      key={intent}
                      heading={intent}
                      className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.08em] [&_[cmdk-group-heading]]:text-ink-muted"
                    >
                      {group.map((action) => (
                        <Command.Item
                          key={action.id}
                          value={`${action.label} ${action.hint ?? ""}`}
                          onSelect={() => {
                            action.run();
                            onOpenChange(false);
                          }}
                          className="flex cursor-pointer items-baseline justify-between gap-3 rounded-md px-2 py-2 text-[13px] text-ink-secondary data-[selected=true]:bg-soft data-[selected=true]:text-ink-primary"
                        >
                          <span>{action.label}</span>
                          {action.hint && <span className="shrink-0 text-[11px] text-ink-muted">{action.hint}</span>}
                        </Command.Item>
                      ))}
                    </Command.Group>
                  );
                })}
              </Command.List>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
