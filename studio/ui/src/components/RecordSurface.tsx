/**
 * From your record: what from your own record, and from what you asked, is
 * worth writing from today.
 *
 * One batch a day, computed once by the daily job into a dated table and
 * only ever read here; nothing is computed on screen load. This is the
 * section's shell, routed from the rail; the batch, the marks, the Kept
 * level and the "What the studio knows" page arrive with the engine behind
 * them (cycle 4, track 7).
 */
export function RecordSurface() {
  return (
    <div className="px-6 py-6 lg:px-8" tabIndex={0} aria-labelledby="record-title">
      <header>
        <p className="studio-label">From your record</p>
        <h1 id="record-title" className="studio-title mt-1">What is worth writing from today</h1>
        <p className="mt-3 max-w-[62ch] text-[13px] leading-relaxed text-ink-secondary">
          Nothing has been computed yet. The daily batch is built the first time the studio runs each day,
          from your own posts, your own comments and what you asked; this screen only reads it.
        </p>
      </header>
    </div>
  );
}
