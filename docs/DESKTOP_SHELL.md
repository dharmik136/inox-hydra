# The Desktop Shell

> How the studio becomes an application with a window, and why it is built the
> way it is.

---

## 1. What the shell is, and what it is not

The shell is a supervisor with a window attached. It starts the same uvicorn
process the `.bat` launcher starts, waits until that process answers, points a
WebView2 window at it, and stops it on the way out.

It implements no product behaviour. That boundary is deliberate and load
bearing: the studio has to keep working without the shell, because the browser
extension that captures LinkedIn activity only runs in a real browser. A
creator who never installs the desktop application loses nothing.

So the product has two surfaces and always will:

| Surface | Runs in | Does |
|---|---|---|
| **The Studio** | this shell, or any browser | composer, CRM, analytics, scheduler |
| **The Bridge** | the user's own Chrome or Edge | reads LinkedIn cookies, observes Voyager responses, scrapes engagers |

That is the same shape as a password manager with a browser extension. The
desktop app is not an attempt to absorb the browser.

---

## 2. Why Tauri, and why not PyInstaller

The shell is Rust and WebView2, bundled by Tauri. Two constraints decided it.

**Antivirus.** `tools/build_portable.py` already documents the reasoning: an
unsigned PyInstaller bootloader trips antivirus heuristics, and there is no
support channel to walk a stranger through a quarantine. That argument did not
stop applying because the packaging changed. The Tauri sidecar documentation
assumes a PyInstaller executable, and this project deliberately does not follow
it. The shell spawns the **embeddable CPython runtime** instead, which is a
folder of ordinary files, and the only executable a user launches is the Rust
binary, which signs cleanly.

**WebView2 is already there.** It is preinstalled on every Windows 11 device
and on almost every Windows 10 device, so the bundle carries a shell measured
in megabytes rather than a copy of Chromium. Electron would have meant shipping
a browser *and* a Python runtime.

---

## 3. Layout

The installer carries the same payload the portable ZIP does. It has to, or
they are two products and only one of them gets tested.

```
<install>/
  LinkedIn Studio.exe      the Rust shell
  runtime/                 embeddable CPython
    python.exe
    python313._pth         puts ..\lib and ..\app on sys.path
  lib/                     vendored dependencies
  app/
    studio/                the application package
```

`runtime/python313._pth` resolves `..\lib` and `..\app` **relative to itself**,
which is why those three directories must stay siblings. The shell therefore
spawns the interpreter without setting `PYTHONPATH`, and
`test_desktop_shell.py` fails if the bundle configuration ever nests them
differently.

User state does not live here. `app/studio/` ships with no `data/` directory,
and that absence is what makes `paths.get_app_home()` resolve to the user
profile, so replacing the install folder during an update cannot destroy drafts.

---

## 4. Startup order

The order is the whole design, and step 3 is the one that gets skipped:

1. **Claim single instance.** A second launch surfaces the running window
   rather than starting an engine that loses the race for port 8000.
2. **Start the backend, or attach to it.** If the health endpoint already
   answers, another launcher owns that process.
3. **Wait for readiness.** Binding a port finishes long before migrations do.
   Showing the window on bind means showing a connection error to a user who
   did nothing wrong. A splash is on screen for this interval.
4. **Navigate and reveal.**

The readiness probe is a hand written HTTP GET over `std::net::TcpStream`
against `/api/v1/health`. It checks the response body for `inox-hydra`, so
another program holding port 8000 reads as *not ready* rather than as a studio
to point a window at. There is no HTTP crate, because one unauthenticated GET
against loopback does not justify pulling a TLS stack into every build.

---

## 5. Two rules the shell must not break

**It never stops a backend it did not start.** A creator may already have the
studio running from the tray with a scheduler mid post. Opening the desktop
application attaches to that server, and quitting leaves it running.

**Closing the window hides it.** The studio runs a scheduler. Clicking the X
means "get this off my screen", not "stop posting". Quitting is an explicit act
from the tray menu.

---

## 6. The port is fixed at 8000

Not a default. A requirement.

The browser extension hardcodes `http://127.0.0.1:8000`. A shell that picked a
free port at runtime would silently break LinkedIn capture, which is the one
thing this product cannot do without. `test_desktop_shell.py` asserts the Rust
constant, the backend, and the extension all agree.

