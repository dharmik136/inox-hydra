"""
The built interface, served for the tests named test_qc2_r5_*.
==============================================================

Cycle 2, batch R5 (everyday flows). One studio serves the built interface for
a whole test module; each test points it at a throwaway home of its own and
seeds that home through the routes the extension calls, as a creator who
finished Setup: a confirmed identity, posts of their own, people who engaged
with them.

Service workers are blocked in every context: the studio's worker would
otherwise answer requests itself. Nothing here clicks a control that opens a
browser, and nothing reaches past loopback.
"""

import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import uvicorn  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

BUILT = os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")

ME = "priya-raman-r5"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    if not os.path.exists(BUILT):
        pytest.skip("the interface is not built (npm --prefix studio/ui run build)")
    old_home, old_demo = os.environ.get("INOX_HYDRA_HOME"), os.environ.get("INOX_DEMO_DATA")
    first = tempfile.mkdtemp(prefix="inox_qc2_r5_")
    os.environ["INOX_HYDRA_HOME"] = first
    os.environ.pop("INOX_DEMO_DATA", None)
    from database import init_db
    init_db()
    import app as app_module

    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app=app_module.app, host="127.0.0.1", port=port,
                                        log_level="error", access_log=False))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield {"url": f"http://127.0.0.1:{port}", "browser": browser, "app": app_module.app}
        browser.close()
    srv.should_exit = True
    thread.join(timeout=3)
    shutil.rmtree(first, ignore_errors=True)
    for key, value in (("INOX_HYDRA_HOME", old_home), ("INOX_DEMO_DATA", old_demo)):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture
def studio(server):
    """A fresh home behind the running server, a client to seed it, and a page on it."""
    home = tempfile.mkdtemp(prefix="inox_qc2_r5_home_")
    previous = os.environ["INOX_HYDRA_HOME"]
    os.environ["INOX_HYDRA_HOME"] = home
    from database import init_db
    init_db()
    client = TestClient(server["app"])
    context = server["browser"].new_context(viewport={"width": 1440, "height": 900}, service_workers="block")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("dialog", lambda dialog: dialog.accept())
    yield {"client": client, "page": page, "context": context, "url": server["url"], "errors": errors}
    context.close()
    os.environ["INOX_HYDRA_HOME"] = previous
    shutil.rmtree(home, ignore_errors=True)


def urn_days_ago(days, salt=0):
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


POST_TEXTS = [
    "Your on-call rota is a culture document.",
    "Most logistics outages start with a spreadsheet nobody owns.",
    "We cut dispatch time by a third. Here is how.",
    "Three things I got wrong about queues.",
    "Nobody reads your roadmap.",
]


def confirm_identity(client):
    """The creator confirms who they are, as Setup's first steps do."""
    assert client.post("/api/v1/bridge/heartbeat", json={"extension_version": "2.6.0", "page_kind": "feed"}).status_code == 200
    observed = client.post("/api/v1/identity/observe", json={
        "vanity": ME, "self_evidence": ["owner_edit_controls"], "display_name": "Priya Raman",
        "headline": "VP of Engineering at Northwind Freight", "location": "Pune, India",
        "current_company": "Northwind Freight", "follower_count": 4200,
    })
    assert observed.status_code == 200, observed.text
    confirmed = client.post("/api/v1/identity/confirm", json={"vanity": ME})
    assert confirmed.status_code == 200, confirmed.text


def seed_creator(client, commenter="Anika Shah", comment="This matches what we saw last year."):
    """A confirmed creator with five posts and one commenter on the first. Returns the post urns."""
    confirm_identity(client)
    urns = [urn_days_ago(2 + index * 6, index) for index in range(len(POST_TEXTS))]
    posts = [{"activity_urn": urn, "actor": ME, "text": text + "\n\nA second paragraph with the detail.",
              "reactions": 20 + index, "comments": 3, "reposts": 0}
             for index, (urn, text) in enumerate(zip(urns, POST_TEXTS))]
    ingested = client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": posts})
    assert ingested.status_code == 200, ingested.text
    if commenter:
        engaged = client.post("/api/v1/crm/interactions/ingest", json={
            "full_name": commenter, "profile_url": "https://www.linkedin.com/in/anika-shah-x",
            "headline": "Head of Platform at Cargoline", "company": "Cargoline", "interaction_type": "COMMENT",
            "comment_text": comment, "post_urn": urns[0], "post_author": ME,
        })
        assert engaged.status_code == 200, engaged.text
    return urns


def open_section(studio, section):
    page = studio["page"]
    page.goto(studio["url"] + f"/#/{section}", wait_until="networkidle")
    return page
