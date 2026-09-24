import { useCallback, useEffect, useState } from "react";
import { Eye, Loader2, Trash2 } from "lucide-react";
import {
  addMcpServer,
  fetchMcpServers,
  previewGrounding,
  removeMcpServer,
  setMcpServerEnabled,
  type EgressReport,
  type GroundingPreview,
  type McpServer,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Grounding sources (MCP).
 *
 * Carried across from the vanilla page's Settings card when that page was
 * retired, because the feature had shipped and the interface it shipped in had
 * not. Two properties from that design are the whole point and are kept:
 *
 * Adding a server stores a command this studio will execute. That is a larger
 * grant than anything else in these settings, so the form says so rather than
 * presenting it as another text field.
 *
 * Adding does not enable. Agreeing that a command exists and agreeing to be
 * read by it are different acts, so they are two deliberate steps and there is
 * no enabled control on the add form.
 */
export function GroundingWorkspace() {
  const [servers, setServers] = useState<McpServer[] | null>(null);
  const [egress, setEgress] = useState<EgressReport | null>(null);
  const [preview, setPreview] = useState<GroundingPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [commandText, setCommandText] = useState("");
  const [description, setDescription] = useState("");

  // A list, never a string handed to a shell. Split here so the tokens can be
  // shown back before anything is stored.
  const commandTokens = commandText.trim().split(/\s+/).filter(Boolean);

  const load = useCallback(async () => {
    const result = await fetchMcpServers();
    setServers(result.servers);
    setEgress(result.egress);
  }, []);

  useEffect(() => {
    load().catch(() => setServers([]));
  }, [load]);

  async function onAdd() {
    if (!name.trim() || commandTokens.length === 0) return;
    setBusy(true);
    setNote(null);
    try {
      await addMcpServer(name.trim(), commandTokens, description.trim());
      setName("");
      setCommandText("");
      setDescription("");
      setNote("Added, and switched off. Turn it on when you want it read.");
      await load();
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : "The server was refused.");
    } finally {
      setBusy(false);
    }
  }

  if (servers === null) return <p className="studio-meta text-ink-muted">LOADING SOURCES</p>;

  return (
    <div className="flex flex-col gap-6">
      {egress && (
        <div
          className={cn(
            "rounded-md border p-3",
            egress.leaves_this_machine
              ? "border-signal-orange/40 bg-signal-orange-subtle"
              : "border-edge",
          )}
        >
          <p className="studio-label mb-1">Where grounding material goes</p>
          <p
            className={cn(
              "text-[12px] leading-snug",
              egress.leaves_this_machine ? "text-signal-orange-text" : "text-ink-secondary",
            )}
          >
            {egress.summary}
          </p>
        </div>
      )}

      <section>
        <div className="mb-2 flex items-baseline justify-between gap-3">
          <p className="studio-label">Sources</p>
          <button
            type="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setNote(null);
              try {
                setPreview(await previewGrounding());
              } catch (caught) {
                setNote(caught instanceof Error ? caught.message : "The preview was refused.");
              } finally {
                setBusy(false);
              }
            }}
            className="studio-meta flex items-center gap-1 text-[10px] text-ink-muted transition-colors hover:text-ink-primary disabled:opacity-40"
          >
            <Eye className="size-3" strokeWidth={2} aria-hidden="true" />
            SHOW WHAT THEY HAND OVER
          </button>
        </div>

        {servers.length === 0 ? (
          <p className="studio-meta text-ink-muted">NO SOURCES CONNECTED</p>
        ) : (
          <ul className="flex flex-col">
            {servers.map((server) => (
              <li key={server.name} className="flex items-start gap-3 border-b border-edge py-2">
                <input
                  type="checkbox"
                  checked={server.enabled}
                  disabled={busy}
                  onChange={async (event) => {
                    setBusy(true);
                    try {
                      await setMcpServerEnabled(server.name, event.target.checked);
                      await load();
                    } finally {
                      setBusy(false);
                    }
                  }}
                  aria-label={`Let ${server.name} be read`}
                  className="mt-0.5 size-4 shrink-0 accent-[var(--studio-orange)]"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-[12px] text-ink-primary">{server.name}</p>
                  {/* The command is shown, not hidden behind the name. It is
                      what this studio will execute. */}
                  <p className="studio-meta truncate text-[10px]">{server.command.join(" ")}</p>
                  {server.description && (
                    <p className="truncate text-[11px] text-ink-muted">{server.description}</p>
                  )}
                </div>
                <button
                  type="button"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await removeMcpServer(server.name);
                      await load();
                    } finally {
                      setBusy(false);
                    }
                  }}
                  aria-label={`Remove ${server.name}`}
                  className="shrink-0"
                >
                  <Trash2
                    className="size-3.5 text-ink-muted hover:text-signal-orange-text"
                    strokeWidth={1.75}
                    aria-hidden="true"
                  />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {preview && (
        <section className="rounded-md border border-edge bg-ink p-3">
          <p className="studio-label mb-2">What would be handed over</p>
          <p
            className={cn(
              "studio-meta mb-2",
              preview.egress.leaves_this_machine ? "text-signal-orange-text" : "text-signal-green-text",
            )}
          >
            {preview.egress.summary.toUpperCase()}
          </p>
          {preview.material.length === 0 ? (
            <p className="studio-meta text-ink-muted">NOTHING GATHERED</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {preview.material.map((entry, index) => (
                <li key={`${entry.server}-${index}`} className="border-l border-edge pl-3">
                  <p className="studio-meta text-[10px]">{entry.server.toUpperCase()}</p>
                  <p className="mt-1 text-[11px] leading-snug whitespace-pre-wrap text-ink-secondary">
                    {entry.text}
                  </p>
                </li>
              ))}
            </ul>
          )}
          {preview.errors.length > 0 && (
            <p className="studio-meta mt-2 leading-snug text-signal-orange-text">
              {preview.errors.join(" | ")}
            </p>
          )}
          <p className="studio-meta mt-2 text-[10px] text-ink-muted">
            {preview.bytes_used} OF {preview.bytes_budget} BYTES
          </p>
        </section>
      )}

      <section className="border-t border-edge pt-4">
        <p className="studio-label mb-2">Connect a source</p>
        <div className="flex flex-col gap-2">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Name"
            aria-label="Source name"
            className="rounded-md border border-edge bg-ink px-2.5 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
          />
          <input
            value={commandText}
            onChange={(event) => setCommandText(event.target.value)}
            placeholder="Command, for example: npx -y @some/mcp-server"
            aria-label="Source command"
            className="rounded-md border border-edge bg-ink px-2.5 py-1.5 font-mono text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
          />
          {commandTokens.length > 0 && (
            /* Shown back as the list it will be stored as, so there is no
               question about what gets run. It never reaches a shell. */
            <p className="studio-meta text-[10px] text-ink-muted">
              RUNS AS {commandTokens.length} ARGUMENT{commandTokens.length === 1 ? "" : "S"}:{" "}
              {commandTokens.map((token) => `[${token}]`).join(" ")}
            </p>
          )}
          <input
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="What it holds (optional)"
            aria-label="Source description"
            className="rounded-md border border-edge bg-ink px-2.5 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong"
          />

          <button
            type="button"
            onClick={onAdd}
            disabled={busy || !name.trim() || commandTokens.length === 0}
            className="flex items-center justify-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
          >
            {busy && <Loader2 className="size-3 animate-spin" aria-hidden="true" />}
            Add, switched off
          </button>

          {note && (
            <p role="status" className="studio-meta leading-snug text-ink-secondary">
              {note}
            </p>
          )}

          <p className="studio-meta leading-relaxed text-ink-muted">
            ADDING A SOURCE STORES A COMMAND THIS STUDIO WILL EXECUTE. IT IS ADDED SWITCHED OFF, AND
            TURNING IT ON IS A SEPARATE CHOICE.
          </p>
        </div>
      </section>
    </div>
  );
}