---

## 7. Building it

**You do not need Rust installed.** The toolchain is Rust plus the MSVC C++
build tools plus the Windows SDK, several gigabytes to change one line of
Python. `windows-latest` runners already carry all of it, so
`.github/workflows/desktop.yml` builds the bundle. Push a `v*.*.*` tag, or run
it from the Actions tab.

To build locally anyway, install the Rust toolchain and MSVC build tools, then:

```bash
python tools/generate_icons.py          # the bundler needs the exact icon set
python tools/stage_desktop_payload.py   # stages runtime, lib and app
npm exec -- tauri build --config desktop/src-tauri/tauri.conf.json
```

Everything checkable without a compiler is covered by `tests/test_desktop_shell.py`:
port agreement, probe route existence, icon presence, payload layout, version
agreement, and the two lifecycle rules above. What it cannot prove is that the
Rust compiles. That is CI's job, and the trade is deliberate.

---

## 8. Not done yet

**Browser launching on macOS and Linux.** `studio/backend/browser_launcher.py`
carries Windows paths only: Program Files, `%LOCALAPPDATA%`, and `.lnk`
shortcuts. On macOS and Linux `detect_installed_browsers()` returns an empty
dict and `create_desktop_shortcuts()` produces nothing.

This matters more than it first looks. The extension is how the studio sees
LinkedIn at all, and the launcher is what opens a browser with it loaded. A
macOS or Linux user can install the application and use the composer, the
scheduler and the CRM, but has no assisted path to the capture half of the
product. They would have to load the unpacked extension by hand.

The fix is a path table per platform (`/Applications/Google Chrome.app/...`,
`/usr/bin/google-chrome` and friends) plus a launcher that is a `.command`
script or a `.desktop` entry rather than a `.lnk`. The tests are gated with
`skipif` naming this reason, so the gap is visible in a test run rather than
silently absent.



**Code signing.** Wired, and off until you add credentials.

Unsigned, the installer trips SmartScreen on download and some antivirus
engines quarantine it outright, which is the exact failure the portable builder
was written to avoid by refusing PyInstaller. Shipping a Rust binary only helps
if that binary is signed.

Signing runs through Tauri's `signCommand`, not as a step after the build. That
ordering is the point: NSIS embeds the application executable inside the
installer, so signing the finished artifacts would leave the embedded copy
unsigned and SmartScreen would still complain once the installer ran.

To turn it on, add these repository secrets:

| Secret | Value |
|---|---|
| `AZURE_TENANT_ID` | directory tenant |
| `AZURE_CLIENT_ID` | the signing identity |
| `AZURE_CLIENT_SECRET` | its secret |
| `AZURE_SIGNING_ENDPOINT` | `https://<region>.codesigning.azure.net` |
| `AZURE_SIGNING_ACCOUNT` | signing account name |
| `AZURE_SIGNING_PROFILE` | certificate profile name |

The identity needs the **Artifact Signing Certificate Profile Signer** role.
Microsoft renamed Trusted Signing to Artifact Signing in January 2026, and the
role was renamed with it, so older guides name the previous one. It is about
ten dollars a month and open to individual developers, which replaced the old
several hundred a year plus a hardware token.

A build with no credentials stays green and produces a working unsigned
artifact, so a fork can still build. It emits a workflow warning rather than
passing quietly, because an unsigned release shipping by accident is the
failure mode worth designing against.

The step that matters is **Verify The Signature**. It asks Windows itself,
through `Get-AuthenticodeSignature`, whether the installer is validly signed,
and fails the build when signing was configured but did not take. A
`signCommand` that silently did nothing, an expired certificate, and a
credential missing the signer role all produce a green build and an unsigned
artifact otherwise.

**Auto update.** Wired, and off until you generate a keypair. Unlike code
signing this costs nothing and needs no account: one command, two secrets.

### The two keys are not the same key

Confusing them is the usual mistake, and they solve different problems.

| | Proves | Needed for |
|---|---|---|
| **Code signing** | to Windows, who published the installer | SmartScreen not warning on download |
| **Updater signing** | to the application, that an update came from the same author as the build it replaces | the updater running at all |

Only the second is what makes an update endpoint safe. A URL in a config file,
without a signature the application checks, is a way to install arbitrary
software on the user's machine. That is why `tauri-plugin-updater` refuses to
run without a public key, and why this feature stayed off rather than shipping
half configured.

