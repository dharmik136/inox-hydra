"""
Quality cycle 2026-10, batch F4a: LinkedIn's archive import.
============================================================

Each section holds the regression test for one finding of the Setup review.
Every name and text here is invented.
"""

import io
import os
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import archive_import  # noqa: E402
import paths  # noqa: E402
from app import app  # noqa: E402
from database import init_db  # noqa: E402

COMPLETE = "Complete_LinkedInDataExport_10-19-2026.zip"
SHARES_HEADER = "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl,Visibility\n"


def _snow(moment: datetime, salt: int) -> int:
    """A LinkedIn-style id: the high bits are the millisecond timestamp."""
    return (int(moment.timestamp() * 1000) << 22) | (salt & ((1 << 22) - 1))


def _share_row(moment: datetime, salt: int, text: str = "", shared: str = "", media: str = "",
               kind: str = "share") -> str:
    link = f"https://www.linkedin.com/feed/update/urn%3Ali%3A{kind}%3A{_snow(moment, salt)}"
    quoted = '"' + text.replace('"', '""') + '"' if text else ""
    return f"{moment.strftime('%Y-%m-%d %H:%M:%S')},{link},{quoted},{shared},{media},MEMBER_NETWORK\n"


def _archive(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return buffer.getvalue()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "studio"))
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
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


def _upload(client, members, name=COMPLETE):
    res = client.post("/api/v1/archive/upload", content=_archive(members),
                      headers={"Content-Type": "application/zip", "X-Archive-Name": name})
    assert res.status_code == 200, res.text
    return res.json()


def _import(client, source, **extra):
    return client.post("/api/v1/archive/import", json={"source": source, **extra})


# ---------------------------------------------------------------------------
# SETUP-06: the same words on different days are different posts, and a post
# with no caption is still a post
# ---------------------------------------------------------------------------

OFFICE_HOURS = "Our weekly office hours are open again this Thursday at 5pm. Bring your questions."


def test_same_text_a_week_apart_imports_as_separate_posts(client):
    days = [datetime(2024, 1, d, 11, 0, tzinfo=timezone.utc) for d in (4, 11, 18)]
    shares = SHARES_HEADER + "".join(_share_row(day, i, OFFICE_HOURS) for i, day in enumerate(days))
    source = _upload(client, {"Shares.csv": shares})["source"]
    summary = _import(client, source, include=["posts"], confirm_owner=True).json()["summary"]
    assert summary["posts"] == {"added": 3, "already_there": 0, "skipped": 0}, summary
    dates = [r[0] for r in _db().execute("SELECT published_at FROM own_posts ORDER BY published_at")]
    assert dates == [d.isoformat() for d in days]


def test_same_text_as_a_bridge_post_on_another_day_is_not_that_post(client):
    bridge_day = datetime(2024, 1, 4, 11, 0, tzinfo=timezone.utc)
    conn = _db()
    conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, "
                 "first_seen_at, last_seen_at) VALUES (?, ?, ?, 'urn_decode', 9, 'x', 'x')",
                 (f"urn:li:activity:{_snow(bridge_day, 5)}", OFFICE_HOURS, bridge_day.isoformat()))
    conn.commit()
    conn.close()
    later = datetime(2024, 1, 11, 11, 0, tzinfo=timezone.utc)
    source = _upload(client, {"Shares.csv": SHARES_HEADER + _share_row(later, 1, OFFICE_HOURS)})["source"]
    summary = _import(client, source, include=["posts"], confirm_owner=True).json()["summary"]
    assert summary["posts"]["added"] == 1, "a post a week later was merged into the bridge's row"
    assert _db().execute("SELECT COUNT(*) FROM own_posts").fetchone()[0] == 2


def test_a_post_with_media_and_no_caption_is_imported(client):
    day = datetime(2024, 2, 1, 9, 0, tzinfo=timezone.utc)
    media = _share_row(day, 77, media="https://media.licdn.com/dms/image/sample/1", kind="ugcPost")
    repost = _share_row(datetime(2024, 2, 2, 9, 0, tzinfo=timezone.utc), 78,
                        shared="https://www.linkedin.com/feed/update/urn:li:activity:7100000000000000000")
    source = _upload(client, {"Shares.csv": SHARES_HEADER + media + repost})["source"]
    summary = _import(client, source, include=["posts"], confirm_owner=True).json()["summary"]
    assert summary["posts"] == {"added": 1, "already_there": 0, "skipped": 1}, summary
    row = _db().execute("SELECT activity_urn, published_at FROM own_posts").fetchone()
    assert row["activity_urn"] == f"urn:li:ugcPost:{_snow(day, 77)}" and row["published_at"] == day.isoformat()


