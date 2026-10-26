"""
Stage 3 of From your record: the Inox library arrives signed, sends nothing of yours, and never touches your forms.
====================================================================================================================

Cycle 4, track 7, batch 9 of the personalised daily ideas report, and
decisions 10 and 11. intelligence_sync.py fetched an unsigned bundle nothing
called and, on every answer, emptied the creator's hook library with
DELETE FROM viral_templates. It is deleted. Its replacement fetches one file
only when the creator presses Fetch, under the existing `library` egress
category, carrying nothing of the creator's; keeps it only when its Ed25519
signature verifies against the key the studio ships; stores it in a table
of its own; and matches it to the creator's own recurring words on this
machine. The material is the company's own: forms, patterns and examples,
never a post copied from LinkedIn.
"""

import base64
import io
import json
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
sys.path.insert(0, BACKEND)

import ed25519  # noqa: E402

SECRET = bytes(range(32))
PUBLIC = base64.b64encode(ed25519.public_key(SECRET)).decode("ascii")
OTHER_SECRET = bytes(range(1, 33))
OTHER_PUBLIC = base64.b64encode(ed25519.public_key(OTHER_SECRET)).decode("ascii")
KEY_ID = "test-library-key"


def entries():
    return [
        {"id": "form-hiring-first-post", "kind": "form", "title": "Write the job post first",
         "text": "Before you look for anyone, write the post you would want to read about [the role].",
         "tags": ["hiring", "recruiting"], "author": "Inox Hydra"},
        {"id": "pattern-pricing-turn", "kind": "pattern", "title": "The price you used to charge",
         "text": "Name the old price, the moment it stopped making sense, and what you charge now.",
         "tags": ["pricing"], "author": "Inox Hydra"},
    ]


def content(**overrides):
    base = {"format": "inox-library", "format_version": 1, "version": "2026.10.1", "signed_at": "2026-10-20",
            "key_id": KEY_ID, "publisher": "Inox Hydra", "content_policy": "company-authored", "entries": entries()}
    base.update(overrides)
    return base


def signed(body=None, secret=SECRET):
    import library_bundle

    return library_bundle.encode(body or content(), lambda message: ed25519.sign(secret, message))


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "studio"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    monkeypatch.delenv("INOX_NO_EGRESS", raising=False)
    monkeypatch.delenv("INOX_LIBRARY_URL", raising=False)
    import library_bundle
    import results
    from database import init_db

    results.forget_cache()
    init_db()
    monkeypatch.setattr(library_bundle, "PUBLIC_KEYS", {KEY_ID: PUBLIC})
    return tmp_path


