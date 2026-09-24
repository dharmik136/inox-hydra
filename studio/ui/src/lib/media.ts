/**
 * Reading an asset's stored dimensions.
 *
 * The media table keeps dimensions as a JSON string, and the panel printed it
 * straight into the row, so every generated image reported its size to the
 * author as {"width": 1080, "height": 1080}. The value was correct and the
 * presentation was a serialisation leak.
 *
 * Uploads do not all agree on the shape, and an asset whose dimensions were
 * never measured stores null, so this is deliberately tolerant: anything it
 * cannot read as a pair of numbers comes back as null and the row shows no
 * dimensions rather than showing the raw field again.
 */

export function formatDimensions(raw: string | null | undefined): string | null {
  if (!raw) return null;

  const text = raw.trim();
  if (!text) return null;

  // The stored shape: a JSON object with width and height.
  if (text.startsWith("{")) {
    try {
      const parsed = JSON.parse(text) as Record<string, unknown>;
      const width = Number(parsed.width);
      const height = Number(parsed.height);
      if (Number.isFinite(width) && Number.isFinite(height) && width > 0 && height > 0) {
        return `${width} x ${height}`;
      }
    } catch {
      // Not JSON after all. Fall through to the plain forms below rather than
      // showing the author a brace.
    }
    return null;
  }

  // Already readable, in any of the forms an upload path might have written.
  const pair = text.match(/^(\d+)\s*[x×*]\s*(\d+)$/i);
  if (pair) return `${pair[1]} x ${pair[2]}`;

  return null;
}
