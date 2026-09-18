# Packaging, Release & Post-Install Maintenance Master Plan

> **Document ID**: `MASTER-PLAN-DISTRIBUTION-01`
> **Scope**: How Inox Hydra ships to a stranger's machine, and how it stays alive there once we have zero control over it.
> **Status**: P0 through P6 are landed and verified. Only P7, the Chrome Web Store submission, remains. See section 6.
> **Anti-Slop Compliance**: Zero em-dashes.

---

## 1. Verdict: The Product Could Not Ship (Now Fixed Through P2)

Everything in this section is the **original diagnosis**, kept as the record of why the work was done. All four blockers and the hardcoded-path issue are now resolved.

This was not a style opinion. A wheel was built from the tree as it stood, installed into a clean environment, and booted. Here is exactly what happened.

| Test | Result |
| :--- | :--- |
| `python -m build --wheel` | **"Successfully built"** (misleading, see below) |
| Frontend SPA present in the artifact | **MISSING** |
| Docs for the Docs tab present | **MISSING** |
| Chrome extension present | **MISSING** (only the build script `package_extension.py` shipped) |
| `studio/tests/` present | **SHIPPED TO USERS** (test code leaked into the distributable) |
| `from studio.backend import app` | **`ModuleNotFoundError: No module named 'database'`** |

The build reported success and produced something that could not start. That is the worst possible failure mode, because CI goes green on it.

**As of P2, the same verification passes**: the wheel installs into a virtual environment with no system site packages and serves the single page app, all 7 documentation modules, and every API endpoint, from an unrelated working directory, with user state written outside the install directory. Run `python tools/verify_package.py` to reproduce.

---

## 2. The Four Blockers (Root Causes)

### Blocker 1: User data lives inside the install directory

`studio/backend/database.py:19` resolves the database as `studio/data/linkedin_studio.db`, relative to the source file. Uploads (`studio/assets/uploads`), AI images (`studio/assets/generated`), and the credential vault resolve the same way.

**Consequence**: any update that replaces the application folder **destroys every draft, lead, and analytics record the user owns**. There is no upgrade path that does not wipe data. This single issue blocks all packaging strategies equally, so it must be fixed first.

**Fix**: split *code* from *state*.

```
%LOCALAPPDATA%\InoxHydra\          <- user state, NEVER touched by an update
    data\linkedin_studio.db
    assets\uploads\
    assets\generated\
    vault\
    logs\
<install dir>\                     <- code, replaced wholesale on update
```

Resolve this through one accessor (`studio/paths.py`) with an env override (`INOX_HYDRA_HOME`) for portable mode and tests. Nothing else in the codebase may call `os.path.dirname(__file__)` for state.

### Blocker 2: `studio/` is not a real Python package

There is no `studio/__init__.py` or `studio/backend/__init__.py`. `app.py:28-72` compensates with a 45 line `try: from .database ... except ImportError: from database ...` block, which only works when the process is started with `cwd` set to `studio/backend`. In an installed package both branches fail, which is the `ModuleNotFoundError` above.

This is also what forced the `importlib` shim in `studio/backend/rate_limiter.py` that hand loads `studio/core/rate_limiter.py` by absolute file path.

**Fix**: add the two `__init__.py` files, delete the dual import block, use real relative imports, delete the shim.

### Blocker 3: Non-Python files are not declared as package data

`frontend/`, `extension/`, and `docs/` are pure data. setuptools ships none of it by default, which is why the wheel was hollow. `DOCS_DIR` (`app.py:1135`) additionally points to `../../docs`, which is **outside** the `studio/` package and therefore unpackageable by construction.

**Fix**: move `docs/` content that the Docs tab serves to `studio/docs/`, and declare package data explicitly in `pyproject.toml`.

### Blocker 4: No single source of version truth

`app.py:101` declares `2.5.0`. `studio/extension/manifest.json:4` declares `2.0.0`. Nothing reconciles them.