You can have updates without code signing. That is the current position.

### Turning it on

Generate the pair once, on your own machine, and keep the private half:

```bash
npm exec --yes -- tauri signer generate -w "$HOME/.tauri/inox-hydra.key"
```

Then set three repository secrets:

| Secret | Value |
|---|---|
| `TAURI_SIGNING_PRIVATE_KEY` | contents of the `.key` file |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | the passphrase, or empty |
| `TAURI_UPDATER_PUBKEY` | contents of the `.key.pub` file |

**Keep the private key.** It is not recoverable and not regenerable. Lose it
and every installed copy stops accepting updates permanently, because they each
carry the matching public key compiled in. There is no path back except asking
every user to reinstall by hand.

### Before you actually add these secrets

Deferred deliberately until there are users to ship to. Read this first,
because the day you add the keys is the day it starts mattering.

This key is not an ordinary credential. A leaked API token exposes data; a
leaked updater key lets an attacker sign an update that **every installed copy
accepts and installs**. It is remote code execution on every machine that ever
ran this application.

The risk is not where the key is stored. GitHub encrypts Actions secrets at
rest, outside the repository, and masks them in logs. The risk is what runs
beside it: this workflow uses `actions/checkout@v4`, `dtolnay/rust-toolchain`,
`swatinem/rust-cache@v2`, `softprops/action-gh-release@v2` and
`@tauri-apps/cli@^2`, all on mutable tags or version ranges. Any one of them
could change under us, and it would be running in the same job that holds the
key.

Two ways to close that, in order of strength:

1. **Sign offline.** CI builds the installer unsigned; you sign it on your own
   machine and upload the `.sig` and manifest. The key never reaches a runner,
   which removes the problem rather than shrinking it.
2. **Protected environment plus pinning.** Move the key into a GitHub
   Environment with a required reviewer, so it is unavailable to any run you
   did not approve, and pin every action to a commit SHA and the CLI to an
   exact version.

An HSM or cloud KMS does not help here, which is worth knowing before paying
for one. Those protect X.509 code signing certificates. The updater key is a
minisign Ed25519 key read from an environment variable, and Tauri's signer has
no KMS integration.

Rotation is expensive, which is why this is worth doing once rather than
fixing later: existing installs verify against the old public key and cannot
auto update to a build signed with a new one. Each of them needs a manual
reinstall.

The public half is not a secret and is compiled into the application. It sits
in the secret store only so that its absence can switch the whole feature off,
which is what keeps a fork's build working.

Both keys, or neither. A build with only the public key would check for updates
it can never verify, so the workflow refuses that combination and says why.

### What a release produces

With the keys present, `desktop.yml` writes `desktop/updater.json` at build
time, the same way it writes `signing.json`, and the bundle gains
`createUpdaterArtifacts`. Tagging `v*.*.*` then attaches three files:

```
LinkedIn Studio_x.y.z_x64-setup.exe        the installer
LinkedIn Studio_x.y.z_x64-setup.exe.sig    its updater signature
latest-desktop.json                        the manifest clients read
```

The manifest version is read from `studio/__version__.py`, never written by
hand: a manifest announcing a version the artifact was not signed for is
rejected by the client as `SignedVersionMismatch`.

If Tauri produced no `.sig`, the build fails rather than publishing. A manifest
without one means every client downloads an update it then refuses, which
breaks updating for the people who already installed.

### Why the tray, and not a button in the studio

The check runs from the tray menu, in Rust, through `UpdaterExt`. It is not
reachable from the window, and `capabilities/default.json` still grants the
webview nothing.

That is deliberate. The window navigates to a loopback origin the shell does
not author. Granting it `updater:default` would let any page the webview ever
loads ask the shell to download and install software. Rust-side calls do not go
through the capability system, so driving the check from the tray is what keeps
that permission list empty.

### It asks, and it does not restart you

The menu item is the status surface: it reports checking, up to date, installed,
unreachable, or not configured, in the place the user clicked to ask.