def test_a_captionless_post_matches_the_bridge_row_by_id_and_time(client):
    day = datetime(2024, 2, 1, 9, 0, tzinfo=timezone.utc)
    activity = f"urn:li:activity:{_snow(day, 4242)}"
    conn = _db()
    conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, "
                 "first_seen_at, last_seen_at) VALUES (?, NULL, ?, 'urn_decode', 3, 'x', 'x')",
                 (activity, day.isoformat()))
    conn.commit()
    conn.close()
    media = _share_row(day, 77, media="https://media.licdn.com/dms/image/sample/1", kind="ugcPost")
    source = _upload(client, {"Shares.csv": SHARES_HEADER + media})["source"]
    summary = _import(client, source, include=["posts"], confirm_owner=True).json()["summary"]
    assert summary["posts"] == {"added": 0, "already_there": 1, "skipped": 0}, summary
    assert _db().execute("SELECT reactions FROM own_posts").fetchone()[0] == 3


# ---------------------------------------------------------------------------
# SETUP-01: the preview says whose archive it is, and another member's
# archive is not imported as the creator's without their word
# ---------------------------------------------------------------------------

PROFILE_HEADER = ("First Name,Last Name,Maiden Name,Address,Birth Date,Headline,Summary,Industry,Zip Code,"
                  "Geo Location,Twitter Handles,Websites,Instant Messengers\n")


def _profile(first, last, headline="Synthetic headline", about="Synthetic about.", where="Synthetic City"):
    return PROFILE_HEADER + f"{first},{last},,,,{headline},{about},Software,,{where},,,\n"


def _person_archive(first, last):
    shares = SHARES_HEADER + _share_row(datetime(2024, 3, 5, 10, 0, tzinfo=timezone.utc), 1,
                                        f"A synthetic post written by {first} {last} about compilers.")
    return {"Profile.csv": _profile(first, last), "Shares.csv": shares,
            "Skills.csv": "Name\nSynthetic Skill\n",
            "Connections.csv": "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
                               "Ada,Example,https://www.linkedin.com/in/ada-example,,Co,Role,05 Mar 2024\n"}


def _confirm(client, vanity, name):
    res = client.post("/api/v1/identity/observe", json={
        "vanity": vanity, "display_name": name, "headline": f"{name}'s synthetic headline",
        "self_evidence": ["owner_edit_controls"]})
    assert res.status_code == 200, res.text
    res = client.post("/api/v1/identity/confirm", json={"vanity": vanity})
    assert res.status_code == 200, res.text


def _nothing_imported():
    conn = _db()
    return all(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
               for table in ("own_posts", "creator_skills", "connections", "archive_imports"))


def test_the_preview_says_whose_archive_it_is(client):
    _confirm(client, "sample-bob", "Sample Bob")
    preview = _upload(client, _person_archive("Sample", "Alice"))
    assert preview["owner"]["name"] == "Sample Alice"
    assert preview["creator"]["name"] == "Sample Bob" and preview["creator"]["vanity"] == "sample-bob"
    assert "Sample Alice" in preview["needs_confirmation"] and "Sample Bob" in preview["needs_confirmation"]


def test_another_members_archive_is_refused_without_a_word_naming_both(client):
    _confirm(client, "sample-bob", "Sample Bob")
    source = _upload(client, _person_archive("Sample", "Alice"))["source"]
    res = _import(client, source)
    assert res.status_code == 409, res.text
    assert "Sample Alice" in res.json()["detail"] and "Sample Bob" in res.json()["detail"]
    assert _nothing_imported(), "another member's archive was written into the creator's studio"
    identity = _db().execute("SELECT about, location FROM creator_identity").fetchone()
    assert identity["about"] is None and identity["location"] is None

    res = _import(client, source, confirm_owner=True)
    assert res.status_code == 200, res.text
    assert res.json()["summary"]["posts"]["added"] == 1


