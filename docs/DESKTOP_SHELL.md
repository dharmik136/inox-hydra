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

**Auto update.** `tauri-plugin-updater` is not enabled, because it requires a
generated signing keypair and enabling it without one produces an application
that fails at runtime. `studio/backend/updates.py` still does its opt-in check.

**macOS and Linux.** Nothing builds for them. `icon.icns` is deliberately not
generated rather than shipped as a placeholder.
