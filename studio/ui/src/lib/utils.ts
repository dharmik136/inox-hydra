import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge class names, letting a later Tailwind utility win over an earlier one
 * in the same group. Without twMerge, `cn("p-2", "p-4")` emits both and the
 * winner is whichever the stylesheet happens to order last.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