def test_your_own_archive_imports_without_a_question(client):
    _confirm(client, "sample-bob", "Sample Bob")
    preview = _upload(client, _person_archive("Sámple", "BOB"))
    assert preview["owner"]["name"] == "Sámple BOB" and preview["needs_confirmation"] == ""
    assert _import(client, preview["source"]).status_code == 200


def test_with_no_profile_confirmed_the_import_asks_first(client):
    preview = _upload(client, _person_archive("Sample", "Alice"))
    assert preview["creator"] is None
    assert "Sample Alice" in preview["needs_confirmation"]
    res = _import(client, preview["source"])
    assert res.status_code == 409 and "Sample Alice" in res.json()["detail"]
    assert _nothing_imported()
    assert _import(client, preview["source"], confirm_owner=True).status_code == 200


# ---------------------------------------------------------------------------
# SETUP-19: what an import brought can be removed from the archive step, with
# or without a confirmed profile
# ---------------------------------------------------------------------------

def test_what_an_import_brought_can_be_removed_without_a_confirmed_profile(client):
    members = _person_archive("Sample", "Alice")
    members["Comments.csv"] = ("Date,Link,Message\n2024-06-01 12:00:00,"
                               "https://www.linkedin.com/feed/update/urn:li:activity:7200000000000000004,Nice.\n")
    members["Positions.csv"] = "Company Name,Title\nSample Co,Sample Role\n"
    source = _upload(client, members)["source"]
    assert _import(client, source, confirm_owner=True).status_code == 200
    assert client.get("/api/v1/onboarding/state").json()["identity"] is None

    res = client.post("/api/v1/archive/undo")
    assert res.status_code == 200, res.text
    assert res.json()["removed"]["posts"] == 1 and res.json()["removed"]["connections"] == 1
    conn = _db()
    for table in ("own_posts", "outbound_engagements", "creator_positions", "creator_skills", "connections",
                  "archive_imports"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    identity = conn.execute("SELECT display_name, headline, about, location, profile_observed_at "
                            "FROM creator_identity").fetchone()
    assert identity is None or all(v is None for v in identity), "the archive's profile fields stayed"
    state = client.get("/api/v1/onboarding/state").json()
    assert state["archive"]["last_import"] is None and state["steps"]["archive"] is False


def test_removing_an_import_keeps_what_was_there_before_it(client):
    conn = _db()
    conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, reactions, first_seen_at, last_seen_at) "
                 "VALUES ('urn:li:activity:7000000000000000001', 'Read by the bridge, long before.', NULL, 4, 'x', 'x')")
    conn.execute("INSERT INTO creator_identity (id, display_name, headline) VALUES (1, 'Sample Bob', 'Mine')")
    conn.execute("INSERT INTO creator_skills (skill, observed_at) VALUES ('Synthetic Skill', 'x')")
    conn.commit()
    conn.close()
    source = _upload(client, _person_archive("Sample", "Alice"))["source"]
    assert _import(client, source, confirm_owner=True).status_code == 200
    assert client.post("/api/v1/archive/undo").status_code == 200
    conn = _db()
    assert [r[0] for r in conn.execute("SELECT activity_urn FROM own_posts")] == ["urn:li:activity:7000000000000000001"]
    assert [r[0] for r in conn.execute("SELECT skill FROM creator_skills")] == ["Synthetic Skill"]
    identity = conn.execute("SELECT display_name, headline, about FROM creator_identity").fetchone()
    assert tuple(identity) == ("Sample Bob", "Mine", None)


def test_there_is_nothing_to_remove_before_an_import(client):
    assert client.post("/api/v1/archive/undo").status_code == 400


def test_an_import_that_fails_part_way_leaves_nothing_behind(client, monkeypatch):
    # Every row its own batch, so the posts are committed before the failure.
    monkeypatch.setattr(archive_import, "BATCH_SECONDS", 0)
    monkeypatch.setattr(archive_import, "BATCH_PAUSE", 0)

    def broken(conn, rows, batches):
        raise RuntimeError("the disk is full")

    monkeypatch.setitem(archive_import._IMPORTERS, "connections", broken)
    source = _upload(client, _person_archive("Sample", "Alice"))["source"]
    with pytest.raises(RuntimeError):
        archive_import.import_archive(source, confirm_owner=True)
    assert _nothing_imported(), "a failed import left part of itself in the studio"
    identity = _db().execute("SELECT about, location FROM creator_identity").fetchone()
    assert identity is None or (identity["about"], identity["location"]) == (None, None)