**Fix**: one `studio/__version__.py`. FastAPI reads it, the manifest is generated from it at build time, the release tag is derived from it. A version mismatch becomes impossible rather than merely discouraged.

### Bonus blocker: your username is in the shipped docs

`README.md`, `docs/GETTING_STARTED.md`, and `docs/ENTERPRISE_USAGE.md` contain absolute links of the form `file:///c:/Users/remoteadmin/Downloads/Linkedin%20strategy/...`. `create_desktop_shortcut.vbs:4` hardcodes the same path.

Every user gets dead links pointing at a machine they do not own, and your Windows username ships with the product. Replace with repo relative links.

---

## 3. The Chosen Distribution Path (One Path, Not A Menu)

**Portable ZIP containing an embedded Python runtime, published on GitHub Releases.**

The actual application is tiny: `studio/backend` 1.1 MB, `frontend` 412 KB, `extension` 75 KB. All the weight is runtime and dependencies.

```
InoxHydra-2.5.0-win64.zip    40.8 MB compressed, 97 MB extracted (measured)
    runtime\        CPython 3.13.14 embeddable distribution
    lib\            53 vendored dependency entries
    app\studio\     the application package, 66 files
    extension\      unpacked MV3 source, for the store submission
    InoxHydra.bat   launcher
    README.txt      quick start and upgrade instructions
    create_desktop_shortcut.vbs
```

User experience: unzip anywhere, double click, done. No admin rights, no Python install, no installer.

**Why not the alternatives**, briefly, so this is not relitigated:

| Option | Rejected because |
| :--- | :--- |
| PyInstaller one file | Unsigned bootloaders trigger antivirus false positives. You have zero support channel to talk a user through a quarantine. Code signing is 200 to 400 USD per year. |
| `pip install` / `pipx` | Requires a working Python toolchain. Your buyers are LinkedIn creators, not developers. |
| MSIX / winget | Requires code signing, and store review conflicts with an extension that reads session cookies. |
| Electron / Tauri wrapper | Adds 100 MB and a second runtime to maintain. `launch_studio.bat` already achieves native window feel via `chrome --app=`. |

The portable ZIP also has the property that matters most for a zero egress product: **it keeps working forever, offline, with no server on our side.**

---

## 4. The Chrome Extension Problem (Hard Deadline)

This is the one genuinely blocking external constraint, and it is time sensitive.

**As of Chrome 149 (June 2026), Chrome disables extensions after a browser update when they were loaded unpacked in developer mode, or sideloaded from a `.crx` file.** Both are the distribution methods the project currently assumes (`docs/GETTING_STARTED.md:46-49` walks the user through Developer mode plus "Load unpacked").

That means the current extension distribution model is already broken for end users, and will silently disable itself on their next Chrome update.

**Decision: publish to the Chrome Web Store as an *unlisted* item.**

- Unlisted means it does not appear in store search. Only people holding the link can install it.
- It still receives automatic updates and does not get disabled.
- Cost is a one time 5 USD developer registration.
- Review risk is real, because the extension requests `cookies` and `webRequest` over `*.linkedin.com`. Mitigate by writing a precise privacy justification: data never leaves `127.0.0.1`, no remote code, no analytics. That claim is true here, which is an advantage most extensions do not have.

Keep the unpacked folder in the ZIP as a documented fallback for advanced users, but it cannot be the primary path.

---

## 5. Maintenance After You Lose Control

This is the actual question: once a stranger installs this, nobody can log in and fix it. The answer is to make the software self-diagnosing and self-repairing, and to make its data format forward safe.

### 5.1 Schema migrations via `PRAGMA user_version`

Today `init_db()` migrates by sniffing `PRAGMA table_info(leads)` and conditionally issuing `ALTER TABLE` (`database.py:236-265`). That works exactly once, cannot be reasoned about, and has no concept of "which version is this database".

Replace with a numbered, forward only migration ledger:

