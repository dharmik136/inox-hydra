"""
LinkedIn's data archive, imported with the creator in charge of each step.
==========================================================================

The archive is the creator's own record, handed over by LinkedIn: the owner
chose to make it a step of onboarding (planning/7 Roadmap/Decisions Needed.md,
decision 6). These build a synthetic archive laid out like LinkedIn's export,
with invented people only, and hold the importer to its rules:

- nothing is written until the creator has previewed it;
- Downloads is looked in only after they say they asked for the archive, and
  only for LinkedIn's export names;
- posts arrive with no figures, because the archive has none;
- what the bridge already captured is neither duplicated nor overwritten;
- messages are never imported, and connections never carry an email address;
- a file whose columns are not the known ones is reported, not guessed at;
- an archive built to exhaust memory is refused.
"""

import io
import os
import sqlite3
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import archive_import  # noqa: E402
import paths  # noqa: E402
from app import app  # noqa: E402
from database import init_db  # noqa: E402

SHARES = (
    "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl,Visibility\n"
    '2024-03-05 10:22:11,https://www.linkedin.com/feed/update/urn%3Ali%3Ashare%3A7170000000000000001,'
    '"Compilers are for people.\n\nMachines do not care how you spell it.",,,MEMBER_NETWORK\n'
    "2024-04-01 08:00:00,https://www.linkedin.com/feed/update/urn%3Ali%3Ashare%3A7180000000000000002,,"
    "https://example.com/reposted,,MEMBER_NETWORK\n"
    '2024-05-09 07:30:00,https://www.linkedin.com/feed/update/urn%3Ali%3AugcPost%3A7190000000000000003,'
    '"Already captured by the bridge.",,,MEMBER_NETWORK\n'
)
COMMENTS = (
    "Date,Link,Message\n"
    '2024-06-01 12:00:00,https://www.linkedin.com/feed/update/urn:li:activity:7200000000000000004,"Nanoseconds, in wire."\n'
)
REACTIONS = (
    "Date,Type,Link\n"
    "2024-06-02 09:00:00,PRAISE,https://www.linkedin.com/feed/update/urn:li:activity:7200000000000000005\n"
    "2024-06-02 09:00:00,LIKE,not-a-link\n"
)
CONNECTIONS = (
    "Notes:\n"
    '"When exporting your connection data, you may notice that some of the email addresses are missing."\n'
    "\n"
    "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
    "Ada,Lovelace,https://www.linkedin.com/in/ada-example,ada@example.com,Analytical Engines,Analyst,05 Mar 2024\n"
    "Hidden,Member,,,,,06 Mar 2024\n"
)
PROFILE = (
    "First Name,Last Name,Maiden Name,Address,Birth Date,Headline,Summary,Industry,Zip Code,Geo Location,"
    "Twitter Handles,Websites,Instant Messengers\n"
    "Grace,Hopper,,,,Rear Admiral,Taught machines to read English.,Defense,,Arlington,,,\n"
)
POSITIONS = "Company Name,Title,Description,Location,Started On,Finished On\nUS Navy,Rear Admiral,,Arlington,Jan 1943,Aug 1986\n"
SKILLS = "Name\nCOBOL\nCompilers\n"
MESSAGES = "CONVERSATION ID,FROM,TO,DATE,CONTENT\n1,Someone,Grace,2024-01-01,private words\n"


def _archive(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return buffer.getvalue()


FULL = {
    "Shares.csv": SHARES, "Comments.csv": COMMENTS, "Reactions.csv": REACTIONS,
    "Connections.csv": CONNECTIONS, "Profile.csv": PROFILE, "Positions.csv": POSITIONS,
    "Skills.csv": SKILLS, "messages.csv": MESSAGES, "Rich_Media.csv": "Date,Link\n",
}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "studio"))
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))  # what Windows reads for "~"
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    os.makedirs(tmp_path / "user" / "Downloads")
    init_db()
    return tmp_path


@pytest.fixture
def client(home):
    return TestClient(app)