# ---------------------------------------------------------------------------
# SETUP-04: LinkedIn's first, basic archive does not end the step; the
# complete one, with the posts, is still looked for and offered
# ---------------------------------------------------------------------------

BASIC = "Basic_LinkedInDataExport_10-19-2026.zip"


def _basic_members():
    members = _person_archive("Sample", "Alice")
    members.pop("Shares.csv")
    return members


def test_after_the_basic_archive_the_complete_one_is_still_looked_for(client, home):
    downloads = home / "user" / "Downloads"
    (downloads / BASIC).write_bytes(_archive(_basic_members()))
    state = client.post("/api/v1/archive/requested").json()
    assert [f["name"] for f in state["found"]] == [BASIC]
    assert _import(client, "downloads:" + state["found"][0]["path"], confirm_owner=True).status_code == 200

    (downloads / COMPLETE).write_bytes(_archive(_person_archive("Sample", "Alice")))
    after = client.get("/api/v1/archive").json()
    assert after["waiting"] is True, "the studio stopped looking once the basic archive was in"
    assert COMPLETE in [f["name"] for f in after["found"]]
    assert after["complete"] is False and after["last_import"]["held_posts"] is False
    onboarding = client.get("/api/v1/onboarding/state").json()
    assert onboarding["steps"]["archive"] is False, "the step ticked with no post imported"

    complete = next(f for f in after["found"] if f["name"] == COMPLETE)
    assert _import(client, "downloads:" + complete["path"], confirm_owner=True).status_code == 200
    done = client.get("/api/v1/archive").json()
    assert done["waiting"] is False and done["complete"] is True
    assert client.get("/api/v1/onboarding/state").json()["steps"]["archive"] is True


def test_an_account_with_no_posts_can_say_so(client):
    source = _upload(client, _basic_members(), name=BASIC)["source"]
    assert _import(client, source, confirm_owner=True).status_code == 200
    assert client.get("/api/v1/onboarding/state").json()["steps"]["archive"] is False
    state = client.post("/api/v1/archive/no-posts").json()
    assert state["complete"] is True and state["waiting"] is False
    assert client.get("/api/v1/onboarding/state").json()["steps"]["archive"] is True


def test_an_archive_whose_posts_file_is_empty_says_the_account_has_none(client):
    members = _person_archive("Sample", "Alice")
    members["Shares.csv"] = SHARES_HEADER
    preview = _upload(client, members)
    ticked = [f["kind"] for f in preview["files"] if f["importable"]]
    assert "posts" not in ticked
    assert _import(client, preview["source"], include=ticked, confirm_owner=True).status_code == 200
    assert client.get("/api/v1/onboarding/state").json()["steps"]["archive"] is True


def test_the_complete_archive_of_an_account_that_never_posted_ends_the_step(client):
    source = _upload(client, _basic_members(), name=COMPLETE)["source"]
    assert _import(client, source, confirm_owner=True).status_code == 200
    assert client.get("/api/v1/archive").json()["complete"] is True


def test_posts_left_unticked_do_not_end_the_step(client):
    source = _upload(client, _person_archive("Sample", "Alice"))["source"]
    assert _import(client, source, include=["skills"], confirm_owner=True).status_code == 200
    assert client.get("/api/v1/archive").json()["complete"] is False


# ---------------------------------------------------------------------------
# SETUP-21: a download still being written is shown as one, not offered as a
# broken archive
# ---------------------------------------------------------------------------

def test_a_firefox_download_in_progress_is_marked_still_downloading(client, home):
    downloads = home / "user" / "Downloads"
    (downloads / BASIC).write_bytes(b"")
    (downloads / (BASIC + ".part")).write_bytes(b"PK\x03\x04partial")
    [hit] = client.post("/api/v1/archive/requested").json()["found"]
    assert hit["name"] == BASIC and hit["downloading"] is True
    res = client.post("/api/v1/archive/preview", json={"source": "downloads:" + hit["path"]})
    assert res.status_code == 400 and "still downloading" in res.json()["detail"]


def test_a_chrome_download_in_progress_is_listed_under_its_final_name(client, home):
    downloads = home / "user" / "Downloads"
    (downloads / (COMPLETE + ".crdownload")).write_bytes(b"PK\x03\x04partial")
    [hit] = client.post("/api/v1/archive/requested").json()["found"]
    assert hit["name"] == COMPLETE and hit["downloading"] is True