def db():
    import paths

    conn = sqlite3.connect(paths.get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def count(table):
    conn = db()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The signature
# ---------------------------------------------------------------------------

def test_a_signed_bundle_verifies_and_a_changed_one_does_not(home):
    import library_bundle

    text = signed()
    assert library_bundle.verify(text)["version"] == "2026.10.1"
    prefix, payload, signature = text.split(".")
    changed = payload[:-3] + ("A" if payload[-3] != "A" else "B") + payload[-2:]
    with pytest.raises(library_bundle.LibraryRefused, match="does not match"):
        library_bundle.verify(f"{prefix}.{changed}.{signature}")


def test_a_key_the_studio_does_not_ship_is_refused(home):
    import library_bundle

    with pytest.raises(library_bundle.LibraryRefused, match="does not match any library key"):
        library_bundle.verify(signed(secret=OTHER_SECRET))


def test_the_old_unsigned_shape_is_refused(home):
    import library_bundle

    with pytest.raises(library_bundle.LibraryRefused, match="not a signed Inox library file"):
        library_bundle.verify(json.dumps({"templates": [{"hook_text": "Anything at all"}]}))


def test_a_bundle_signed_by_one_listed_key_while_naming_another_is_refused(home, monkeypatch):
    import library_bundle

    monkeypatch.setattr(library_bundle, "PUBLIC_KEYS", {KEY_ID: PUBLIC, "second-key": OTHER_PUBLIC})
    with pytest.raises(library_bundle.LibraryRefused, match="names a different key"):
        library_bundle.verify(signed(content(key_id="second-key")))


def test_the_committed_public_key_is_a_real_key_and_no_secret_is_in_the_repository():
    import library_bundle

    assert library_bundle.PUBLIC_KEYS, "no library key is committed"
    for key_id, public in library_bundle.PUBLIC_KEYS.items():
        assert len(base64.b64decode(public)) == 32, key_id
    for base, dirs, names in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__", "frontend_next")]
        assert "ed25519.secret" not in names, f"a signing secret is in the repository at {base}"


# ---------------------------------------------------------------------------
# The content policy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("change,reason", [
    ({"publisher": "Someone Else"}, "not the company's own material"),
    ({"content_policy": "quoted-with-attribution"}, "not the company's own material"),
    ({"entries": [{**entries()[0], "text": "See linkedin.com/posts/someone-viral-123"}]}, "links to LinkedIn"),
    ({"entries": [{**entries()[0], "author": "A Famous Creator"}]}, "author other than the company"),
    ({"entries": [{**entries()[0], "kind": "viral_post"}]}, "forms, patterns and examples"),
    ({"entries": [entries()[0], entries()[0]]}, "repeated"),
    ({"entries": []}, "between 1 and"),
])
def test_what_is_not_the_companys_own_material_is_refused(home, change, reason):
    import library_bundle

    with pytest.raises(library_bundle.LibraryRefused, match=reason):
        library_bundle.validate(library_bundle.verify(signed(content(**change))))


def test_keeping_the_library_never_touches_the_creators_hook_forms(home):
    import hook_forms
    import library_bundle

    hook_forms.ensure_seeded()
    forms = count("viral_templates")
    assert forms > 0
    assert library_bundle.import_text(signed())["status"] == "updated"
    assert count("library_entries") == 2
    assert count("viral_templates") == forms, "the library replaced the creator's forms"
    refused = library_bundle.import_text(signed(secret=OTHER_SECRET))
    assert refused["status"] == "refused" and count("library_entries") == 2, "a refused file changed the library"
    source = io.open(os.path.join(BACKEND, "library_bundle.py"), encoding="utf-8").read()
    assert "viral_templates" not in source.split('"""', 2)[2], "the library module writes the creator's forms"


# ---------------------------------------------------------------------------
# Fetching: one request, nothing of yours, under the library category
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, body, etag):
        self.body, self.headers = body, {"ETag": etag}

    def read(self, limit):
        return self.body[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_a_fetch_sends_nothing_of_the_creators_and_is_counted_under_library(home, monkeypatch):
    import egress
    import library_bundle

    conn = db()
    conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) VALUES "
                 "('urn:li:activity:7450000000000000001', 'A distinctive sentence about my hiring loop', "
                 "'2025-05-01', '2025-05-01', '2025-05-01')")
    conn.execute("INSERT INTO asks (text, source, status, created_at, updated_at) VALUES "
                 "('my private ask about pricing', 'ask_box', 'open', '2026-10-26', '2026-10-26')")
    conn.commit()
    conn.close()
    sent = []

    def fake_open(request, timeout=None):
        sent.append(request)
        return FakeResponse(signed().encode("ascii"), '"tag-one"')

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    egress.reset_for_tests()
    answer = library_bundle.fetch()
    assert answer["status"] == "updated" and answer["entries"] == 2
    request = sent[0]
    assert request.get_method() == "GET" and request.data is None
    assert request.full_url == library_bundle.DEFAULT_URL
    assert {k.lower() for k in request.headers} == {"user-agent", "accept"}
    everything = request.full_url + json.dumps(dict(request.headers))
    for private in ("distinctive sentence", "private ask", "hiring", "pricing"):
        assert private not in everything, f"the request carried {private!r}"
    counted = {c["name"]: c["performed"] for c in egress.describe()["categories"]}
    assert counted["library"] == 1 and sum(counted.values()) == 1

    def not_modified(request, timeout=None):
        sent.append(request)
        import urllib.error
        raise urllib.error.HTTPError(request.full_url, 304, "Not Modified", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", not_modified)
    again = library_bundle.fetch()
    assert again["status"] == "up_to_date"
    assert sent[1].get_header("If-none-match") == '"tag-one"'
    assert count("library_entries") == 2


def test_a_refused_category_and_a_bad_address_send_nothing(home, monkeypatch):
    import library_bundle

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("opened")))
    monkeypatch.setenv("INOX_NO_EGRESS", "1")
    assert library_bundle.fetch()["status"] == "refused"
    monkeypatch.delenv("INOX_NO_EGRESS")
    monkeypatch.setenv("INOX_LIBRARY_URL", "http://raw.githubusercontent.com/x/library.ilb")
    assert library_bundle.fetch()["message"] == "The library is fetched over https only."
    monkeypatch.delenv("INOX_LIBRARY_URL")
    assert not library_bundle.allowed_host("evil-githubusercontent.com")
    assert not library_bundle.allowed_host("raw.githubusercontent.com.evil.example")
    assert count("library_entries") == 0


