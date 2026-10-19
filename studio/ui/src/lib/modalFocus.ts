import { useEffect, useRef, type RefObject } from "react";

/**
 * Keyboard focus for a modal: taken when it opens, kept inside while it is
 * open, and given back to whatever opened it when it closes.
 *
 * The palette, the tray and the profile switcher each said aria-modal and
 * none behaved like it: Tab walked out into the page behind the overlay, and
 * Escape dropped focus on the body. A keyboard user had to tab through the
 * whole studio to get back to where they were.
 *
 * Open modals form a stack, and only the top one answers Tab and Escape. So
 * when one sits inside another (the profile switcher in the tray), Escape
 * closes one layer, not both, and a key pressed while focus has fallen to the
 * body (a focused button that became disabled) still reaches the modal.
 *
 * The modal's first control should not carry autoFocus. React applies it
 * before this effect runs, and the element that opened the modal, which is
 * what focus returns to, would then read as the modal's own input.
 */

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Open modals, innermost last. */
const stack: HTMLElement[] = [];

function focusables(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (element) => element.getClientRects().length > 0,
  );
}

export function useModalFocus(
  ref: RefObject<HTMLElement | null>,
  open: boolean,
  onEscape: () => void,
  /** "first" focuses the first control; "self" focuses the modal itself, which needs tabIndex -1. */
  initial: "first" | "self" = "first",
): void {
  const escape = useRef(onEscape);
  escape.current = onEscape;

  useEffect(() => {
    if (!open) return;
    const root = ref.current;
    if (!root) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    stack.push(root);

    if (!root.contains(document.activeElement)) {
      (initial === "self" ? root : (focusables(root)[0] ?? root)).focus({ preventScroll: true });
    }

    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || stack[stack.length - 1] !== root) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        escape.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusables(root);
      const active = document.activeElement;
      if (!items.length) {
        event.preventDefault();
        root.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const outside = !root.contains(active);
      if (event.shiftKey && (outside || active === first || active === root)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (outside || active === last)) {
        event.preventDefault();
        first.focus();
      }
    };

    // Capture, so the modal hears the key before anything behind it does.
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      const index = stack.lastIndexOf(root);
      if (index !== -1) stack.splice(index, 1);
      // Back to the opener only if it is still on the page and focus has not
      // already been sent somewhere on purpose.
      const now = document.activeElement;
      const stranded = !now || now === document.body || root.contains(now);
      if (stranded && opener && opener.isConnected) opener.focus({ preventScroll: true });
    };
  }, [open, ref, initial]);
}
