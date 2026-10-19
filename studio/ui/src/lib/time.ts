/**
 * Times as the creator's own clock reads them.
 *
 * The studio stores every time in UTC, and a screen that showed the stored
 * string sliced to sixteen characters showed UTC: a post queued for Tuesday
 * 08:30 in India appeared on the Queue as "2026-10-20 03:00", while the
 * Publish dialog and Today said 08:30. Every timestamp a screen shows goes
 * through here instead, in the machine's own time zone.
 */

/**
 * A stored time as a short local date and time, for example "Tue 20 Oct, 08:30".
 *
 * The year is added only when it is not this year. A missing time reads as
 * `missing`, and a value that is not a time reads as itself, so a malformed
 * row is visible rather than silently shown as some other moment.
 */
export function formatLocal(iso: string | null | undefined, missing = "No time set"): string {
  if (!iso) return missing;
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return iso;
  const options: Intl.DateTimeFormatOptions = {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  };
  if (when.getFullYear() !== new Date().getFullYear()) options.year = "numeric";
  return when.toLocaleString(undefined, options);
}
