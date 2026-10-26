import { useEffect, useState } from "react";

/**
 * Whether a media query matches, kept current as the window resizes.
 *
 * Read synchronously on the first render, so a layout that depends on it does
 * not draw the wide version for one frame and then jump.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia(query).matches
      : false,
  );

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(query);
    const update = () => setMatches(list.matches);
    update();
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, [query]);

  return matches;
}

/**
 * Below this the composer cannot spare a docked inspector: at 768 pixels a
 * 380 pixel panel left the editor a 330 pixel column, and on a phone it left
 * none at all. The inspector becomes a drawer over the editor instead.
 */
export const DOCKED_INSPECTOR_QUERY = "(min-width: 1024px)";

/**
 * From this width the rail shows its labels and its group names; below it,
 * icons, with each label on hover. Icon-only rails are the pattern measured
 * as ignored (sections report, decision 16, after GitLab's 1200 pixel rule).
 */
export const RAIL_EXPANDED_QUERY = "(min-width: 1200px)";
