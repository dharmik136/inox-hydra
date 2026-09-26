# UI Conventions

> The rules the studio interface is held to, and what to do when you add a
> surface to it. Icons have their own document: [ICON_SYSTEM.md](ICON_SYSTEM.md).

The interface is the React application in `studio/ui`, built to
`studio/frontend_next`. `tests/test_react_ui_contract.py` enforces everything on
this page.

Every rule here was added because it had already been broken in shipped code.
The code it was broken in was a vanilla page that no longer exists, and the
rules outlived it, because none of them was about that page. They are about
what happens to a themed interface when a colour is written into a component,
or a control has no name, or a preference is ignored.

---

## 1. Colour comes from tokens, never from literals

The palette lives in two blocks at the top of `studio/ui/src/styles/tokens.css`:

```
:root { ... }                                  /* light palette + shared values */
[data-theme="dark"], :root:not([data-theme="light"]) { ... }   /* dark palette */
```

The product is dark first: an unstamped document gets the dark palette, and
`data-theme="light"` opts out. Both blocks declare the **same colour names**
with different values. That is the whole mechanism, and it only works if
components reference tokens rather than colours.

Tokens reach components through `@theme inline` in
`studio/ui/src/styles/index.css`, which maps each one onto a Tailwind utility.
`bg-canvas` compiles to `var(--studio-canvas)` rather than to a baked colour,
which is what makes the theme switch free: the utility resolves at use time,
through whichever palette is live. **No colour in this interface needs a
`dark:` variant.**

### Canonical tokens

| Group | Tokens |
|---|---|
| Ground | `--studio-canvas`, `--studio-ink`, `--studio-raised`, `--studio-soft` |
| Borders | `--studio-border`, `--studio-border-strong` |
| Text | `--studio-text`, `--studio-text-secondary`, `--studio-text-muted` |
| Signal | `--studio-orange`, `--studio-green`, `--studio-blue`, each with a `-subtle` variant |
| Signal as text | `--studio-orange-text`, `--studio-green-text` |
| On a signal fill | `--studio-on-signal` |
| Chart | `--studio-chart-1` |
| Shape | `--studio-radius-sm` 4px, `--studio-radius-md` 6px, `--studio-radius-lg` 8px |
| Motion | `--studio-motion-fast`, `--studio-motion-standard`, `--studio-motion-expressive`, plus easing curves |

### A signal used as text is a different step

This is the one that keeps being rediscovered. A signal colour that reads
perfectly as a fill fails as text on the same surface, because the contrast
requirement is four and a half to one rather than three.

Measured: orange at `#e9552c` on the light canvas is 3.01:1; green at `#168a61`
is 3.6:1. Both are fine as a bar or a border and neither may carry a word. So
each has a darker step for text, and `--studio-on-signal` is the near black
that labels sit in when they are *on* an orange fill, because white on orange
measured 2.85:1 in dark and 3.62:1 in light.

**If you need a colour that does not exist, add it to both palette blocks.** Do
not add it to `:root` alone, or the dark theme will inherit a light value.
Theme-neutral values, fonts, radii, easing, durations, are correctly declared
once; a colour never is.

## 2. Structure belongs in the stylesheet

Two ratchets guard this, both frozen at today's count:

| Debt | Ceiling |
|---|---|
| Hex literals in components | 0 |
| Inline `style={}` props | 6 |

The tests fail if a count rises. When you reduce one, lower the ceiling in the
test.

The previous interface carried 42 hex literals and 365 inline styles, and these
ceilings are not an invitation to spend the difference. Every one of the six
inline styles is computed geometry: where a measured fold rule sits, where a
toolbar follows a selection, how tall a revealed paragraph is, how far along a
progress bar the server says a task is. None of those is expressible as a
class, which is the one case this rule was never arguing with. A colour or a
spacing value appearing there is the regression it counts.

Why it matters: a colour written into a component cannot follow the theme, and
an inline style cannot be overridden by a class or a media query. Both are how
a themed interface quietly stops being themed.

## 3. Accessibility floor

| Rule | Enforced by |
|---|---|
| A button whose only content is a glyph carries `aria-label` | `test_icon_only_buttons_have_an_accessible_name` |
| Decorative glyphs carry `aria-hidden="true"` | `test_decorative_glyphs_are_hidden_from_assistive_technology` |
| Keyboard focus is visible via `:focus-visible` | `test_keyboard_focus_is_visible` |
| Animation honours `prefers-reduced-motion` | `test_reduced_motion_preference_is_honoured` |
| A scrollable region is reachable from the keyboard | measured, see below |

