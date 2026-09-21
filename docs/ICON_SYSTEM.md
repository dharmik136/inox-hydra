# Icon System

> How the studio draws icons, where they come from, and what to do when you need
> one that does not exist yet.

The interface draws every icon from a single inline SVG sprite. There is one
sprite, one grid, one stroke weight, and one colour rule. Anything that departs
from those is a defect, and `tests/test_icon_system.py` fails the build for it.

---

## 1. Why a sprite and not icon files

The product is local first and ships as one page. An external sprite referenced
with `<use href="icons.svg#id">` does not resolve in every browser, and a
per icon `<img>` costs a request each and cannot inherit text colour. So the
sprite is inlined at the top of `studio/frontend/index.html`, inside
`<svg id="editorial-symbol-catalog" style="display: none;">`, and every icon in
the interface is a reference to it:

```html
<svg class="app-symbol app-symbol-md"><use href="#sym-sec-queue"></use></svg>
```

## 2. The contract

| Rule | Value | Why |
|---|---|---|
| Grid | `viewBox="0 0 24 24"` | Mixed grids make icons visually different sizes at the same CSS size. |
| Stroke weight | `2` | One weight, so icons sit together in a row. |
| Caps and joins | `round` | The coolicons geometry is drawn for round terminals. |
| Colour | `stroke="currentColor"` on the `<symbol>`, and **no colour on the geometry** | The icon takes the colour of whatever references it, so it follows the theme for free. |
| Fill | `fill="none"` | These are stroke icons. |

The colour rule is the one that bites. The Figma exporter emits
`stroke="white"` on every path. Left in place, every icon is invisible on the
light theme. The build step strips per path colour so the `<symbol>` can drive
it. `test_symbols_inherit_currentcolor` enforces this.

## 3. Naming

```
sym-<role>-<name>
```

| Role | Meaning | Example |
|---|---|---|
| `sec` | A destination in the studio rail | `sym-sec-queue` |
| `act` | A verb the author invokes | `sym-act-publish` |
| `mode` | A state a surface is currently in | `sym-mode-preview` |
| `brand` | The product's own mark | `sym-brand-logo` |

Two utility symbols predate the convention and are exempt by name:
`sym-refresh` and `sym-close`.

Read the role off the id and you know where the icon belongs. A new section
icon that is called `sym-act-something` will pass review and then confuse the
next person, so the naming test is not cosmetic.

## 4. Sizes

The stylesheet defines the ramp. Use a class, never a hardcoded width.

| Class | Rendered |
|---|---|
| `.app-symbol-xs` | 11px |
| `.app-symbol-sm` | 13px |
| `.app-symbol` | 14px |
| `.app-symbol-md` | 16px |
| `.app-symbol-lg` | 20px |

At 11px a 2 unit stroke on a 24 unit grid is the heaviest the set gets. If an
icon looks muddy there, it is usually too detailed for the size rather than too
heavy, so prefer a simpler glyph over a thinner stroke.

## 5. Where the glyphs come from

| | |
|---|---|
| Iconset | coolicons (Free Iconset, Community) |
| Figma file | `P1LOY4s7crnhhkWpmYGNDo`, named "Icons" |
| Retrieved via | Figma REST API |
| Credential | `FIGMA_API_KEY` environment variable |

The API key lives in the environment and is never committed. Nothing at runtime
talks to Figma: the sprite is generated once and checked in, so the application
stays air gapped.

`studio/frontend/icons.manifest.json` records, for every symbol, its role, the
coolicons glyph it came from, the Figma node id, and how many places reference
it. That file is the reason the set can be regenerated, audited, or relicensed
later without guesswork. It is verified against the sprite by the tests, so it
cannot quietly drift out of date.

## 6. Adding an icon

1. **Find the glyph.** List the file's icons and pick by name:

   ```bash
   curl -s -H "X-Figma-Token: $FIGMA_API_KEY" \
     "https://api.figma.com/v1/files/P1LOY4s7crnhhkWpmYGNDo/nodes?ids=17102:2265&depth=2"
   ```

   The icons live in frames under that canvas, named `Category / Name`.

2. **Export it as SVG.**

   ```bash
   curl -s -H "X-Figma-Token: $FIGMA_API_KEY" \
     "https://api.figma.com/v1/images/P1LOY4s7crnhhkWpmYGNDo?ids=<NODE_ID>&format=svg"
   ```

   The response carries a short lived URL. Download it.