def test_only_linkedins_exports_count_as_downloads_in_progress(client, home):
    (home / "user" / "Downloads" / "my linkedin data export notes.txt.part").write_bytes(b"x")
    assert client.post("/api/v1/archive/requested").json()["found"] == []


def test_a_file_written_moments_ago_that_does_not_open_may_still_be_downloading(client, home):
    downloads = home / "user" / "Downloads"
    (downloads / COMPLETE).write_bytes(_archive(_person_archive("Sample", "Alice"))[:200])
    [hit] = client.post("/api/v1/archive/requested").json()["found"]
    assert hit["downloading"] is False
    res = client.post("/api/v1/archive/preview", json={"source": "downloads:" + hit["path"]})
    assert res.status_code == 400 and "may still be downloading" in res.json()["detail"]


def test_a_finished_download_is_offered_as_before(client, home):
    downloads = home / "user" / "Downloads"
    (downloads / COMPLETE).write_bytes(_archive(_person_archive("Sample", "Alice")))
    [hit] = client.post("/api/v1/archive/requested").json()["found"]
    assert hit["downloading"] is False
    assert client.post("/api/v1/archive/preview", json={"source": "downloads:" + hit["path"]}).status_code == 200


# ---------------------------------------------------------------------------
# SETUP-12: an archive Safari unpacked into a folder is found and read like
# the ZIP, within the same limits
# ---------------------------------------------------------------------------

UNPACKED = COMPLETE[:-len(".zip")]


def _unpack(folder, members):
    os.makedirs(folder)
    for name, text in members.items():
        os.makedirs(os.path.dirname(os.path.join(folder, name)) or folder, exist_ok=True)
        with open(os.path.join(folder, name), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)


def test_an_unpacked_archive_folder_is_found_and_previews_like_the_zip(client, home):
    members = _person_archive("Sample", "Alice")
    members["messages.csv"] = "CONVERSATION ID,FROM,TO,DATE,CONTENT\n1,Someone,Sample,2024-01-01,private\n"
    members["Jobs/Job Applications.csv"] = "Application Date,Company Name\n"
    _unpack(home / "user" / "Downloads" / UNPACKED, members)
    (home / "user" / "Downloads" / "Holiday photos").mkdir()
    [hit] = client.post("/api/v1/archive/requested").json()["found"]
    assert hit["name"] == UNPACKED and hit["downloading"] is False

    from_folder = client.post("/api/v1/archive/preview", json={"source": "downloads:" + hit["path"]})
    assert from_folder.status_code == 200, from_folder.text
    from_zip = _upload(client, members)
    rows = lambda preview: {f["kind"]: f["rows"] for f in preview["files"]}  # noqa: E731
    assert rows(from_folder.json()) == rows(from_zip)
    assert {os.path.basename(f["file"]) for f in from_folder.json()["not_imported"]} == {
        "messages.csv", "Job Applications.csv"}

    res = _import(client, "downloads:" + hit["path"], confirm_owner=True)
    assert res.status_code == 200 and res.json()["summary"]["posts"]["added"] == 1
    assert os.path.isdir(hit["path"]), "the creator's own folder was removed"


def test_a_folder_without_linkedins_files_is_not_offered(client, home):
    folder = home / "user" / "Downloads" / UNPACKED
    folder.mkdir()
    (folder / "notes.txt").write_text("not an archive")
    assert client.post("/api/v1/archive/requested").json()["found"] == []


def test_a_folder_is_read_within_the_archive_limits(client, home, monkeypatch):
    _unpack(home / "user" / "Downloads" / UNPACKED, {"Skills.csv": "Name\n" + "Skill\n" * 2000})
    [hit] = client.post("/api/v1/archive/requested").json()["found"]
    monkeypatch.setattr(archive_import, "MAX_MEMBER_BYTES", 1000)
    res = client.post("/api/v1/archive/preview", json={"source": "downloads:" + hit["path"]})
    assert res.status_code == 400 and "larger than any file" in res.json()["detail"]
    monkeypatch.setattr(archive_import, "MAX_MEMBERS", 0)
    res = client.post("/api/v1/archive/preview", json={"source": "downloads:" + hit["path"]})
    assert res.status_code == 400 and "far more files" in res.json()["detail"]