- Migrations are immutable numbered scripts in source control. Never edit a shipped migration.
- On startup, read `PRAGMA user_version`, apply every higher numbered migration **in order**.
- Each migration and its `user_version` bump happen **inside one transaction**. On any error, roll back and refuse to start rather than continuing on a half understood schema.
- **Back up the database file before the first migration of any run**, timestamped. This is the user's undo button and costs nothing.
- The app declares `MIN_SCHEMA` and `MAX_SCHEMA` it can open. If `user_version > MAX_SCHEMA`, refuse to open and tell the user their data is from a newer version. This protects the user who rolls back a release.

Treat the schema version as a compatibility contract, not a counter you increment when you remember.

### 5.2 Update delivery, opt-in, reusing what you already built

`studio/backend/intelligence_sync.py` already implements conditional HTTP GET against a GitHub Releases CDN with `If-None-Match` and 304 handling at zero cost. That is exactly the right mechanism for version checks. Point it at a `version.json` on the releases CDN.

**It must be opt-in and off by default.** A product whose headline promise is zero cloud egress cannot silently phone home. Ask on first run, store the answer, honor it. When an update exists, show a banner with a changelog link. The user downloads and swaps the folder. Their data in `%LOCALAPPDATA%` is untouched by construction.

### 5.3 Diagnostics without telemetry

You will never receive a crash report. So the user must be able to generate one on demand.

`inox doctor --bundle` produces a single redacted file containing: app and schema version, Python and OS version, table row counts, migration history, last 200 log lines, and the AI config **with keys stripped**. The user attaches it to a GitHub issue. This is the only honest substitute for observability in an air gapped product, and it must be built before release, not after the first angry user.

### 5.4 Self-service commands

Nobody can help them, so the CLI must:

| Command | Purpose |
| :--- | :--- |
| `inox backup` / `inox restore <file>` | Full state snapshot and rollback |
| `inox export` | Portable JSON or CSV of drafts, leads, analytics. Guarantees no lock in. |
| `inox doctor` | Health check plus the diagnostic bundle above |
| `inox reset --keep-data` | Repair a corrupt config without data loss |
| `inox migrate --dry-run` | Show pending migrations before committing to them |

### 5.5 Versioning contract

Semantic versioning where **MAJOR is reserved for a schema break that cannot be migrated forward**. MINOR adds features and forward safe migrations. PATCH is fixes only. Publish a `CHANGELOG.md` per release. Users with no support channel need to read what changed before they upgrade.

---

## 6. Execution Order

Each phase is independently shippable and leaves the tree green. Do not start a later phase before an earlier one lands.

| Phase | Work | Gate |
| :--- | :--- | :--- |
| **P0 DONE** | `studio/backend/paths.py`, state resolves outside the install dir, `INOX_HYDRA_HOME` override | **Met.** Full suite green, `tests/test_paths_and_state_isolation.py` proves data survives a simulated folder replacement |
| **P1 DONE** | Added `studio/__init__.py` and `studio/backend/__init__.py`, fixed `gstack_governance.py`, demoted the `importlib` shim to a fallback | **Met.** `studio.backend.app` imports from any cwd (95 routes), locked by `tests/test_package_importability.py` |
| **P2 DONE** | `pyproject.toml` with explicit packages and package data, `tools/prepare_package.py` stages served docs into `studio/docs/`, `tools/verify_package.py` proves it | **Met.** Wheel installs into a venv with no system site packages and serves the SPA, all 7 doc modules and every API from an unrelated cwd |
| **P3 DONE** | `tools/sync_version.py` propagates the single source into `manifest.json`, 20 absolute links rewritten relative, `create_desktop_shortcut.vbs` self-resolves | **Met.** `tests/test_version_and_paths_hygiene.py` proves no absolute user path survives in any shipped surface and every rewritten link resolves |
| **P4 DONE** | `studio/backend/migrations.py` ledger, baseline adoption, transactional apply, pre-migration backup, downgrade refusal | **Met.** `tests/test_schema_migrations.py` covers upgrade from a pre-ledger database, rollback on failure, backup contents, and both refusal paths |
| **P5 DONE** | `tools/build_portable.py` produces the ZIP, `tools/smoke_portable.py` drives it with a scrubbed environment, `.github/workflows/release.yml` builds and publishes on a tag | **Met.** A 40.8 MB ZIP boots from its own embedded CPython, serves the UI, docs and APIs, and writes state to `%LOCALAPPDATA%` |
| **P6 DONE** | `studio/backend/support.py`, `studio/backend/updates.py`, `studio/cli.py`, 8 API endpoints, `InoxHydra-CLI.bat` in the artifact | **Met.** Full flow run end to end, including destroying data and recovering it from a backup. Redaction proven against planted credentials |
| **P7** | Chrome Web Store unlisted submission | Extension survives a Chrome update |

