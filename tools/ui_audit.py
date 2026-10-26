"""
UI Audit: Drive Every Surface the Way a Person Would, and Write Down What Broke.
=================================================================================
Boots the studio against a throwaway home (or points at one already running),
then walks every section of the rail in both themes and at two widths. For each
screen it records:

  - a full page screenshot
  - console errors and uncaught page errors
  - every request that left loopback (the product promises zero egress)
  - every failed or non 2xx API response
  - axe-core accessibility violations
  - horizontal overflow, which is how a layout breaks at phone width

docs/UI_AGENT_WORKFLOW.md section 5 explains why this exists: of the defects on
one branch, the build caught none and the suite caught one, while driving the
interface caught four. This makes that drive repeatable.

Usage:
    python tools/ui_audit.py                      # fresh, empty install
    python tools/ui_audit.py --demo               # seeded with FABRICATED demo data
    python tools/ui_audit.py --url http://127.0.0.1:8123
    python tools/ui_audit.py --sections today,leads --themes dark

Writes scratch/ui_audit/<timestamp>/ with report.md, report.json and PNGs.
Exits non-zero when any screen has a console error, an egress request or an
axe violation of serious or critical impact.

Requires the playwright package and its Chromium, and a built interface
(npm --prefix studio/ui run build).

Strict Invariants:
- Zero em-dashes.
- Never writes into the source checkout's studio/data: a booted server always
  gets its own INOX_HYDRA_HOME.
"""

import argparse
import datetime
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AXE_JS = os.path.join(REPO_ROOT, "studio", "ui", "node_modules", "axe-core", "axe.min.js")

# Rail labels, in rail order (studio/ui/src/lib/navigation.ts, which
# tests/test_qc4_t4_rail.py holds this to). These are the accessible names
# StudioRail gives each button, so a rename there shows up here as "section
# not found" rather than as a silently skipped screen. Brand and Settings both
# open Brand Studio until the two are split.
SECTIONS = {
    "today": "Today",
    "replies": "Replies",
    "record": "From your record",
    "composer": "Composer",
    "queue": "Queue",
    "outbound": "Outbound",
    "posts": "Posts",
    "leads": "Leads",
    "audience": "Audience",
    "patterns": "Patterns",
    "analytics": "Analytics",
    "brand": "Brand",
    "activity": "Activity",
    "health": "Health",
    "setup": "Setup",
    "docs": "Docs",
    "settings": "Settings",
}

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "phone": {"width": 390, "height": 844},
}

BLOCKING_IMPACT = ("serious", "critical")


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _boot(demo):
    """Starts uvicorn against a temporary home. Returns (url, process, home)."""
    home = tempfile.mkdtemp(prefix="inox_ui_audit_")
    env = dict(os.environ, INOX_HYDRA_HOME=home)
    if demo:
        env["INOX_DEMO_DATA"] = "1"
    else:
        env.pop("INOX_DEMO_DATA", None)
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "studio.backend.app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=REPO_ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/", timeout=2) as response:
                if response.status == 200:
                    return url, proc, home
        except OSError:
            time.sleep(0.5)
    proc.terminate()
    raise SystemExit(f"the studio did not answer on {url} within 60 seconds")


def _is_loopback(url):
    host = urllib.parse.urlparse(url).hostname or ""
    return host in ("127.0.0.1", "localhost", "::1") or url.startswith(("data:", "blob:", "about:"))


def _audit_screen(page, axe_source):
    """Runs the per-screen checks that read the DOM."""
    page.add_script_tag(content=axe_source)
    axe = page.evaluate(
        """async () => {
            const r = await axe.run(document, { resultTypes: ['violations'] });
            return r.violations.map(v => ({
                id: v.id, impact: v.impact, help: v.help,
                nodes: v.nodes.slice(0, 5).map(n => n.target.join(' ')),
                count: v.nodes.length,
            }));
        }"""
    )
    overflow = page.evaluate(
        "() => Math.max(0, document.documentElement.scrollWidth - window.innerWidth)"
    )
    return axe, overflow