@pytest.mark.skipif(not hasattr(os, "symlink") or sys.platform.startswith("win"), reason="symlinks")
def test_a_link_inside_the_folder_is_not_followed(client, home):
    folder = home / "user" / "Downloads" / UNPACKED
    _unpack(folder, {"Skills.csv": "Name\nSynthetic Skill\n"})
    secret = home / "elsewhere.csv"
    secret.write_text("First Name,Last Name,URL\nSecret,Person,https://www.linkedin.com/in/secret\n")
    os.symlink(secret, folder / "Connections.csv")
    [hit] = client.post("/api/v1/archive/requested").json()["found"]
    preview = client.post("/api/v1/archive/preview", json={"source": "downloads:" + hit["path"]}).json()
    assert [f["kind"] for f in preview["files"]] == ["skills"]


# ---------------------------------------------------------------------------
# SETUP-20: on Windows, a Downloads folder moved to another drive or into
# OneDrive is the one looked in, and the step says which it is
# ---------------------------------------------------------------------------

def _fake_winreg(value):
    import types

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    fake = types.ModuleType("winreg")
    fake.HKEY_CURRENT_USER = object()
    seen = []

    def open_key(root, path):
        seen.append(path)
        return Key()

    def query(key, name):
        if name != "{374DE290-123F-4565-9164-39C4925E467B}":
            raise OSError(name)
        return value, 2

    fake.OpenKey, fake.QueryValueEx, fake.seen = open_key, query, seen
    return fake


def test_a_moved_windows_downloads_folder_is_looked_in(client, home, monkeypatch):
    moved = home / "D" / "Downloads"
    moved.mkdir(parents=True)
    fake = _fake_winreg(str(moved))
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.setattr(sys, "platform", "win32")
    assert str(moved) in archive_import.downloads_dirs()
    assert any("User Shell Folders" in path for path in fake.seen)

    (moved / COMPLETE).write_bytes(_archive(_person_archive("Sample", "Alice")))
    state = client.post("/api/v1/archive/requested").json()
    assert [f["name"] for f in state["found"]] == [COMPLETE]
    assert str(moved) in state["watching"]


def test_elsewhere_the_registry_is_not_read(client, monkeypatch):
    fake = _fake_winreg("/nowhere")
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.setattr(sys, "platform", "linux")
    archive_import.downloads_dirs()
    assert fake.seen == []


# ---------------------------------------------------------------------------
# Review follow-ups
# ---------------------------------------------------------------------------

def _confirm_bob(client, **extra):
    res = client.post("/api/v1/identity/observe", json={
        "vanity": "sample-bob", "display_name": "Sample Bob", "self_evidence": ["owner_edit_controls"], **extra})
    assert res.status_code == 200, res.text
    assert client.post("/api/v1/identity/confirm", json={"vanity": "sample-bob"}).status_code == 200


def test_an_unpacked_folder_on_windows_is_not_still_downloading(client, home, monkeypatch):
    """SETUP-12: NTFS reports 0 bytes for a folder."""
    import stat as stat_module
    _unpack(home / "user" / "Downloads" / UNPACKED, _person_archive("Sample", "Bob"))
    real = os.stat

    class Folder:
        def __init__(self, st):
            self._st = st

        def __getattr__(self, name):
            return 0 if name == "st_size" else getattr(self._st, name)

    def windows_stat(path, *args, **kwargs):
        st = real(path, *args, **kwargs)
        return Folder(st) if stat_module.S_ISDIR(st.st_mode) else st

    monkeypatch.setattr(archive_import.os, "stat", windows_stat)
    [hit] = client.post("/api/v1/archive/requested").json()["found"]
    assert hit["folder"] is True and hit["downloading"] is False


@pytest.mark.parametrize("first,last", [("Sample", ""), ("Bob", ""), ("Sample", "Bob-Jones"), ("Bob", "Other")])
def test_a_partial_name_match_asks_first(client, first, last):
    """SETUP-01: one word, or an extra word, is not the confirmed creator's name."""
    _confirm_bob(client)
    preview = _upload(client, _person_archive(first, last))
    assert preview["needs_confirmation"], f"{first} {last} was taken for Sample Bob"


def test_the_same_name_in_another_order_or_case_is_the_creator(client):
    _confirm_bob(client)
    assert _upload(client, _person_archive("BOB", "Sámple"))["needs_confirmation"] == ""