**P0 and P1 are the only ones that are truly urgent**, because every additional day of Day 05 through Day 17 feature work written against the current path model and import model increases the cost of both. Both are now landed, so Day 05 onward can be written against the correct models.

### Deferred out of P1, deliberately

The `try: from .x import ... except ImportError: from x import ...` blocks in 14 backend files were **kept**, not deleted as originally scoped.

Deleting them requires rewriting the import style of 18 of the 23 test files, because they import backend modules top-level (`from database import get_db`). Mixing the two styles in one process creates two distinct module objects for the same file, which would silently duplicate the module-level singletons (`rate_limiter`, `write_actor`, `event_bus`, `linkedin_client`, `ingress_daemon`, `reverse_crm`, `gstack_engine`). That is a subtle, hard to debug class of failure, and it buys tidiness rather than capability.

The blocks are ugly but they are a working dual-mode shim, and the P1 gate is met with them in place. Collapse them as a standalone cleanup when the test suite is not also being extended daily, not as a rider on a packaging phase.

### What P2 uncovered

The clean-install gate found two dependencies that the running application requires but the metadata never declared:

- **`apscheduler`**, imported at module scope by `scheduler.py`, which `app.py` imports unconditionally. A clean install failed at import time.
- **`python-multipart`**, required by FastAPI for the `UploadFile` and `Form` endpoints that power the media dropzone. A clean install imported fine and then raised at the first upload.

Both were present in the development environment as somebody else's transitive dependency, which is precisely why a normal test run could never have caught them. `tests/test_packaging_manifest.py` now guards the declaration list, and the `package-verify` CI job runs the full build-install-boot cycle on every push.

The wheel went from 39 entries shipping no frontend, no docs and a copy of the test suite, to 69 entries shipping the complete application and no test code.

### What P3 changed

Version now has exactly one author: `studio/__version__.py`. The FastAPI application and the packaging metadata import it directly. `tools/sync_version.py` propagates it into the Chrome extension manifest and validates that the result is a version Chrome will actually accept (one to four integers, each 0 to 65535), so a value like `2.5.0-beta` fails at build time rather than at the user's install. `--check` mode runs in CI and fails the build on drift. `tools/prepare_package.py` propagates before packaging, so a built artifact cannot contain a drifted manifest.

The extension service worker now logs `chrome.runtime.getManifest().version` instead of a baked-in `v2.5` literal.

Twenty `file:///c:/Users/<developer>/Downloads/Linkedin%20strategy/...` links in README.md, GETTING_STARTED.md and ENTERPRISE_USAGE.md were rewritten to repository relative paths, and the test suite verifies every one of them resolves to a file that exists. `create_desktop_shortcut.vbs` now derives the install directory from `WScript.ScriptFullName`, so it produces a working shortcut wherever the user unzipped, and it fails with a readable message instead of creating a broken shortcut if it is moved away from the launcher.

Note that `registry.py` carries its own `"version": "2.0.0"`. That is an agent schema version, a different concept, and was deliberately left alone.

