import { useCallback, useEffect, useRef, useState } from "react";
import { FileImage, FileText, FileVideo, Loader2, Sparkles, Trash2, Upload } from "lucide-react";
import {
  deleteMedia,
  fetchImageProgress,
  fetchMedia,
  startImageGeneration,
  synthesizeImagePrompt,
  uploadMedia,
  type MediaAsset,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/** Bytes as a person reads them. Binary units, because file managers use them. */
function readableSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`;
}

function iconFor(asset: MediaAsset) {
  if (asset.mime_type.startsWith("video/")) return FileVideo;
  if (asset.mime_type === "application/pdf") return FileText;
  return FileImage;
}

/**
 * The media inspector (blueprint section 10).
 *
 * Accepts a drop, lists what is in the local library, and can ask the image
 * studio for a new asset. Everything here stays on this machine unless a cloud
 * model provider is configured, in which case the concept text reaches it.
 */
export function MediaPanel() {
  const [assets, setAssets] = useState<MediaAsset[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setAssets(await fetchMedia());
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const accept = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;
      setBusy(true);
      setNote(null);
      const failures: string[] = [];
      for (const file of Array.from(files)) {
        try {
          await uploadMedia(file);
        } catch (error) {
          // Named individually. A batch that reports one failure for five
          // files leaves the creator guessing which four arrived.
          failures.push(`${file.name}: ${error instanceof Error ? error.message : "refused"}`);
        }
      }
      await load();
      setBusy(false);
      setNote(failures.length ? failures.join(" · ") : null);
    },
    [load],
  );

  return (
    <div className="flex flex-col gap-4">
      {/* The dropzone is also a button, so the same affordance works without a
          pointer. A drop target that cannot be reached from the keyboard is
          not an upload control. */}
      <button
        type="button"
        onClick={() => fileInput.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          void accept(event.dataTransfer.files);
        }}
        disabled={busy}
        className={cn(
          "flex w-full flex-col items-center gap-1.5 rounded-md border border-dashed p-5",
          "transition-colors duration-(--studio-motion-fast) ease-(--ease-standard)",
          dragging ? "border-signal-orange bg-signal-orange-subtle" : "border-edge hover:border-edge-strong",
          busy && "opacity-50",
        )}
      >
        {busy ? (
          <Loader2 className="size-5 animate-spin text-ink-muted" aria-hidden="true" />
        ) : (
          <Upload className="size-5 text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
        )}
        <span className="text-[12px] text-ink-secondary">
          {busy ? "Uploading" : "Drop a file, or click to choose"}
        </span>
        <span className="studio-meta text-[10px]">IMAGES, PDF CAROUSELS, MP4 AND WEBM</span>
      </button>

      <input
        ref={fileInput}
        type="file"
        multiple
        className="sr-only"
        aria-label="Choose media to upload"
        onChange={(event) => void accept(event.target.files)}
      />

      {note && (
        <p role="status" className="studio-meta leading-snug text-signal-orange-text">
          {note}
        </p>
      )}

      <ImageStudio onDone={load} />

      {failed ? (
        <p className="studio-meta pt-4 text-center text-ink-muted">MEDIA LIBRARY UNAVAILABLE</p>
      ) : !assets ? (
        <p className="studio-meta pt-4 text-center text-ink-muted">LOADING MEDIA</p>
      ) : assets.length === 0 ? (
        <p className="studio-meta pt-4 text-center text-ink-muted">NOTHING IN THE LOCAL LIBRARY YET</p>
      ) : (
        <div className="flex flex-col gap-2 border-t border-edge pt-4">
          <p className="studio-label">
            {assets.length} local asset{assets.length === 1 ? "" : "s"}
          </p>
          <ul className="flex flex-col gap-1">
            {assets.map((asset) => {
              const Icon = iconFor(asset);
              return (
                <li key={asset.id} className="group flex items-start gap-2 rounded-md p-2 hover:bg-soft">
                  <Icon className="mt-0.5 size-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[12px] text-ink-primary">{asset.filename}</p>
                    <p className="studio-meta text-[10px]">
                      {readableSize(asset.size_bytes)}
                      {asset.dimensions && (
                        <>
                          <span className="mx-1.5 text-ink-muted">·</span>
                          {asset.dimensions}
                        </>
                      )}
                      {asset.page_count !== null && (
                        <>
                          <span className="mx-1.5 text-ink-muted">·</span>
                          {asset.page_count} PAGES
                        </>
                      )}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={async () => {
                      await deleteMedia(asset.id).catch(() => undefined);
                      await load();
                    }}
                    aria-label={`Delete ${asset.filename}`}
                    className="opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                  >
                    <Trash2 className="size-3.5 text-ink-muted hover:text-signal-orange-text" strokeWidth={1.75} aria-hidden="true" />
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

/**
 * Image generation, polled rather than awaited.
 *
 * The endpoint starts a task and returns immediately, so the only way to know
 * it finished is to ask. Polling stops on a terminal status rather than after
 * a fixed number of tries, and the percentage shown is the server's own.
 */
function ImageStudio({ onDone }: { onDone: () => Promise<void> }) {
  const [concept, setConcept] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [percent, setPercent] = useState(0);
  const [stage, setStage] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId) return;
    let live = true;

    const timer = window.setInterval(async () => {
      try {
        const progress = await fetchImageProgress(taskId);
        if (!live) return;
        setPercent(progress.progress_percent);
        setStage(progress.status_message);

        if (progress.status === "completed") {
          window.clearInterval(timer);
          setTaskId(null);
          setConcept("");
          await onDone();
        } else if (progress.status === "failed" || progress.error_message) {
          window.clearInterval(timer);
          setTaskId(null);
          setError(progress.error_message || "Generation failed.");
        }
      } catch {
        window.clearInterval(timer);
        if (live) {
          setTaskId(null);
          setError("Progress could not be read, so the outcome is unknown.");
        }
      }
    }, 1200);

    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [taskId, onDone]);

  async function onGenerate() {
    if (!concept.trim() || taskId) return;
    setError(null);
    setPercent(0);
    setStage("");
    try {
      setTaskId(await startImageGeneration(concept.trim(), "1:1"));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The request was refused.");
    }
  }

  return (
    <div className="flex flex-col gap-2 border-t border-edge pt-4">
      <p className="studio-label">Generate an image</p>
      <textarea
        value={concept}
        onChange={(event) => setConcept(event.target.value)}
        rows={2}
        disabled={Boolean(taskId)}
        placeholder="Describe the image"
        aria-label="Image concept"
        className="resize-none rounded-md border border-edge bg-ink px-2.5 py-1.5 text-[12px] text-ink-primary outline-none placeholder:text-ink-muted focus-visible:border-edge-strong disabled:opacity-50"
      />
      <div className="flex gap-2">
        {/* The prompt the studio would actually send, shown before anything is
            rendered. Generation does not need it; a creator deciding whether
            to spend a render does. */}
        <button
          type="button"
          onClick={async () => {
            if (!concept.trim()) return;
            try {
              const result = await synthesizeImagePrompt(concept.trim(), "1:1");
              setPreview(result.master_prompt);
            } catch {
              setPreview(null);
            }
          }}
          disabled={Boolean(taskId) || !concept.trim()}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
        >
          Preview prompt
        </button>
        <button
          type="button"
          onClick={onGenerate}
          disabled={Boolean(taskId) || !concept.trim()}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-[11px] text-ink-secondary transition-colors hover:bg-soft hover:text-ink-primary disabled:opacity-40"
        >
          <Sparkles className="size-3.5" strokeWidth={1.75} aria-hidden="true" />
          {taskId ? `${percent}%` : "Generate"}
        </button>
      </div>

      {preview && (
        <p className="rounded-md border border-edge bg-ink p-2 text-[11px] leading-snug text-ink-secondary">
          {preview}
        </p>
      )}

      {taskId && (
        <>
          {/* A real bar rather than a spinner, because the server reports a
              real percentage and a long wait with no sense of progress reads
              as a hang. */}
          <div className="h-1 w-full overflow-hidden rounded-full bg-soft" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
            <div
              className="h-full bg-signal-orange transition-[width] duration-(--studio-motion-standard)"
              style={{ width: `${percent}%` }}
            />
          </div>
          {stage && <p className="studio-meta text-[10px]">{stage.toUpperCase()}</p>}
        </>
      )}

      {error && (
        <p role="status" className="studio-meta leading-snug text-signal-orange-text">
          {error}
        </p>
      )}
    </div>
  );
}
