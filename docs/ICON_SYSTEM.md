# Icon System

> How the studio draws icons, where they come from, and what to do when you
> need one that does not exist yet.

The interface draws every icon from [lucide](https://lucide.dev), imported as a
React component per glyph. There is one set, one grid, one stroke weight, and
one colour rule. `tests/test_react_ui_contract.py` fails the build for anything
that departs from the last two.

---

## 1. Why components and not a sprite

The previous interface inlined a 37 symbol SVG sprite at the top of its one
page, because an external sprite referenced with `<use href="icons.svg#id">`
does not resolve in every browser, and a per icon `<img>` costs a request each
and cannot inherit text colour. Both problems were real and the sprite was the
right answer to them.

Neither problem survives a bundler. An imported component is inlined into the
bundle at build time, so it costs no request, and it is ordinary JSX, so it
inherits colour like anything else. What it adds is that **only the glyphs
actually referenced are included**: lucide tree shakes, so the icon set does
not grow the bundle by existing.

```tsx
import { CalendarClock } from "lucide-react";

<CalendarClock className="size-4 text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
```

## 2. The contract

| Rule | Value | Why |
|---|---|---|
| Grid | lucide's `24x24` | Mixed grids make icons visually different sizes at the same CSS size. |
| Stroke weight | `1.75` | One weight, so icons sit together in a row. Lucide defaults to 2, which reads heavy beside this typography. |
| Caps and joins | lucide's defaults, round | The geometry is drawn for round terminals. |
| Colour | a text token, never a signal literal | The icon takes the colour of whatever it is set to, so it follows the theme for free. |
| Size | a `size-*` utility, never a hardcoded width | The ramp is shared, so a row stays a row. |

The colour rule is the one that bites, and it bit differently here than it did
with the sprite. A lucide icon inherits `currentColor` automatically, so the
old failure, a `stroke="white"` left on by an exporter, cannot happen. The
failure that replaced it is using a signal colour as an icon colour and
assuming it passes: a signal that is legible as a fill can fail as a mark. Use
`text-ink-muted`, `text-ink-secondary`, or the `-text` step of a signal. See
[UI_CONVENTIONS.md](UI_CONVENTIONS.md) section 1.

## 3. Accessibility is not optional here

Every icon is one of two things, and it must say which:

```tsx
{/* Decorative: it sits beside its own label. */}
<Trash2 className="size-3.5" aria-hidden="true" />

{/* Load bearing: it is the entire content of a control. */}
<button aria-label="Delete this asset"><Trash2 className="size-3.5" aria-hidden="true" /></button>
```

An icon inside a labelled control is still `aria-hidden`: the control carries
the name, and the glyph would otherwise be announced twice. 125 decorative
glyphs were once read aloud as unnamed images, and fourteen icon-only buttons
announced as nothing but "button".

## 4. Sizes

Use a Tailwind size utility, never a hardcoded width.

| Class | Rendered | Used for |
|---|---|---|
| `size-3` | 12px | inline meta, chips |
| `size-3.5` | 14px | row actions, toolbar glyphs |
| `size-4` | 16px | buttons, list icons |
| `size-5` | 20px | section headers |

At 12px a 1.75 stroke on a 24 unit grid is the heaviest the set gets. If an
icon looks muddy there, it is usually too detailed for the size rather than too
heavy, so prefer a simpler glyph over a thinner stroke.

## 5. Adding one

Import it. There is no manifest to update, no sprite to regenerate, and no
build step: lucide ships the whole set and the bundler takes what you named.

Two things to check before you do:

- **Is it decorative or load bearing?** That decides `aria-hidden` versus
  `aria-label`, and getting it wrong is silent.
- **Does an existing glyph already mean this?** A second icon for a concept the
  interface already has one for is how a set stops being a set.

## 6. Where the glyphs come from

| | |
|---|---|
| Set | lucide |
| Licence | ISC, commercial use permitted |
| Package | `lucide-react`, a direct dependency of `studio/ui` |

The previous set was coolicons, inlined by hand. It went with the page it was
inlined into.
