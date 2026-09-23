import { useEffect, useState } from "react";
import { FileImage, FileVideo, FileText } from "lucide-react";
import { fetchMedia, type MediaAsset } from "@/lib/api";

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
 * Lists what is actually in the local library. Uploading happens through the
 * dropzone, so this reports rather than accepts, and it says so when empty
 * instead of drawing an upload target that would not work.
 */
export function MediaPanel() {
  const [assets, setAssets] = useState<MediaAsset[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    fetchMedia()
      .then((rows) => live && setAssets(rows))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  if (failed) return <p className="studio-meta pt-8 text-center text-ink-muted">MEDIA LIBRARY UNAVAILABLE</p>;
  if (!assets) return <p className="studio-meta pt-8 text-center text-ink-muted">LOADING MEDIA</p>;
  if (assets.length === 0) {
    return (
      <p className="studio-meta pt-8 text-center leading-relaxed text-ink-muted">
        NO MEDIA IN THE LOCAL LIBRARY
        <br />
        <span className="text-ink-muted/70">ADDED THROUGH THE DROPZONE</span>
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="studio-label">{assets.length} local asset{assets.length === 1 ? "" : "s"}</p>
      <ul className="flex flex-col gap-1">
        {assets.map((asset) => {
          const Icon = iconFor(asset);
          return (
            <li key={asset.id} className="flex items-start gap-2 rounded-md p-2 hover:bg-soft">
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
            </li>
          );
        })}
      </ul>
    </div>
  );
}