### What P4 changed

`PRAGMA user_version` is now the database's schema version, and `studio/backend/migrations.py` is the only place schema changes may be authored.

**Version 1 is the baseline**: the schema `init_db()` already produced. That choice is what makes adoption safe. Every database in existence already matches it, so the ledger stamps them rather than rebuilding them. The live development database went from `user_version = 0` to `1` with all 22 tables and their rows untouched.

The guarantees, each covered by a test:

- A migration and its version bump commit in **one transaction**. A migration that fails halfway rolls back both, so a database is never left at a version whose schema it does not actually have. Verified with a deliberately half-valid migration.
- A **timestamped backup** is taken before the first migration of any run, using the SQLite backup API rather than a file copy, so it is consistent under WAL with readers active. The test opens the backup and confirms it holds the pre-migration state.
- A database **newer than the build is refused**, not opened. This protects the user who takes an update, dislikes it, and reinstalls the previous version. The error names the backups directory, because that message is the entire support channel.
- A database **older than `MIN_SUPPORTED_SCHEMA` is refused** rather than migrated down a path the build no longer carries.
- `PRAGMA` cannot bind parameters, so the version is interpolated. It is validated as a non-negative integer first, and the test feeds it `"1; DROP TABLE posts"` to prove the guard holds.

`GET /api/v1/schema/status` reports current version, target, pending migrations and actionable advice. The diagnostics bundle in P6 will include it.

`database.py` now carries an explicit rule in its module docstring: the DDL there is the frozen baseline, and everything after it is a numbered migration.

### Loose ends from earlier phases, resolved or consciously left

- **Fixed**: the P0 update-survival test leaked an empty temporary directory on every run.
- **Not needed**: `studio/extension/package_extension.py` was flagged as a build tool living in shipped source. P2's explicit package list already excludes it from the wheel (verified against a real build), so moving it would be churn against a live test import for no gain.
- **Still deferred**: collapsing the 14 dual-import blocks, for the reasons given under P1. The concurrent addition of `docs_engine.py`, seed days 05 through 11 and several test files during this work is exactly the churn that makes a 32-file import rewrite a bad trade right now.
- **Still open, your call**: `studio/data/linkedin_studio.db` remains tracked in git. A live database carrying leads does not belong in version control, but removing it changes what a fresh clone does, so it is a decision rather than a cleanup.

### What P5 produced

A real artifact, measured rather than estimated: **40.8 MB compressed, 97 MB extracted.**

It was extracted to a scratch directory and driven using only its own embedded interpreter, with every `PYTHON*` variable removed and `PATH` reduced to the Windows system directories, so nothing on the host could quietly supply a missing piece. Under those conditions it imported `sqlite3`, `ssl` and `ctypes` from the bundled runtime, imported all vendored dependencies, registered 96 routes, served the 142 KB single page app and all 7 documentation modules, created its database at `%LOCALAPPDATA%\InoxHydra`, and stamped the schema ledger.

A live server was also started from the bundled runtime (not just an in-process test client) and answered real HTTP requests on `/`, `/api/posts` and `/api/v1/schema/status`.

**The single most consequential line in the build** is the exclusion of `studio/data` from the artifact. Its absence is what makes `paths.get_app_home()` resolve to the user profile, which is what allows the update procedure (delete the folder, extract the new one) to leave the user's work alone. The builder asserts it, the smoke test refuses an artifact containing it, and a unit test guards the exclusion list. That is three independent checks on one property, which is proportionate given that getting it wrong destroys user data silently.

`.github/workflows/release.yml` builds on `windows-latest`, which is not optional: the artifact embeds ABI-specific compiled wheels, so a Linux runner would produce a ZIP that cannot import pymupdf, pillow or pydantic-core while still reporting a successful build. A test asserts the runner choice. The workflow also refuses to publish when the git tag disagrees with `studio/__version__.py`, and gates the release behind the test suite, `verify_package.py` and `smoke_portable.py`.