That first check was itself broken for most of its life, which is worth
recording because the failure mode is the one this whole page is about. It
found the end of a button's opening tag with `source.find(">")`, and every
button in this interface is written with an arrow handler, so the `>` it found
belonged to `onClick={() => ...}`. The "body" it then searched began in the
middle of the attribute list, the leftover `className` string counted as
visible text, and the guard passed all 58 buttons without ever reading one.
Planting an icon-only unnamed button confirmed it passed that too.

It now scans to the first `>` at brace depth zero outside a string, and
`test_the_accessible_name_guard_is_not_vacuous` plants the defect and asserts
the detection, because a guard that cannot fail protects nothing.

Fourteen icon-only buttons previously announced as nothing but "button", and
125 decorative glyphs were read aloud as unnamed images. Focus was invisible
throughout: there was no `:focus-visible` rule anywhere in 5,600 lines of CSS.

The static checks above are cheap and run on every commit, but they are
approximations. The real measurement is `axe-core`, which `studio/ui` carries
as a devDependency so it never enters the bundle:

```js
await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa'] } })
```

Run it across every surface in **both** themes. It found 97 violations the
static checks could not see, 96 of them from a single token, and it is how the
contrast steps in section 1 were chosen. Surfaces are at zero; keep them there.

Two things that only a real sweep catches: an opacity modifier on muted text
(`text-ink-muted/70`) puts it straight back under the floor, and a region that
scrolls but holds no focusable child cannot be reached without a pointer.

## 4. Integrity of what actually ships

Two structural checks run against the build output, because both failure modes
are silent and total:

- **Unbalanced braces** in the stylesheet discard every rule after the error.
- **Malformed markup** reparents everything after it, and the React mount point
  has to survive.

A third checks that the built page fetches nothing from outside this machine.
The product claims zero cloud egress, and the previous interface opened three
connections to Google for fonts on every launch, which an air-gapped machine
cannot complete, so the typography silently degraded as well.

TypeScript covers the class of failure that used to need a parser: a duplicated
`catch` block once left `app.js` unparseable, so the browser aborted the entire
file and nothing rendered, while every Python test stayed green.

## 5. Rendering a document

The docs surface reads 38 markdown files and used to print each one as a single
`<pre>` element. Across that corpus it meant 798 table rows, 182 fence lines,
1,266 bullets and 1,226 bold runs reached the reader as literal markdown
characters, and the six row penalty table in module 01 is the content of the
algorithmic audit section rather than an aside.

`studio/ui/src/lib/markdown.ts` parses a document into typed blocks and
`DocumentView.tsx` draws them. Two rules hold that apart from every other way
this could have been done:

**Nothing is ever handed to the HTML parser.** No `innerHTML`, no
`dangerouslySetInnerHTML`, no helper that returns markup as a string. A playbook
file is allowed to contain markup and several do: angle bracket placeholders
appear in prose and one table cell carries a literal break tag. Spans render as
React elements, so text is a text child and is escaped by construction. This is
the same reasoning `lib/snippet.ts` was written under, applied to a document
instead of a snippet. `tests/test_markdown_rendering.py` holds it at both ends.

**The dialect is decided by what is in these files, not by a spec.** Three
choices, each pinned by a test because each is one a plausible cleanup would
undo:

| Rule | Why |
|---|---|
| Underscore never emphasises | The corpus is snake_case throughout, and CommonMark's intraword rules eat identifiers out of a technical document |
| A table needs its delimiter row | Several files draw ASCII interface mocks out of pipes, and the delimiter is the only thing that tells a sketch from a table |
| Inline math needs a backslash inside it | There is no typesetter here, so math is shown as source; without the rule a price becomes an equation |

A tone on a callout comes only from the document's own `[!KIND]` marker, and a
mermaid fence is labelled as source rather than drawn, for the reason in section
6 item 4: showing something nobody wrote is the same mistake as showing a metric
nobody measured.

## 6. Adding a surface

1. Build it from tokens. No hex literals, no inline styles except measured
   geometry.
2. Give every icon-only control an `aria-label`, and every decorative glyph
   `aria-hidden="true"`.
3. If it can be filed against, give it a `screenKey` in
   `studio/ui/src/lib/navigation.ts` that the backend's registry knows, or
   annotations resolve to `unknown`.
4. Show nothing you did not measure. An uncaptured metric reads "not measured",
   never zero; a name the studio was never told is a blank, not a guess.
5. Run the contract, then look at it:

   ```bash
   cd studio/ui && npm run build
   cd ../.. && python -m pytest tests/test_react_ui_contract.py -q
   ```

   Then boot the studio and sweep it with axe in both themes. Of the defects
   found on this interface, the build caught none and the suite caught one.
   Driving it caught the rest, and none of them was visible from a diff.