def test_the_routes_fetch_import_and_say_what_the_library_is(home, monkeypatch):
    from fastapi.testclient import TestClient

    import app as app_module

    client = TestClient(app_module.app)
    knows = client.get("/api/v1/record/knows").json()["library"]
    assert knows["entries"] == 0 and "nothing of yours" in knows["sends"] and "Inox Hydra team wrote" in knows["contains"]
    assert client.post("/api/v1/record/library/import", json={"text": signed(secret=OTHER_SECRET)}).status_code == 400
    assert client.post("/api/v1/record/library/import", json={"text": signed()}).status_code == 200
    assert client.get("/api/v1/record/knows").json()["library"]["version"] == "2026.10.1"


# ---------------------------------------------------------------------------
# Matching on this machine, into the open slot
# ---------------------------------------------------------------------------

def test_an_entry_tagged_for_the_creators_topic_fills_the_open_slot_curated(home):
    import library_bundle
    import record_daily

    conn = db()
    texts = ["Hiring is a product problem, not a recruiting problem.", "We changed our hiring loop this spring.",
             "Hiring slowly is a choice, and it costs.", "Pricing is a design decision.", "Pricing pages lie less.",
             "A note on writing every morning."]
    for n, text in enumerate(texts):
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                     "VALUES (?, ?, '2025-05-01', '2025-05-01', '2025-05-01')", (f"urn:li:activity:74600000000000{n:05d}", text))
    conn.commit()
    conn.close()
    library_bundle.import_text(signed())
    record_daily.run_today()
    slot5 = [c for c in record_daily.read_today()["cards"] if c["slot"] == 5]
    assert len(slot5) == 1 and slot5[0]["label"] == "curated" and slot5[0]["kind"] == "library"
    card = slot5[0]
    assert card["provenance"]["bundle"] == {"version": "2026.10.1", "signed_at": "2026-10-20", "key_id": KEY_ID}
    assert card["payload"]["badge"] == "curated, not measured for you"
    assert card["payload"]["because"].endswith("rule: From the Inox library")
    assert card["provenance"]["source_rows"][0]["table"] == "library_entries"


def test_a_library_that_matches_nothing_leaves_the_slot_to_say_so(home):
    import library_bundle
    import record_daily

    conn = db()
    for n, text in enumerate(["Gardening in clay soil.", "Clay soil needs patience.", "Roses in clay, a year on."]):
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                     "VALUES (?, ?, '2025-05-01', '2025-05-01', '2025-05-01')", (f"urn:li:activity:74700000000000{n:05d}", text))
    conn.commit()
    conn.close()
    library_bundle.import_text(signed())
    record_daily.run_today()
    slot5 = [c for c in record_daily.read_today()["cards"] if c["slot"] == 5]
    assert slot5 and slot5[0]["label"] == "abstained"