def run(url, sections, themes, viewports, out_dir, settle_ms):
    from playwright.sync_api import sync_playwright

    with open(AXE_JS, encoding="utf-8") as handle:
        axe_source = handle.read()

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for viewport_name in viewports:
            for theme in themes:
                context = browser.new_context(
                    viewport=VIEWPORTS[viewport_name],
                    color_scheme="dark" if theme == "dark" else "light",
                    reduced_motion="reduce",
                )
                page = context.new_page()
                events = {"console": [], "pageerror": [], "egress": [], "api": []}
                page.on("console", lambda m: events["console"].append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda e: events["pageerror"].append(str(e)))
                page.on("request", lambda r: None if _is_loopback(r.url) else events["egress"].append(r.url))
                page.on(
                    "response",
                    lambda r: events["api"].append(f"{r.status} {r.request.method} {urllib.parse.urlparse(r.url).path}")
                    if "/api/" in r.url and r.status >= 400 else None,
                )

                page.goto(url + "/", wait_until="networkidle")
                page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")

                for key in sections:
                    for bucket in events.values():
                        bucket.clear()
                    label = SECTIONS[key]
                    record = {"section": key, "theme": theme, "viewport": viewport_name}
                    button = page.locator(f"nav[aria-label='Studio sections'] button[aria-label='{label}']")
                    if button.count() == 0:
                        record["error"] = f"no rail button named {label!r}"
                        results.append(record)
                        continue
                    try:
                        button.first.click(timeout=5000)
                    except Exception as exc:  # a covered or hidden control is itself a finding
                        record["error"] = f"could not click {label!r}: {exc.__class__.__name__}"
                        results.append(record)
                        continue
                    page.wait_for_timeout(settle_ms)
                    try:
                        page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass  # a live stream keeps the network busy; the settle wait covers it

                    shot = f"{key}-{theme}-{viewport_name}.png"
                    page.screenshot(path=os.path.join(out_dir, shot), full_page=True)
                    axe, overflow = _audit_screen(page, axe_source)
                    record.update({
                        "screenshot": shot,
                        "console_errors": list(dict.fromkeys(events["console"])),
                        "page_errors": list(dict.fromkeys(events["pageerror"])),
                        "egress": list(dict.fromkeys(events["egress"])),
                        "api_failures": list(dict.fromkeys(events["api"])),
                        "axe": axe,
                        "horizontal_overflow_px": overflow,
                    })
                    results.append(record)
                context.close()
        browser.close()
    return results


def _blocking(record):
    return bool(
        record.get("error")
        or record.get("console_errors")
        or record.get("page_errors")
        or record.get("egress")
        or any(v["impact"] in BLOCKING_IMPACT for v in record.get("axe", []))
    )


def write_report(results, out_dir, url):
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)

    lines = [f"# UI audit, {datetime.datetime.now():%Y-%m-%d %H:%M}", "", f"Target: {url}", ""]
    lines.append("| Screen | Theme | Width | Console | Egress | API >= 400 | axe (serious+) | Overflow |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        if r.get("error"):
            lines.append(f"| {r['section']} | {r['theme']} | {r['viewport']} | {r['error']} | | | | |")
            continue
        serious = sum(1 for v in r["axe"] if v["impact"] in BLOCKING_IMPACT)
        lines.append(
            f"| {r['section']} | {r['theme']} | {r['viewport']} | {len(r['console_errors']) + len(r['page_errors'])}"
            f" | {len(r['egress'])} | {len(r['api_failures'])} | {serious} of {len(r['axe'])}"
            f" | {r['horizontal_overflow_px']}px |"
        )
    lines.append("")
    for r in results:
        detail = []
        for name in ("console_errors", "page_errors", "egress", "api_failures"):
            for item in r.get(name, []):
                detail.append(f"- {name}: `{item[:300]}`")
        for v in r.get("axe", []):
            detail.append(f"- axe {v['impact']}: {v['id']} ({v['count']}x) {v['help']}: `{'; '.join(v['nodes'])}`")
        if detail:
            lines.append(f"## {r['section']} / {r['theme']} / {r['viewport']}")
            lines.extend(detail)
            lines.append("")
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--url", help="audit a studio that is already running instead of booting one")
    parser.add_argument("--demo", action="store_true", help="boot with INOX_DEMO_DATA (fabricated, for layout only)")
    parser.add_argument("--sections", default=",".join(SECTIONS), help="comma separated section ids")
    parser.add_argument("--themes", default="dark,light")
    parser.add_argument("--viewports", default="desktop,phone")
    parser.add_argument("--settle-ms", type=int, default=1200)
    parser.add_argument("--out", help="output directory (default scratch/ui_audit/<timestamp>)")
    args = parser.parse_args(argv)

    sections = [s.strip() for s in args.sections.split(",") if s.strip()]
    unknown = [s for s in sections if s not in SECTIONS]
    if unknown:
        parser.error(f"unknown sections: {', '.join(unknown)}")
    if not os.path.exists(AXE_JS):
        parser.error("axe-core is missing; run npm --prefix studio/ui ci")

    out_dir = args.out or os.path.join(REPO_ROOT, "scratch", "ui_audit", f"{datetime.datetime.now():%Y%m%d_%H%M%S}")
    os.makedirs(out_dir, exist_ok=True)

    proc = None
    url = args.url
    if not url:
        url, proc, _home = _boot(args.demo)
    try:
        results = run(
            url.rstrip("/"), sections, args.themes.split(","), args.viewports.split(","), out_dir, args.settle_ms
        )
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=15)

    write_report(results, out_dir, url)
    blocking = [r for r in results if _blocking(r)]
    print(f"{len(results)} screens audited, {len(blocking)} with blocking findings")
    print(f"report: {os.path.join(out_dir, 'report.md')}")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
