# UI Agent Workflow

> How UI decisions get made on this product, and how an agent working on the
> interface lands work without colliding with anyone else working in the repo.
>
> The visual specification is [linkedin_studio_reimagined_design.md](linkedin_studio_reimagined_design.md).
> The rules the interface is held to are [UI_CONVENTIONS.md](UI_CONVENTIONS.md)
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
| Icons | Lucide, Phosphor, Heroicons, Tabler, Iconoir | **Lucide**, as tree-shaken React components. Only referenced glyphs enter the bundle. It replaced a 37 symbol coolicons sprite that was inlined by hand, and went with the page it was inlined into. |
| Components | shadcn/ui, Radix, Origin UI, Mantine | Available now that the interface is React. shadcn copies source into the repository rather than adding a runtime dependency, which suits a product that has to audit what it ships. |
| Effects | Magic UI, Aceternity | Usable, but measured against blueprint section 18, which removes glow, gradient and "AI dashboard" language. Most of what these libraries are known for is on that list. |
| Charts | Recharts, Tremor, visx, nivo, ECharts, Observable Plot | Open. All are installable and bundle locally. Pick per surface when analytics is built, not before. |
| Landing templates | Cruip, Tailkit, Tailwind UI | Out of scope here. A marketing site is a different surface with different constraints, and none of the above applies to it. |

Fonts are the worked example. The previous interface opened three connections
to Google on every launch, which fails constraint 1 outright and, on an
air-gapped machine, silently degrades the editorial typography to system
fallbacks. The interface bundles the same faces through `@fontsource`, emitted
as woff2 beside the bundle. No behaviour changed; the requests stopped.

## 4. Where things live

```text
studio/ui/                 React source. Excluded from the artifact.
studio/ui/public/          Copied verbatim to the bundle root (manifest, icons, sw.js).
studio/frontend_next/      Build output. Gitignored, reproducible, what FastAPI serves.
```

`get_frontend_dir()` returns `frontend_next`, and nothing else. It used to
fall back to a second, vanilla page when the build was absent. That page is
gone and the fallback with it: a missing build now answers 503 naming the step
that was skipped, rather than silently serving a different interface.

That silence is worth being specific about, because it cost real time. While
the fallback existed, a build that never ran looked exactly like a build that
worked: the product booted, served a page, and passed its suite. That is how
`frontend_next` reached no artifact at all for as long as it did.

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

Phase 2 added two more of the same kind:

5. The filmstrip read `hook` from `/api/format/re-hook`, because that is the key
   `generate_10x_hooks` builds internally. The endpoint enriches each hook
   before returning it and the body arrives as `hook_text`, so every generated
   specimen rendered an empty card. **Read the endpoint's response, not the
   function that feeds it.**
6. React's `onSelect` is polyfilled rather than a real DOM event, so a
   synthetic `new Event("select")` never reaches it. Selection behaviour has to
   be driven the way a person drives it, with a real click.

One note on running the suite while another agent is working:
`test_a_second_instance_is_refused` acquires a Win32 named mutex under a fixed
global name. Two suites running at once collide on it and the second fails, in
either worktree, with nothing wrong in either. Re-run the test alone before
believing it.

## 6. Measuring what the author wrote

Never take `.length` on draft text. It is wrong in two directions at once, and
the number it produces drives the fold verdict.

| Decoration | What it does | `"abc".length` |
|---|---|---|
| none | | 3 |
| `to_sans_bold` | one astral code point per letter, so two UTF-16 units each | 6 |
| `to_strikethrough` | a combining mark inserted after each letter | 6 |

All three read as three characters. `studio/ui/src/lib/text.ts` is the only
correct way to count them, and `tests/test_composer_text_measurement.py`
executes that module against all three cases rather than checking the source
mentions it.

The backend hit the combining-mark half of this and fixed it in
`formatters.py::_measurable_text`. The surrogate-pair half does not exist in
Python, where `len()` counts code points, which is precisely why porting that
fix by reading it would have left bold broken here.

Formatting goes through the existing `/api/format/*` endpoints. A second set of
Unicode maps in the browser would drift from the first, and the fold verdict is
computed from whatever they return.

## 7. Retiring an interface

Done once, and the procedure is the reusable part.

**Prove parity first, by measurement.** Compare the endpoint families the old
interface calls against the ones the new interface calls. Completing a design
blueprint is not the same as replacing a product: the blueprint said how each
surface should look, and the diff said what the old page could actually do. It
found three placeholder sections, a Publish button that did not publish, and
roughly twenty-three unreached endpoint families, none of which the phase list
showed.

Normalise both sides carefully and confirm every hit by hand. A naive path
normaliser reported `/api/leads` and `/api/posts/{id}` as missing when both were
covered, and those false positives nearly hid the real ones.

**Then migrate the coverage, file by file, with a decision each.** Nineteen test
files referenced the old page. Each was carried across, rewritten where the
subject had moved, or retired with the reason recorded. The fast version is to
delete the ones that stop compiling and watch the suite go green with less
behind it, which is the failure this repository has been burned by twice.

Rewriting is often the better outcome. One check grepped `app.js` for a guard
inside `const verdictDisplay`; the interface renders what the audit returns
rather than deciding a label, so it now asserts the audit's behaviour. That is
stronger than what it replaced, which passed as long as the guard existed,
whatever it did.

**Clear the build directory before you believe a wheel.** A wheel built
immediately after the deletion still contained nine files from the deleted
page: setuptools does not clean `build/lib` between builds, so deleted files
persist into artifacts until it is cleared.

## 8. Landing the work

Commit to `ui/<workstream>`, never to `main`, and never rebase or force-push a
branch another agent has read.

Check what the other agent shipped before deleting anything they may have built
into. A grounding settings card landed in the vanilla page an hour before the
branch that deleted that page; merging as-is would have removed a feature that
was a day old. It was ported instead, along with its test file. The endpoint
parity diff in section 3 is what makes that checkable rather than a matter of
noticing.