# ---------------------------------------------------------------------------
# The unsigned sync is gone, and the rail's forms are not
# ---------------------------------------------------------------------------

def test_the_unsigned_sync_is_deleted_and_the_rails_forms_remain(home):
    from fastapi.testclient import TestClient

    import app as app_module

    assert not os.path.exists(os.path.join(BACKEND, "intelligence_sync.py"))
    assert not os.path.exists(os.path.join(REPO_ROOT, "tests", "test_intelligence_sync_hardening.py"))
    client = TestClient(app_module.app)
    assert client.get("/api/v1/intelligence/status").status_code == 404
    assert client.get("/api/v1/intelligence/bundle/export").status_code == 404
    assert client.post("/api/v1/intelligence/bundle/import", json={"bundle": {}}).status_code in (404, 405)
    assert client.get("/api/v1/intelligence/templates?limit=5").json()["count"] > 0
    for base, dirs, names in os.walk(os.path.join(REPO_ROOT, "studio")):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", "frontend_next")]
        for name in names:
            if name.endswith(".py"):
                source = io.open(os.path.join(base, name), encoding="utf-8").read()
                assert "DELETE FROM viral_templates\")" not in source and "DELETE FROM viral_templates\n" not in source, name


# ---------------------------------------------------------------------------
# The vendor's tool
# ---------------------------------------------------------------------------

def test_the_tool_signs_a_file_the_studio_verifies_and_never_writes_a_key_into_the_repository(tmp_path):
    tool = os.path.join(REPO_ROOT, "tools", "library_bundle.py")
    refused = subprocess.run([sys.executable, tool, "new-keypair", "--out", os.path.join(REPO_ROOT, "tmp-library-key"),
                              "--key-id", "x"], capture_output=True, text=True, timeout=60)
    assert refused.returncode == 2 and "inside the repository" in refused.stderr
    assert not os.path.exists(os.path.join(REPO_ROOT, "tmp-library-key"))

    keys = tmp_path / "keys"
    made = subprocess.run([sys.executable, tool, "new-keypair", "--out", str(keys), "--key-id", "tool-test"],
                          capture_output=True, text=True, timeout=60)
    assert made.returncode == 0, made.stderr
    public = made.stdout.strip().splitlines()[-1].split('"')[3]
    # Owner-only where the platform has POSIX modes. Windows reports 666 for any
    # file it can write; there the secret is guarded by the user profile's ACL.
    if os.name != "nt":
        assert oct(os.stat(keys / "ed25519.secret").st_mode)[-3:] == "600"
    source = tmp_path / "entries.json"
    source.write_text(json.dumps({"entries": [{k: v for k, v in e.items() if k != "author"} for e in entries()]}))
    bundle = tmp_path / "library.ilb"
    done = subprocess.run([sys.executable, tool, "sign", "--key", str(keys / "ed25519.secret"), "--in", str(source),
                           "--out", str(bundle), "--version", "2026.10.9", "--key-id", "tool-test"],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    text = bundle.read_text().strip()
    assert text.startswith("ILB1.") and text.count(".") == 2
    checked = subprocess.run([sys.executable, tool, "verify", "--in", str(bundle), "--public", public,
                              "--key-id", "tool-test"], capture_output=True, text=True, timeout=60)
    assert checked.returncode == 0 and "2 entries" in checked.stdout, checked.stderr


def test_the_policy_and_the_help_say_what_the_library_is_and_sends():
    policy = io.open(os.path.join(REPO_ROOT, "docs", "PRIVACY_POLICY.md"), encoding="utf-8").read()
    assert "fetching the Inox library when you press Fetch" in policy
    assert "the request for it carries nothing of yours" in policy
    assert "the file is kept only if its signature matches the key the studio ships" in policy
    help_text = io.open(os.path.join(REPO_ROOT, "docs", "help", "what-leaves-this-machine.md"), encoding="utf-8").read()
    row = next(line for line in help_text.splitlines() if line.startswith("| `library` |"))
    assert "Fetch the Inox library" in row and "Nothing of yours" in row