Nothing happens unannounced, and nothing restarts on its own. The studio runs a
scheduler and holds someone's professional correspondence; an update that took
the window away mid draft would be the one moment the product acted against the
person using it. `studio/backend/updates.py` is opt-in for the same reason and
still does its own check, against a different manifest: `release/latest.json`
is committed and read over raw.githubusercontent, while `latest-desktop.json`
is a release asset in Tauri's schema. They are separate things and should not
be merged.

**The engine log.** Done. The shell spawns uvicorn with `CREATE_NO_WINDOW`, so
the child has no console, and its output used to go nowhere: a Python process
that died on an import error was indistinguishable from one still starting, and
the user got a splash that never resolved with nothing to inspect.

Its stdout and stderr now go to `engine.log` in the same directory
`paths.get_logs_dir()` returns, which is where `support.py` already tails the
newest files for the diagnostics bundle. Nothing else had to be wired.

The file appends across launches, each marked with a separator, and is dropped
once it passes 2 MB. Opening it is never a precondition for starting: if the
directory is read only or the disk is full, the studio runs and the output is
discarded as it was before.

**The engine outliving the shell.** Done. `Backend::shutdown` covers the
ordinary exit and respects the attach rule. It does not run when the shell is
killed outright, and the engine then kept running with no window of its own,
holding port 8000. Because `is_ready` correctly reports that engine as healthy,
the next launch attached to a process the user could not see and had not
knowingly left behind.

The spawned child is now placed in a Job Object with `KILL_ON_JOB_CLOSE`, so
Windows terminates it when the last handle to the job closes, which the kernel
does for us however this process dies. Only a backend the shell started is ever
placed in the job; an attached one returns before that point, because killing a
server we did not start is the one thing this file must not do.

The Win32 calls are declared by hand rather than adding the `windows` crate:
four functions and one struct whose layout has been fixed since Windows XP,
against a dependency costing build time on every run. A wrong struct size would
make `SetInformationJobObject` fail quietly and leave the orphan behind, so the
suite calls the real API with the same layout and asserts Windows accepts it.

**macOS and Linux.** Supported across builds, bundles, keystores, and autostart:

1. **Icons.** `tools/generate_icons.py` produces `icon.icns` with standard and
   retina layer sizes (32 to 1024 px) for macOS, and Linux PNG assets (32, 64,
   128, 256, 512 px). The icon generation is deterministic and reproducible.
2. **Bundle targets.** `desktop/src-tauri/tauri.conf.json` targets `nsis` on
   Windows, `app` and `dmg` on macOS, and `deb` and `appimage` on Linux. Tauri
   compiles only the targets valid for the host platform.
3. **Payload staging.** `tools/stage_desktop_payload.py` and
   `tools/build_portable.py` support cross-platform staging. On Windows,
   embeddable CPython uses `python3XX._pth`. On Unix, the isolated runtime
   resolves dependencies through `site-packages/inox_hydra.pth` pointing to
   the vendored `lib` and `app` trees. The Rust backend runner looks for
   `bin/python3` on Unix and `python.exe` on Windows, writing engine logs to
   `~/Library/Application Support/InoxHydra/logs` on macOS and
   `$XDG_DATA_HOME/inox-hydra/logs` on Linux.
4. **Platform keystores.** `studio/backend/vault.py` queries macOS Keychain via
   the `/usr/bin/security` CLI and Linux Secret Service via `secret-tool`. When
   the platform keystore is unavailable or headless, it falls back to the
   counter-mode encrypted file key beside the database. The vault status reports
   `MACOS_KEYCHAIN`, `LINUX_SECRET_SERVICE`, or `FILE_KEY` honestly, with no
   unsupported claims of hardware backing.
5. **Autostart.** `studio/backend/desktop.py` manages autostart via LaunchAgent
   property lists on macOS (`~/Library/LaunchAgents/com.inoxhydra.linkedinstudio.plist`)
   and XDG autostart desktop entries on Linux (`~/.config/autostart/inox-hydra.desktop`).
   It stays off by default, is cleanly reversible, and validates that files
   exist on disk before reporting enabled.
6. **CI workflow.** `.github/workflows/desktop.yml` runs a matrix across
   `windows-latest`, `macos-latest`, and `ubuntu-latest`. Linux runners install
   `libwebkit2gtk-4.1-dev` and required system libraries. Windows-specific code
   signing and updater manifests are guarded to Windows, ensuring unsigned builds
   produce working artifacts on every platform without credentials.