def _db():
    conn = sqlite3.connect(paths.get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _send(client, data, name="Complete_LinkedInDataExport_10-19-2026.zip"):
    return client.post("/api/v1/archive/upload", content=data,
                       headers={"Content-Type": "application/zip", "X-Archive-Name": name})


def _upload(client, members=FULL, name="Complete_LinkedInDataExport_10-19-2026.zip"):
    res = _send(client, _archive(members), name)
    assert res.status_code == 200, res.text
    return res.json()


def test_a_preview_writes_nothing_and_says_what_it_found(client):
    preview = _upload(client)
    kinds = {f["kind"]: f for f in preview["files"]}
    assert kinds["posts"]["rows"] == 3 and kinds["connections"]["rows"] == 2
    assert all(f["importable"] for f in preview["files"])
    skipped = {os.path.basename(f["file"]): f["note"] for f in preview["not_imported"]}
    assert "Messages stay in the archive" in skipped["messages.csv"]
    assert "Rich_Media.csv" in skipped
    conn = _db()
    assert conn.execute("SELECT COUNT(*) FROM own_posts").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM archive_imports").fetchone()[0] == 0


def test_the_import_reads_each_file_into_its_place(client):
    source = _upload(client)["source"]
    res = client.post("/api/v1/archive/import", json={"source": source, "confirm_owner": True})
    assert res.status_code == 200, res.text
    summary = res.json()["summary"]
    assert summary["posts"] == {"added": 2, "already_there": 0, "skipped": 1}, "a repost with no text became a post"
    assert summary["comments"]["added"] == 1 and summary["reactions"] == {"added": 1, "already_there": 0, "skipped": 1}

    conn = _db()
    post = conn.execute(
        "SELECT * FROM own_posts WHERE activity_urn = 'urn:li:share:7170000000000000001'").fetchone()
    assert post["text"].startswith("Compilers are for people.\n\n"), "line breaks were lost"
    assert post["published_at"] == "2024-03-05T10:22:11+00:00" and post["published_at_source"] == "archive"
    assert [post[k] for k in ("reactions", "comments", "reposts", "impressions")] == [None] * 4, (
        "an imported post was given figures the archive does not have"
    )
    comment = conn.execute("SELECT * FROM outbound_engagements WHERE kind = 'comment'").fetchone()
    assert comment["my_text"] == "Nanoseconds, in wire." and comment["target_author"] is None
    reaction = conn.execute("SELECT * FROM outbound_engagements WHERE kind = 'reaction'").fetchone()
    assert reaction["reaction_kind"] == "celebrate", "LinkedIn's internal name instead of the bridge's word"
    identity = conn.execute("SELECT display_name, headline, about, location, confirmed_at FROM creator_identity").fetchone()
    assert tuple(identity) == ("Grace Hopper", "Rear Admiral", "Taught machines to read English.", "Arlington", None)
    assert conn.execute("SELECT title, company, date_range FROM creator_positions").fetchone()[:] == (
        "Rear Admiral", "US Navy", "Jan 1943 - Aug 1986")
    assert {r[0] for r in conn.execute("SELECT skill FROM creator_skills")} == {"COBOL", "Compilers"}


def test_connections_never_carry_an_email_address(client):
    source = _upload(client)["source"]
    client.post("/api/v1/archive/import", json={"source": source, "confirm_owner": True})
    conn = _db()
    columns = [r[1] for r in conn.execute("PRAGMA table_info(connections)")]
    assert not any("mail" in c for c in columns)
    rows = conn.execute("SELECT * FROM connections").fetchall()
    assert len(rows) == 1, "a connection with no profile URL was stored"
    assert rows[0]["first_name"] == "Ada" and rows[0]["connected_on"] == "05 Mar 2024"
    dumped = "\n".join(str(tuple(r)) for r in rows)
    assert "ada@example.com" not in dumped


def test_what_the_bridge_captured_is_kept(client):
    conn = _db()
    conn.execute(
        "INSERT INTO own_posts (activity_urn, text, published_at, reactions, first_seen_at, last_seen_at) "
        "VALUES ('urn:li:activity:7190000000000000099', 'Already captured by the bridge.', NULL, 42, 'x', 'x')")
    conn.execute(
        "INSERT INTO creator_identity (id, display_name, headline) VALUES (1, 'G. Hopper', 'Read by the bridge')")
    conn.commit()
    source = _upload(client)["source"]
    summary = client.post("/api/v1/archive/import", json={"source": source, "confirm_owner": True}).json()["summary"]
    assert summary["posts"]["already_there"] == 1
    conn = _db()
    kept = conn.execute("SELECT reactions, published_at FROM own_posts WHERE activity_urn LIKE '%99'").fetchone()
    assert kept["reactions"] == 42, "the archive overwrote a figure the bridge measured"
    assert kept["published_at"] == "2024-05-09T07:30:00+00:00", "the archive's date did not fill the missing one"
    identity = conn.execute("SELECT display_name, headline, about FROM creator_identity").fetchone()
    assert identity["display_name"] == "G. Hopper" and identity["headline"] == "Read by the bridge"
    assert identity["about"] == "Taught machines to read English.", "an empty field was not filled"


def test_importing_twice_adds_nothing_the_second_time(client):
    for _ in range(2):
        source = _upload(client)["source"]
        summary = client.post("/api/v1/archive/import", json={"source": source, "confirm_owner": True}).json()["summary"]
    assert summary["posts"]["added"] == 0 and summary["comments"]["added"] == 0
    assert summary["reactions"]["added"] == 0 and summary["connections"]["added"] == 0


def test_only_what_stays_ticked_is_imported(client):
    source = _upload(client)["source"]
    summary = client.post("/api/v1/archive/import", json={"source": source, "include": ["posts"], "confirm_owner": True}).json()["summary"]
    assert summary["connections"] == {"left_out": True}
    assert _db().execute("SELECT COUNT(*) FROM connections").fetchone()[0] == 0


def test_an_uploaded_copy_is_deleted_once_imported(client):
    source = _upload(client)["source"]
    client.post("/api/v1/archive/import", json={"source": source, "confirm_owner": True})
    assert client.post("/api/v1/archive/preview", json={"source": source, "confirm_owner": True}).status_code == 400
    assert not os.listdir(os.path.join(paths.get_data_dir(), "archive_uploads"))


def test_unknown_columns_are_reported_not_guessed(client):
    preview = _upload(client, {"Shares.csv": "When,Where,What\n1,2,3\n"})
    [entry] = preview["files"]
    assert entry["rows"] is None and entry["importable"] is False
    assert "when, where, what" in entry["note"]


def test_downloads_is_looked_in_only_after_the_archive_was_requested(client, home):
    downloads = home / "user" / "Downloads"
    (downloads / "Basic_LinkedInDataExport_10-19-2026.zip").write_bytes(_archive(FULL))
    (downloads / "holiday-photos.zip").write_bytes(b"not looked at")
    assert client.get("/api/v1/archive").json()["found"] == []

    state = client.post("/api/v1/archive/requested").json()
    assert [f["name"] for f in state["found"]] == ["Basic_LinkedInDataExport_10-19-2026.zip"]
    source = "downloads:" + state["found"][0]["path"]
    assert client.post("/api/v1/archive/preview", json={"source": source, "confirm_owner": True}).status_code == 200
    assert os.path.exists(state["found"][0]["path"]), "the creator's own download was removed"

    # Setup's polling of onboarding state, which Today also calls, never looks.
    assert client.get("/api/v1/onboarding/state").json()["archive"]["found"] == []
    # Once an archive has been imported, the studio stops looking.
    client.post("/api/v1/archive/import", json={"source": source, "confirm_owner": True})
    after = client.get("/api/v1/archive").json()
    assert after["waiting"] is False and after["found"] == []


def test_only_sources_the_studio_offered_are_opened(client, home):
    secret = home / "elsewhere.zip"
    secret.write_bytes(_archive(FULL))
    for source in ("downloads:" + str(secret), "upload:../../etc", str(secret)):
        assert client.post("/api/v1/archive/preview", json={"source": source, "confirm_owner": True}).status_code == 400


def test_an_oversized_upload_is_refused_as_it_arrives(client, monkeypatch):
    monkeypatch.setattr(archive_import, "MAX_ARCHIVE_BYTES", 1000)
    res = _send(client, _archive({"Shares.csv": "x" * 5000}) + os.urandom(2000))
    assert res.status_code == 413
    uploads = os.path.join(paths.get_data_dir(), "archive_uploads")
    assert not os.path.isdir(uploads) or not os.listdir(uploads)


def test_a_small_file_that_unpacks_to_a_huge_one_is_refused(client):
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Skills.csv", "Name\n" + "a\n" * (3 * 1024 * 1024))
    res = _send(client, bomb.getvalue())
    assert res.status_code == 400 and "unpacks" in res.json()["detail"]
    assert not os.listdir(os.path.join(paths.get_data_dir(), "archive_uploads")), "the refused copy was kept"


def test_a_damaged_or_locked_archive_is_a_plain_refusal(client):
    data = bytearray(_archive(FULL))
    data[len(data) // 3] ^= 0xFF
    damaged = _send(client, bytes(data))
    assert damaged.status_code == 400, damaged.text
    assert _send(client, b"not a zip at all").status_code == 400


def test_setup_carries_the_archive_step(client):
    state = client.get("/api/v1/onboarding/state").json()
    assert state["archive"]["download_page"].startswith("https://www.linkedin.com/")
    assert state["steps"]["archive"] is False
    source = _upload(client)["source"]
    client.post("/api/v1/archive/import", json={"source": source, "confirm_owner": True})
    state = client.get("/api/v1/onboarding/state").json()
    assert state["steps"]["archive"] is True and state["archive"]["last_import"]["summary"]["posts"]["added"] == 2


# ---------------------------------------------------------------------------
# Found in review
# ---------------------------------------------------------------------------

POST_TEXT = "Compilers are for people.\n\nMachines do not care how you spell it."
SHARE = "urn:li:share:7170000000000000001"
# The activity id LinkedIn's page shows for the same post: created the same
# second, so it decodes to the same moment, but a different number.
ACTIVITY = f"urn:li:activity:{(int(SHARE.rsplit(':', 1)[1]) >> 22 << 22) + 12345}"


def _confirm_me():
    conn = _db()
    conn.execute("INSERT OR REPLACE INTO creator_identity (id, vanity, confirmed_at) VALUES (1, 'grace', '2026-10-01')")
    conn.commit()
    conn.close()


def test_a_post_read_by_the_bridge_after_the_import_becomes_the_same_row(client):
    import onboarding

    source = _upload(client, {"Shares.csv": SHARES})["source"]
    client.post("/api/v1/archive/import", json={"source": source, "confirm_owner": True})
    _confirm_me()
    onboarding.ingest_own_posts("grace", [{"activity_urn": ACTIVITY, "actor": "grace", "reactions": 7,
                                           "text": "Compilers are for people. Machines do not\u2026more"}])
    rows = _db().execute("SELECT activity_urn, text, reactions, published_at FROM own_posts "
                         "WHERE text LIKE 'Compilers%'").fetchall()
    assert len(rows) == 1, "the archive's post and the page's post are two rows"
    assert rows[0]["activity_urn"] == ACTIVITY and rows[0]["reactions"] == 7
    assert rows[0]["text"] == POST_TEXT, "the page's cut text replaced the archive's full text"
    assert rows[0]["published_at"] == "2024-03-05T10:22:11+00:00"


def test_a_post_the_bridge_read_first_is_not_imported_again(client):
    conn = _db()
    conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, "
                 "first_seen_at, last_seen_at) VALUES (?, 'Compilers are for people. Machines\u2026more', "
                 "'2024-03-05T10:22:11.500000+00:00', 'urn_decode', 7, 'x', 'x')", (ACTIVITY,))
    conn.commit()
    source = _upload(client, {"Shares.csv": SHARES})["source"]
    summary = client.post("/api/v1/archive/import", json={"source": source, "confirm_owner": True}).json()["summary"]
    assert summary["posts"]["already_there"] == 1
    row = _db().execute("SELECT text, reactions FROM own_posts WHERE activity_urn = ?", (ACTIVITY,)).fetchone()
    assert row["reactions"] == 7 and row["text"] == POST_TEXT


def test_the_same_words_on_different_posts_are_different_comments(client):
    comments = ("Date,Link,Message\n"
                + "".join(f"2024-06-0{i} 12:00:00,https://www.linkedin.com/feed/update/urn:li:activity:72000000000000000{i}0,"
                          "Congratulations!\n" for i in range(1, 4)))
    source = _upload(client, {"Comments.csv": comments})["source"]
    summary = client.post("/api/v1/archive/import", json={"source": source, "confirm_owner": True}).json()["summary"]
    assert summary["comments"] == {"added": 3, "already_there": 0, "skipped": 0}


def test_an_unreadable_date_is_skipped_never_made_today(client):
    comments = "Date,Link,Message\nsometime,https://www.linkedin.com/feed/update/urn:li:activity:7200000000000000004,Hello\n"
    reactions = "Date,Type,Link\n2024-06-02 09:00:00 UTC,EMPATHY,https://www.linkedin.com/feed/update/urn:li:activity:7200000000000000005\n"
    source = _upload(client, {"Comments.csv": comments, "Reactions.csv": reactions})["source"]
    summary = client.post("/api/v1/archive/import", json={"source": source, "confirm_owner": True}).json()["summary"]
    assert summary["comments"]["skipped"] == 1 and summary["comments"]["added"] == 0
    reaction = _db().execute("SELECT reaction_kind, first_seen_at FROM outbound_engagements").fetchone()
    assert tuple(reaction) == ("love", "2024-06-02T09:00:00+00:00"), "LinkedIn's internal name or a UTC suffix leaked through"


def test_a_broken_row_is_reported_not_merged_into_the_next(client):
    lines = ["Date,Link,Message"]
    for i in range(10):
        lines.append(f'2024-06-01 12:00:00,https://www.linkedin.com/feed/update/urn:li:activity:72000000000000001{i:02d},"Comment {i}"')
    lines.insert(6, '2024-06-01 12:00:00,https://x,"unclosed')
    preview = _upload(client, {"Comments.csv": "\n".join(lines) + "\n"})
    [entry] = preview["files"]
    assert entry["note"], "rows were lost without a word"


def test_forgetting_yourself_removes_what_the_archive_brought(client):
    source = _upload(client)["source"]
    client.post("/api/v1/archive/import", json={"source": source, "confirm_owner": True})
    client.post("/api/v1/archive/requested")
    assert client.delete("/api/v1/identity").status_code == 200
    conn = _db()
    assert conn.execute("SELECT COUNT(*) FROM connections").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM archive_imports").fetchone()[0] == 0
    state = client.get("/api/v1/onboarding/state").json()
    assert state["steps"]["archive"] is False and state["archive"]["requested_at"] is None


def test_an_upload_set_aside_is_deleted(client):
    source = _upload(client)["source"]
    assert client.post("/api/v1/archive/discard", json={"source": source, "confirm_owner": True}).status_code == 200
    assert not os.listdir(os.path.join(paths.get_data_dir(), "archive_uploads"))


def test_a_csv_export_cannot_carry_a_formula(client):
    import support

    conn = _db()
    conn.execute("INSERT INTO connections (profile_url, first_name, last_name, imported_at) "
                 "VALUES ('https://www.linkedin.com/in/x', '=HYPERLINK(\"http://evil\")', '@SUM(A1)', 'now')")
    conn.commit()
    conn.close()
    out = support.export_data(os.path.join(paths.get_exports_dir(), "t.zip"), fmt="csv")
    with zipfile.ZipFile(out) as archive:
        text = archive.read("connections.csv").decode()
    assert "'=HYPERLINK" in text and "'@SUM" in text
