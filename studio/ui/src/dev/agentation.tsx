import { createRoot } from "react-dom/client";
import { Agentation } from "agentation";

/**
 * The Agentation review toolbar, for interface work only.
 *
 * Click any element, write what is wrong with it, and the note goes to the
 * agent through the agentation-mcp server with the element's selector and
 * position attached, so feedback names the exact control instead of
 * describing it. See docs/UI_AGENT_WORKFLOW.md, section 9.
 *
 * It never reaches a user. main.tsx imports this module only when Vite is
 * serving in dev mode or the build was asked for it with VITE_AGENTATION=1.
 * Both are replaced with constants at build time, so a normal build drops the
 * import and this file with it, and tests/test_agentation_is_dev_only.py
 * checks the shipped bundle for any trace of it.
 *
 * Its own React root, outside the studio's tree, so nothing in App can depend
 * on it being there.
 */
export function mountAgentation(): void {
  const host = document.createElement("div");
  host.id = "agentation-review";
  document.body.appendChild(host);
  createRoot(host).render(
    <Agentation
      endpoint={import.meta.env.VITE_AGENTATION_ENDPOINT || "http://localhost:4747"}
      appName="Inox Hydra Studio"
    />,
  );
}