3. **Add the symbol** to the sprite in `index.html`, in the block matching its
   role, keeping the catalog numbering in order:

   ```html
   <!-- 37. Action: Archive a draft (coolicons: File / Archive) -->
   <symbol id="sym-act-archive" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
     <path d="..."/>
   </symbol>
   ```

   Strip `stroke`, `stroke-width`, `stroke-linecap` and `stroke-linejoin` from
   the paths. The `<symbol>` supplies them.

4. **Record it** in `icons.manifest.json`, including the Figma node id.

5. **Run the contract tests.**

   ```bash
   python -m pytest tests/test_icon_system.py -q
   ```

## 7. Removing an icon

Delete the symbol, delete its manifest entry, and remove every reference. The
tests will tell you if you missed one in either direction: a reference without a
symbol draws nothing, and a manifest entry without a symbol is a lie about what
ships.

## 8. What the tests guarantee

`tests/test_icon_system.py` fails if any of these stop being true.

- Every referenced symbol is defined. *This one had already been broken:
  `sym-sec-chat` and `sym-sec-radar` were referenced by the interface but never
  defined, so those controls drew empty space, and no test looked.*
- No duplicate symbol ids.
- Names follow the role convention.
- No symbol carries its own colour.
- Every symbol uses the 24 by 24 grid and contains real geometry.
- The manifest matches the sprite exactly, records a source for every symbol,
  and keeps accurate reference counts.
- The documented size ramp exists in the stylesheet.
- No em-dashes, matching the project wide rule.

## 9. The current set

The brand mark is drawn by hand and is deliberately not an iconset glyph.
Everything else is coolicons geometry.

| Symbol | Role | Source glyph | References |
|---|---|---|---|
| `sym-brand-logo` | brand | hand-authored | 3 |
| `sym-sec-composer` | section | Edit/Edit_Pencil_Line_01 | 4 |
| `sym-sec-queue` | section | Calendar/Calendar_Days | 5 |
| `sym-sec-crm` | section | User/Users_Group | 4 |
| `sym-sec-analytics` | section | Interface/Chart_Line | 4 |
| `sym-sec-docs` | section | File/File_Document | 7 |
| `sym-sec-swipe` | section | Interface/Bookmark | 3 |
| `sym-sec-brand` | section | Edit/Swatches_Palette | 4 |
| `sym-sec-ai-command` | section | System/Terminal | 16 |
| `sym-sec-chat` | section | Communication/Chat_Conversation | 1 |
| `sym-sec-radar` | section | Navigation/Compass | 1 |
| `sym-act-copy` | action | Edit/Copy | 6 |
| `sym-act-save` | action | System/Save | 5 |
| `sym-act-export` | action | Interface/Download | 6 |
| `sym-act-eye` | action | Edit/Show | 3 |
| `sym-act-lock` | action | Interface/Lock | 4 |
| `sym-act-tag` | action | Interface/Tag | 2 |
| `sym-act-trim` | action | Edit/Crop | 2 |
| `sym-act-clean` | action | Edit/Text | 5 |
| `sym-act-spark` | action | Interface/Star | 10 |
| `sym-act-hooks` | action | Environment/Bulb | 5 |
| `sym-act-image` | action | Media/Image_01 | 3 |
| `sym-act-rhythm` | action | Interface/Trending_Up | 3 |
| `sym-act-repurpose` | action | Arrow/Arrow_Reload_02 | 1 |
| `sym-act-apply` | action | Interface/Check | 11 |
| `sym-act-eject` | action | Interface/Log_Out | 4 |
| `sym-act-publish` | action | Communication/Paper_Plane | 0 |
| `sym-act-theme-dark` | action | Environment/Moon | 1 |
| `sym-act-theme-light` | action | Environment/Sun | 1 |
| `sym-mode-audit` | mode | Warning/Shield_Check | 2 |
| `sym-mode-brand` | mode | Interface/Label | 2 |
| `sym-mode-media` | mode | Media/Image_02 | 7 |
| `sym-mode-preview` | mode | System/Monitor | 2 |
| `sym-mode-prompt` | mode | Communication/Chat_Circle_Dots | 2 |
| `sym-refresh` | utility | Arrow/Arrows_Reload_01 | 4 |
| `sym-close` | utility | Menu/Close_MD | 15 |
