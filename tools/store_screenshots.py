#!/usr/bin/env python3
"""
Captures the store listing's screenshots from the real product.

Both the Chrome Web Store and Microsoft Edge Add-ons take 1280x800 PNGs. The
set shipped with 2.6.0 was taken by hand and never regenerated, so after cycle
3 rebuilt the sections its first image showed an Activity screen of five tabs
that no longer exists, with a caption describing it. A listing that shows a
product the installer will not find is worse than one with fewer images.

Nothing here is a mock-up. A throwaway home is seeded with the studio's own
demo data through the studio's own startup, the built interface is served from
a loopback port, and each image is whatever the browser drew. The captions in
SCREENSHOTS.md are written from the images, not from this file.

    python3 tools/store_screenshots.py --out ~/.cache/inox-qc3/store/screenshots

Requires the interface to be built (npm --prefix studio/ui run build) and
Playwright's chromium. The studio's own port is left alone: this serves its
own instance on a free one.
"""

import argparse
import os
import shutil
import socket
import sys
import tempfile
import threading
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO, "studio", "backend")
BUILT = os.path.join(REPO, "studio", "frontend_next", "index.html")

# 1280x800 is what both stores accept. The studio is measured at 1440x900 in
# its own audits; this is the listing's size, not the product's.
WIDTH, HEIGHT = 1280, 800

# Each entry is the rail section to open and the file to write. The order is
# the order the stores show them in, and it leads with what the extension
# reads, because that is the question a cautious installer actually has.
SHOTS = (
    ("activity", "01-activity-what-the-bridge-read.png", "What the bridge has read"),
    ("today", "02-today-the-next-hour.png", "What to do in the next hour"),
    ("leads", "03-leads-and-a-dossier.png", None),
    ("posts", "04-posts-what-worked.png", "What worked, and who it brought"),
)


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _serve(home):
    """The studio, on its own home and its own port, with demo data seeded."""
    os.environ["INOX_HYDRA_HOME"] = home
    os.environ["INOX_DEMO_DATA"] = "1"
    sys.path.insert(0, BACKEND)
    from database import init_db
    init_db()
    import app as app_module
    import uvicorn

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app=app_module.app, host="127.0.0.1",
                                           port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if getattr(server, "started", False):
            break
        time.sleep(0.1)
    else:
        raise SystemExit("the studio did not start")
    return server, f"http://127.0.0.1:{port}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="directory to write the PNGs into")
    args = parser.parse_args()

    if not os.path.exists(BUILT):
        raise SystemExit("the interface is not built: npm --prefix studio/ui run build")
    from playwright.sync_api import sync_playwright

    out = os.path.abspath(os.path.expanduser(args.out))
    os.makedirs(out, exist_ok=True)
    home = tempfile.mkdtemp(prefix="inox_store_shots_")
    server, url = _serve(home)
    written = []
    try:
        with sync_playwright() as play:
            browser = play.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT},
                                    device_scale_factor=1,
                                    service_workers="block")
            page.goto(url + "/", wait_until="networkidle")
            page.wait_for_timeout(1500)

            for section, filename, heading in SHOTS:
                page.goto(f"{url}/#/{section}", wait_until="networkidle")
                page.wait_for_timeout(1400)
                drawn = page.locator("h1").first.inner_text().strip()
                if heading and drawn != heading:
                    print(f"  ! {section}: the screen is headed {drawn!r}, expected {heading!r}",
                          file=sys.stderr)
                if section == "leads":
                    # The dossier, not the empty right pane: open the first lead.
                    row = page.locator("main button, main [role='button'], main tr").first
                    try:
                        row.click(timeout=4000)
                        page.wait_for_timeout(1200)
                    except Exception as error:
                        print(f"  ! leads: could not open a dossier ({error.__class__.__name__})",
                              file=sys.stderr)
                target = os.path.join(out, filename)
                page.screenshot(path=target)
                size = os.path.getsize(target)
                written.append((filename, size, drawn))
                print(f"  {filename}  {size:,} bytes  h1: {drawn!r}")
            browser.close()
    finally:
        server.should_exit = True
        time.sleep(0.4)
        shutil.rmtree(home, ignore_errors=True)

    print(f"\n{len(written)} images in {out}")
    print("The extension popup is not captured here: it needs the extension loaded in a")
    print("real browser profile. Capture it by hand from the bridge browser's popup, or")
    print("leave it out rather than shipping a stale one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
