"""
Ten tabs on one post: requests and rows per item.
=================================================

Cycle 4, track 1, phase 2: the capture report's measurement for the
coordination block. One post with thirty people commenting is open in ten
tabs of one browser. One tab's read is captured from the shipped content.js
in Chromium; the shipped worker (tests/ten_tabs_harness.js, under node)
replays it from ten tabs at once against a real studio on a loopback port;
then the studio's own tables are read.

Measured on 2.9.0 (main at e9ab6ff) with the same harness and recorded in
docs/quality/cycle4/t1-phase2.md: 620 requests (300 engager writes, 10 run
reports, 310 heartbeats), each person's seen_count 10, 10 capture rows and
310 heartbeat rows. Now: one read, one run report and one heartbeat; each
person once.

Every name here is invented.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import pytest

pytest.importorskip("playwright.sync_api")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TESTS = os.path.dirname(os.path.abspath(__file__))
NODE = shutil.which("node")
TABS, PEOPLE, ME = 10, 30, "test-creator"
POST = "urn:li:activity:7385000000000000001"


def _post_with_people():
    comments = "".join(
        f"""<div class="c"><a href="https://www.linkedin.com/in/person-{n}-example/"><img alt=""></a>
        <div><a href="https://www.linkedin.com/in/person-{n}-example/"><p>Person {n} Example</p></a><p>• 2nd</p>
        <p>Engineer at Example {n}</p><p>{n}h</p></div><p>Comment number {n}, with its own words.</p></div>"""
        for n in range(PEOPLE))
    return f"""<div data-urn="{POST}"><div data-testid="commentList-{POST}">
      <div class="hdr"><a href="https://www.linkedin.com/in/{ME}/"><p>Test Creator</p></a><p>A post of mine.</p></div>
      {comments}</div></div>"""


def _one_tabs_read():
    from qc_f3_pages import Pages, page_html
    pages = Pages()
    try:
        page = pages.open("/feed/", page_html("<main id='m'></main>", title="Feed | LinkedIn"))
        page.clock.run_for(5000)
        page.evaluate("(html) => { document.getElementById('m').innerHTML = html; }", _post_with_people())
        page.clock.run_for(8000)
        sent = page.evaluate("() => window.__sent")
    finally:
        pages.close()
    return [m for m in sent if m.get("action") == "STUDIO_API"
            and m.get("path") in ("/api/v1/crm/interactions/ingest", "/api/v1/bridge/capture")]


@pytest.fixture
def live_studio(monkeypatch, tmp_path):
    import uvicorn
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
    from database import init_db
    init_db()
    from app import app
    from security import get_or_create_token
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    token = get_or_create_token()

    def call(path, body):
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "X-Inox-Token": token},
                                         method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read() or b"{}")

    call("/api/v1/identity/observe", {"vanity": ME, "display_name": "Test Creator", "self_evidence": ["owner_edit_controls"]})
    call("/api/v1/identity/confirm", {"vanity": ME})
    call("/api/v1/self/posts/ingest", {"author": ME, "posts": [{"activity_urn": POST, "actor": ME, "text": "A post of mine."}]})
    yield {"port": port, "token": token, "home": str(tmp_path)}
    server.should_exit = True
    thread.join(timeout=10)


def test_ten_tabs_on_one_post_cost_one_read_and_each_person_once(live_studio, tmp_path):
    if not NODE:
        pytest.skip("node is not installed")
    messages = _one_tabs_read()
    one_tab = {path: sum(1 for m in messages if m["path"] == path) for path in {m["path"] for m in messages}}
    assert one_tab["/api/v1/crm/interactions/ingest"] == 1, "a tab's read of thirty people is not one request"
    read = os.path.join(str(tmp_path), "read.json")
    with open(read, "w") as handle:
        json.dump(messages, handle)
    result = subprocess.run([NODE, os.path.join(TESTS, "ten_tabs_harness.js"),
                             os.path.join(REPO_ROOT, "studio", "extension", "background.js"),
                             str(live_studio["port"]), live_studio["token"], read, str(TABS)],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    run = json.loads(result.stdout)
    conn = sqlite3.connect(os.path.join(live_studio["home"], "data", "linkedin_studio.db"))
    try:
        rows, seen, most = conn.execute("SELECT COUNT(*), SUM(seen_count), MAX(seen_count) FROM lead_interactions "
                                        "WHERE post_urn = ?", (POST,)).fetchone()
        captures = conn.execute("SELECT COUNT(*) FROM captures WHERE extractor = 'engagers'").fetchone()[0]
        heartbeats = conn.execute("SELECT COUNT(*) FROM bridge_heartbeats").fetchone()[0]
    finally:
        conn.close()
    print(f"\nten tabs on one post: {run['requests']} requests {run['by_path']}, {rows} rows, seen_count total "
          f"{seen} (most {most}), {captures} capture rows, {heartbeats} heartbeat rows, {run['wall_ms']} ms")
    assert run["by_path"].get("/api/v1/crm/interactions/ingest") == 1, run["by_path"]
    # A slow runner can let the ten reads straddle the coalescing window, so
    # the run report may go out twice; never once per tab.
    assert run["by_path"].get("/api/v1/bridge/capture", 0) <= 2, run["by_path"]
    assert run["requests"] <= 4, run["by_path"]
    assert rows == PEOPLE and seen == PEOPLE and most == 1, "a person was written more than once"
    assert 1 <= captures <= 2 and heartbeats <= 1
