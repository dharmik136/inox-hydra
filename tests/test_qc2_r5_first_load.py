"""
The first screen, drawn once, and one answer about the bridge on screen.
=======================================================================

Cycle 2, batch R5, D-18 and D-11. Opened without an address, the studio drew
the Composer for a frame, then a blank one, then Setup or Today, and on the
way asked for onboarding/state three times and fetched the Composer's
templates and profile for a screen it was about to leave. Separately, Today
could say BRIDGE CONNECTED for up to a minute beside a header mark that said
the bridge was not connected, because each read the bridge on its own clock.
"""

from qc2_r5_live import confirm_identity, server, studio  # noqa: F401

# Records each distinct state of the page as it is drawn: whether the
# Composer's editor is on screen, and the screen's heading.
OBSERVER = """
window.__seen = [];
new MutationObserver(() => {
  const composer = !!document.querySelector('[aria-label="Post body"]');
  const heading = document.querySelector('h1');
  const key = (composer ? 'composer' : '-') + '|' + (heading ? heading.textContent.slice(0, 30) : '');
  const last = window.__seen[window.__seen.length - 1];
  if (last !== key) window.__seen.push(key);
}).observe(document, { subtree: true, childList: true });
"""


def _land(studio):
    page = studio["page"]
    page.add_init_script(OBSERVER)
    requests = []
    page.on("request", lambda request: requests.append(request.url.split("://", 1)[1].split("/", 1)[1]))
    page.goto(studio["url"] + "/", wait_until="networkidle")
    return page, requests


def test_a_new_install_lands_on_setup_without_drawing_the_composer(studio):
    page, requests = _land(studio)
    page.wait_for_selector("h1")
    assert page.url.endswith("#/setup"), page.url
    seen = page.evaluate("window.__seen")
    assert not any(state.startswith("composer") for state in seen), seen
    asked = [path for path in requests if path.startswith("api/v1/onboarding/state")]
    # One for the shell to choose the screen, one for Setup itself.
    assert len(asked) <= 2, asked
    assert not any("templates" in path or "profile" in path for path in requests), requests


def test_a_known_creator_lands_on_today_asking_once(studio):
    confirm_identity(studio["client"])
    page, requests = _land(studio)
    page.wait_for_selector("text=What to do in the next hour")
    seen = page.evaluate("window.__seen")
    assert not any(state.startswith("composer") for state in seen), seen
    asked = [path for path in requests if path.startswith("api/v1/onboarding/state")]
    assert len(asked) == 1, asked


def test_the_header_mark_agrees_with_today_about_the_bridge(studio):
    page = studio["page"]
    page.clock.install()
    confirm_identity(studio["client"])
    # Heard from long enough ago that it no longer counts as connected.
    import database

    conn = database.get_db()
    try:
        conn.execute("UPDATE bridge_heartbeats SET seen_at = '2000-01-01T00:00:00+00:00'")
        conn.commit()
    finally:
        conn.close()
    page.goto(studio["url"] + "/#/today", wait_until="networkidle")
    page.wait_for_selector("text=What to do in the next hour")
    assert "BRIDGE CONNECTED" not in page.inner_text("main")

    # The bridge reports in; Today reads it again within 30 seconds.
    assert studio["client"].post("/api/v1/bridge/heartbeat", json={"extension_version": "2.6.0"}).status_code == 200
    page.clock.run_for("00:31")
    page.wait_for_selector("text=BRIDGE CONNECTED")
    mark = page.locator("header button", has_text="Activity").first.text_content()
    assert ", bridge connected" in mark, mark