The artifact's `README.txt` documents where data lives, how to upgrade, how to opt into true portable mode, and why the extension must come from the store rather than being loaded unpacked.

### Fixed along the way

`tests/test_phase4_algorithmic_safety.py` scanned the entire tree for em-dashes, including build output. Once a portable artifact existed, it failed on 13 vendored third party files (fastapi, pydantic, pymupdf, requests, idna, charset_normalizer) that we neither author nor ship as our own content. Its exclusion set now skips build directories. The fix was verified by planting a real violation in project code and confirming it is still caught.

### What P6 delivered

The support model for a product with no support channel. All of it reachable three ways: `python -m studio.cli`, `InoxHydra-CLI.bat` in the portable artifact, and eight REST endpoints under `/api/v1/support` and `/api/v1/updates` for the Settings tab.

**Redaction is treated as a security property, not a courtesy.** The diagnostics bundle is designed to be pasted into a public GitHub issue, and the database behind it holds the user's LinkedIn session cookies and AI provider key. It uses an **allowlist**, because a denylist fails open: the day somebody adds `gemini_api_key` to the settings table, a denylist silently starts leaking it and nobody finds out until a user has already posted it in public.

This was verified rather than asserted. Real-looking credentials were planted (`li_at`, `JSESSIONID`, `sk-proj-...`), a bundle was generated, and the output was grepped for each one. All absent. The same check was run against the data export. Redacted entries still report `is_set` and `length`, because "the key is missing" and "the key is set but wrong" are different bugs and we have to tell them apart without ever seeing the value.

**The full flow was run end to end**, including the destructive path: seed an installation, run `doctor`, take a backup, delete every draft, attempt `restore` without `--yes` (correctly refused, exit 1), restore with `--yes`, and confirm all 7 drafts came back. Restoring takes a safety snapshot of the current state first, because a user restoring the wrong archive is otherwise the one failure nobody can rescue them from.

`reset` clears configuration and leaves content untouched, verified by row counts. Destructive reset is deliberately `NotImplementedError`: there is no undo for it.

**Update checks are off by default and enforced as such.** A test replaces `requests.get` with a function that raises, then calls the checker and asserts it returns without touching the network. Another test greps `updates.py` for `subprocess`, `zipfile`, `exec` and `eval`, so the module can never quietly grow the ability to install what it finds. It reports a version and a link; the user swaps the folder themselves, which is safe because their data is outside it by construction.

`release/latest.json` is the manifest opt-in clients read, and `tools/sync_version.py` now keeps it in step with `studio/__version__.py` alongside the Chrome manifest. Both surfaces drift-check in CI. Version comparison is numeric, so 2.10.0 correctly ranks above 2.9.0, and a malformed remote manifest degrades rather than crashing startup.

### Fixed along the way

- `sync_version.py` tracebacked at the user on a malformed `latest.json`. It now reports the line and column and refuses to rewrite a file it cannot parse.
- `doctor` reported "migrations pending" on a fresh install that simply had no database yet, which reads as a fault when nothing is wrong. It now says "not initialized (created on first launch)".

### New rule for Day 05 onward

`tests/test_package_importability.py` will fail any new backend module that imports a sibling without a package-relative path. `gstack_governance.py` shipped broken in exactly that way and nothing caught it, because `app.py`'s try/except masked the real error. That hole is now closed.

---

## 7. What This Plan Deliberately Does Not Do

- No license keys, no activation, no seat management. Those require a server, which contradicts the zero egress promise and creates an attack surface plus a support burden you cannot staff.
- No telemetry or usage analytics, for the same reason. Section 5.3 is the replacement.
- No auto-applying updater that rewrites its own install directory. On Windows that path is full of file locking and permission failure modes, and a failed self update on a machine you cannot reach is unrecoverable. Download plus manual swap is boring and it works.
