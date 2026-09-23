# UI Agent Workflow

> How UI decisions get made on this product, and how an agent working on the
> interface lands work without colliding with anyone else working in the repo.
>
> The visual specification is [linkedin_studio_reimagined_design.md](linkedin_studio_reimagined_design.md).
> The rules the vanilla interface is held to are [UI_CONVENTIONS.md](UI_CONVENTIONS.md)
> and [ICON_SYSTEM.md](ICON_SYSTEM.md). This document is the decision procedure,
> not the design.

---

## 1. Isolation: two agents, one repository

More than one agent works in this repository. `git checkout -b` in a shared
working tree swaps files underneath whoever else is mid-edit, so the branch for
interface work is checked out as a **worktree in a separate directory**:

```bash
git worktree add -b ui/<workstream> ../inox-hydra-ui main
```

The worktree lives **outside the repository root**, and that placement is not
cosmetic. `copy_application()` in `tools/build_portable.py` copies the working
tree rather than the git index, so a worktree created inside the repository
would be staged into every locally built portable artifact: a second complete
copy of the application, plus its git metadata, inside the zip.

The same rule produced the two build entries this branch added. Anything new
that lands under `studio/` must go in **both** `.gitignore` and
`STUDIO_EXCLUDE`, because the two protections look equivalent and are not.
`.gitignore` governs what git tracks; `STUDIO_EXCLUDE` governs what ships.
`studio/ui/node_modules` is hundreds of megabytes and is caught by both.

## 2. The constraint order

Every interface decision is filtered through these, in order. A choice that
fails an earlier test is not rescued by being better on a later one.

| # | Constraint | What it rejects |
|---|---|---|
| 1 | **Zero cloud egress at runtime** | Anything the shipped page fetches from a host that is not this machine. CDN scripts, remote stylesheets, webfonts, telemetry, hosted icon APIs. |
| 2 | **Nothing invented on screen** | Placeholder metrics, sample names, plausible-looking counts, a "Saved" mark that no write produced. |
| 3 | **Colour comes from tokens** | Hex literals in components, theme branching in JavaScript, a colour declared in one palette block and not the other. |
| 4 | **The accessibility floor** | Icon-only controls with no accessible name, decorative glyphs read aloud, invisible focus, motion that ignores `prefers-reduced-motion`, an overlay with no keyboard exit. |
| 5 | **Taste** | Everything still standing. |

Constraint 1 is the product's headline claim, so it is worth being concrete
about what "at runtime" means: build-time network access is fine. `npm install`
reaches the registry, and that is a developer's machine, not a user's. What must
never happen is the *running studio* opening a connection to anything but
localhost.

Constraint 2 has its own enforcement elsewhere in this repository
(`tests/test_no_fabricated_metrics.py`), and a run of commits about surfaces
that reported success without performing the work. An interface that cannot yet
show something says so in plain words. It does not render a convincing shell
over nothing.

## 3. How a library gets adopted

Vendor it, or do not use it.

A dependency is acceptable when it can be installed at build time and emitted
into the bundle as local files. It is unacceptable when the running page must
reach a host to use it, no matter how reliable that host is.

Applying that to the reference table the product was evaluated against:

| Want | Candidates | Decision |
|---|---|---|
| Icons | Lucide, Phosphor, Heroicons, Tabler, Iconoir | **Lucide**, as tree-shaken React components. Only referenced glyphs enter the bundle. The vanilla interface keeps its 37 symbol coolicons sprite; the two sets are never mixed inside one surface. |
| Components | shadcn/ui, Radix, Origin UI, Mantine | Available now that the interface is React. shadcn copies source into the repository rather than adding a runtime dependency, which suits a product that has to audit what it ships. |
| Effects | Magic UI, Aceternity | Usable, but measured against blueprint section 18, which removes glow, gradient and "AI dashboard" language. Most of what these libraries are known for is on that list. |
| Charts | Recharts, Tremor, visx, nivo, ECharts, Observable Plot | Open. All are installable and bundle locally. Pick per surface when analytics is built, not before. |
| Landing templates | Cruip, Tailkit, Tailwind UI | Out of scope here. A marketing site is a different surface with different constraints, and none of the above applies to it. |

Fonts are the worked example. `studio/frontend/index.html` opens three
connections to Google on every launch, which fails constraint 1 outright and,
on an air-gapped machine, silently degrades the editorial typography to system
fallbacks. The React interface bundles the same faces through `@fontsource`,
emitted as woff2 beside the bundle. No behaviour changed; the requests stopped.

## 4. Where things live

```text
studio/ui/                 React source. Excluded from the artifact.
studio/ui/public/          Copied verbatim to the bundle root (manifest, icons, sw.js).
studio/frontend_next/      Build output. Gitignored, reproducible, what FastAPI serves.
studio/frontend/           The vanilla interface. Still the fallback.
```

`get_frontend_dir()` prefers `frontend_next` when it contains an `index.html`,
and falls back to `frontend` otherwise. The check is for the file rather than
the directory, because an interrupted build leaves the directory behind with
nothing servable in it, and falling back then is the difference between the old
interface and a blank page.

Two collisions to know about:

- Vite's asset directory is `static`, not the default `assets`. `app.py` mounts
  `/assets` to `studio/assets` **before** the SPA, and Starlette resolves mounts
  in registration order, so a bundle under `/assets` would sit behind a mount
  that does not contain it.
- Everything the old page served still has to be served. The PWA manifest,
  icons and service worker were carried into `studio/ui/public/`; missing them
  broke `test_desktop_integration.py` and, less visibly, installability.

## 5. Verification before anything is called done

```bash
cd studio/ui && npm run build     # tsc -b, then vite build
cd ../.. && python -m pytest -q   # the whole suite, not a subset
```

`paths.py` is imported almost everywhere, so a change to what gets served is a
change to a shared dependency. Run everything.

Then **look at it**. Boot the studio on a port other than 8000, since another
agent may be holding the default, and drive the real interface:

```bash
INOX_HYDRA_HOME="$PWD/scratch/_shot_home" \
  python -m uvicorn studio.backend.app:app --host 127.0.0.1 --port 8123
```

Set `INOX_HYDRA_HOME` or the probe writes a database into the source checkout.
Capture both themes, open every overlay, and check the console for errors.

This step is not ceremonial. Of the defects on this branch, the build caught
none and the test suite caught one. Driving the interface caught four:

1. The command palette had no `Escape` handler, so the only way out was
   clicking the scrim. `cmdk` ships this in `Command.Dialog`; a bare `Command`
   inside a custom animated overlay binds nothing.
2. `#root` had no height, so `h-full` on the shell measured an auto-height box
   and the rail and inspector stopped short of the viewport.
3. The fold annotation was drawn over the sentence it annotates. It belongs in
   the margin, which is where blueprint section 7B puts the ruler anyway.
4. A Tailwind arbitrary variant was carrying a **component** class
   (`[&_[cmdk-group-heading]]:studio-label`). Arbitrary variants can only apply
   utilities, so the rule compiled to nothing and the headings silently kept
   their default size.

Every one of those renders and typechecks cleanly. None is visible from a diff.

## 6. Landing the work

Commit to `ui/<workstream>`, never to `main`, and never rebase or force-push a
branch another agent may have read. Keep the vanilla interface working for as
long as it is the fallback: while `frontend_next` can be absent, the old page is
what a user gets, and a half-migrated `studio/frontend` serves nobody.
