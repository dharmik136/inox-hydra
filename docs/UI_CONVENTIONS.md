# UI Conventions

> The rules the studio interface is held to, and what to do when you add a
> surface to it. Icons have their own document: [ICON_SYSTEM.md](ICON_SYSTEM.md).

`tests/test_ui_visual_contract.py` enforces everything on this page. Every rule
here was added because it had already been broken in shipped code.

---

## 1. Colour comes from tokens, never from literals

The palette lives in two blocks at the top of `studio/frontend/styles.css`:

```
:root { ... }                                  /* light palette + aliases */
[data-theme="dark"], :root:not([data-theme="light"]) { ... }   /* dark palette */
```

The product is dark first: an unstamped document gets the dark palette, and
`data-theme="light"` opts out. Both blocks declare the **same token names** with
different values. That is the whole mechanism, and it only works if components
reference tokens rather than colours.

### Canonical tokens

| Group | Tokens |
|---|---|
| Ground | `--bg-canvas`, `--bg-ink`, `--bg-raised`, `--bg-soft` |
| Borders | `--border-subtle`, `--border-strong`, `--border-focus` |
| Text | `--text-primary`, `--text-secondary`, `--text-muted`, `--text-dim` |
| Signal | `--signal-orange`, `--signal-green`, `--signal-blue`, `--accent-indigo` (each with a `-subtle` variant) |
| Shape | `--radius-sm` 4px, `--radius-md` 6px, `--radius-lg` 8px |
| Motion | `--motion-fast`, `--motion-standard`, `--motion-expressive`, plus easing curves |

### Semantic aliases

Components were written against a second family of names that nobody had
declared, so **16 `var()` references resolved to nothing**: borders disappeared,
panels fell back to transparent, corners rendered square. Rather than rewrite
every component, the aliases now exist and point at canonical tokens:

```css
--bg-surface: var(--bg-ink);
--bg-surface-elevated: var(--bg-raised);
--border-medium: var(--border-strong);
--signal-emerald: var(--signal-green);
```

An alias points at a token, never at a literal. That is what keeps it correct in
both themes: the alias resolves at use time, through whichever palette is live.

**If you need a colour that does not exist, add it to both palette blocks.** Do
not add it to `:root` alone, or the dark theme will inherit a light value.

## 2. Structure belongs in the stylesheet

Two ratchets guard this, both frozen at today's count:

| Debt | Ceiling |
|---|---|
| Hex literals in `app.js` | 42 |
| `style="` in `index.html` | 284 |
| `style="` injected by `app.js` | 81 |

The tests fail if a count rises. They do not demand the debt be paid, only that
it stops growing. When you reduce one, lower the ceiling in the test.

Why it matters: a colour written into a script cannot follow the theme, and an
inline style cannot be overridden by a class or a media query. Both are how a
themed interface quietly stops being themed.

## 3. Accessibility floor

| Rule | Enforced by |
|---|---|
| A button whose only content is a glyph carries `aria-label` | `test_icon_only_buttons_have_an_accessible_name` |
| Decorative glyphs carry `aria-hidden="true"` | `test_decorative_glyphs_are_hidden_from_assistive_technology` |
| Keyboard focus is visible via `:focus-visible` | `test_keyboard_focus_is_visible` |
| Animation honours `prefers-reduced-motion` | `test_reduced_motion_preference_is_honoured` |

Fourteen icon-only buttons previously announced as nothing but "button", and 125
decorative glyphs were read aloud as unnamed images. Focus was invisible
throughout: there was no `:focus-visible` rule anywhere in 5,600 lines of CSS.

The focus ring uses `--border-focus` and is scoped so pointer users keep the old
look:

```css
:focus-visible { outline: 2px solid var(--border-focus); outline-offset: 2px; }
:focus:not(:focus-visible) { outline: none; }
```

## 4. Markup and stylesheet integrity

Two structural checks run on every build, because both failure modes are silent
and total:

- **Unbalanced braces** in the stylesheet discard every rule after the error.
- **A stray closing tag** in the markup reparents everything after it.

A related failure already cost the whole interface once: a duplicated `catch`
block left `app.js` unparseable, so the browser aborted the entire file and
nothing rendered, while every Python test stayed green.
`tests/test_frontend_js_syntax.py` parses the shipped JavaScript with Node to
stop that recurring.

## 5. Adding a surface

1. Build it from tokens. No hex literals, no inline styles.
2. Give every icon-only control an `aria-label`, and every decorative glyph
   `aria-hidden="true"`.
3. Use a class from the size ramp for icons, never a hardcoded width.
4. Run the contract:

   ```bash
   python -m pytest tests/test_ui_visual_contract.py tests/test_icon_system.py \
                    tests/test_frontend_js_syntax.py -q
   ```

## 6. Known debt, deliberately not fixed

Recorded so it is a decision rather than an oversight.

| Debt | Why it stands |
|---|---|
| 365 inline styles across the markup and scripts | Unpicking them is a refactor, not a fix. Ratcheted so it cannot grow. |
| 42 hex literals in `app.js` | Same. Most are status colours that should become `--signal-*` tokens. |
| `sym-act-publish` defined but unreferenced | Kept deliberately: publish-now is wired in the queue and the glyph is expected to be used again. |
