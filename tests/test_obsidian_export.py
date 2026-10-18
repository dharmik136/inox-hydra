"""
The Obsidian export writes the creator's record as a vault they can think in.
=============================================================================

Each test is one promise the export makes:

  - posts, people and topics link to each other, so the graph is the audience
  - a figure nobody read says "not measured", never 0
  - exporting again into the same vault keeps what the creator wrote
  - it refuses to write into a folder that is not one of its own exports
  - credentials never appear in it
  - the JSON and CSV export now carry the same record

They run against the real schema (init_db and every migration) in a throwaway
home. The column a Voyager capture wrote to for weeks did not exist, and only a
test against the real tables would have said so.
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from studio.backend import obsidian_export, paths, support  # noqa: E402

POST_URN = "urn:li:activity:7380000000000000001"
QUIET_URN = "urn:li:activity:7380000000000000002"
LI_AT = "AQEDA_notarealkey_obsidian_export_cookie"


@pytest.fixture
def creator(monkeypatch):
    """A fresh install with a confirmed creator, two posts, two engagers and some outbound."""
    home = tempfile.mkdtemp(prefix="inox_obsidian_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)

    from studio.backend.database import init_db
    init_db()

    conn = sqlite3.connect(paths.get_db_path())
    now = "2026-10-01T10:00:00+00:00"
    conn.execute(
        "INSERT OR REPLACE INTO creator_identity (id, vanity, display_name, headline, about, confirmed_at) "
        "VALUES (1, 'ada', 'Ada Lovelace', 'Analyst of engines', 'I write about machines that think.', ?)",
        (now,),
    )
    conn.execute(
        "INSERT INTO creator_positions (ordinal, title, company, date_range, observed_at) VALUES (0, 'Analyst', 'Engines Ltd', '1842 - Present', ?)",
        (now,),
    )
    conn.execute("INSERT INTO creator_skills (skill, observed_at) VALUES ('Mathematics', ?)", (now,))
    conn.execute(
        "INSERT INTO own_posts (activity_urn, text, published_at, reactions, comments, impressions, first_seen_at, last_seen_at) "
        "VALUES (?, ?, '2026-09-30T08:00:00+00:00', 42, 7, NULL, ?, ?)",
        (POST_URN, "Our AI agent pipeline: what broke first.\n\nThe second line.", now, now),
    )
    conn.execute(
        "INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) VALUES (?, ?, '2026-09-20T08:00:00+00:00', ?, ?)",
        (QUIET_URN, "Hiring: what I ask in every interview / and why: [notes]", now, now),
    )
    conn.execute(
        "INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, source, reactions) "
        "VALUES (?, '2026-10-01T08:00:00', '2026-10-01T08', 24, 'activity_page', 40)",
        (POST_URN,),
    )
    for lead_id, name in (("lead-grace", "Grace Hopper"), ("lead-alan", "Alan Turing")):
        conn.execute(
            "INSERT INTO leads (id, name, full_name, headline, company, status, icp_score) VALUES (?, ?, ?, 'Engineer', 'Navy', 'New Lead', 72)",
            (lead_id, name, name),
        )
    conn.execute(
        "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text) VALUES ('lead-grace', ?, 'COMMENT', 'This matches what we saw.')",
        (POST_URN,),
    )
    conn.execute(
        "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type) VALUES ('lead-grace', ?, 'LIKE')",
        (QUIET_URN.replace("activity", "ugcPost"),),
    )
    conn.execute(
        "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type) VALUES ('lead-alan', ?, 'LIKE')",
        (POST_URN,),
    )
    conn.execute(
        "INSERT INTO lead_stage_events (lead_id, from_status, to_status, changed_at) VALUES ('lead-grace', 'New Lead', 'Connected', '2026-10-02T09:00:00')"
    )
    conn.execute(
        "INSERT INTO outbound_engagements (target_activity_urn, target_author, target_excerpt, kind, my_text, my_text_key, first_seen_at, last_seen_at) "
        "VALUES ('urn:li:activity:7370000000000000009', 'Grace Hopper', 'Compilers are for people.', 'comment', 'Agreed, and then some.', 'k1', ?, ?)",
        (now, now),
    )
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('li_at', ?)", (LI_AT,))
    conn.commit()
    conn.close()

    yield home
    shutil.rmtree(home, ignore_errors=True)


def _read(root, relative):
    with open(os.path.join(root, relative), encoding="utf-8") as handle:
        return handle.read()


def _find(root, folder, starts):
    for name in os.listdir(os.path.join(root, folder)):
        if name.startswith(starts):
            return f"{folder}/{name}"
    raise AssertionError(f"no note in {folder} starting with {starts!r}: {os.listdir(os.path.join(root, folder))}")


def test_posts_people_and_topics_link_to_each_other(creator, tmp_path):
    result = obsidian_export.export_obsidian_vault(str(tmp_path / "vault"))
    root = result["path"]

    post = _read(root, _find(root, "Posts", "2026-09-30 Our AI agent pipeline"))
    assert "[[People/Grace Hopper|Grace Hopper]] comment" in post
    assert "This matches what we saw." in post
    assert "[[People/Alan Turing|Alan Turing]] like" in post
    assert "[[Topics/AI & Machine Learning|AI & Machine Learning]]" in post

    grace = _read(root, "People/Grace Hopper.md")
    assert "Our AI agent pipeline" in grace, "a person's note does not link the post they engaged with"
    # The second interaction carries a ugcPost URN for the same numeric id.
    assert "Hiring" in grace, "an interaction recorded against a ugcPost URN lost its post"
    assert "New Lead to Connected" in grace

    topic = _read(root, "Topics/AI & Machine Learning.md")
    assert "[[Posts/2026-09-30 Our AI agent pipeline" in topic

    outbound = _read(root, "Outbound/Grace Hopper.md")
    assert "[[People/Grace Hopper|Grace Hopper]]" in outbound, "someone who engaged back is not linked"

    me = _read(root, "Me.md")
    assert "Ada Lovelace" in me and "Analyst, Engines Ltd" in me and "Mathematics" in me

    assert result["counts"]["Posts"] == 2 and result["counts"]["People"] == 2


def test_a_figure_nobody_read_says_so(creator, tmp_path):
    root = obsidian_export.export_obsidian_vault(str(tmp_path / "vault"))["path"]
    post = _read(root, _find(root, "Posts", "2026-09-30"))
    assert "| not measured | 42 | 7 | not measured |" in post
    assert "impressions:" not in post.split("---")[1], "an unread figure was written as a property"


def test_names_are_safe_for_every_filesystem(creator, tmp_path):
    root = obsidian_export.export_obsidian_vault(str(tmp_path / "vault"))["path"]
    names = os.listdir(os.path.join(root, "Posts"))
    for name in names:
        assert not set('/\\:*?"<>|#^[]') & set(name), name
    assert any(n.startswith("2026-09-20 Hiring what I ask in every interview and why notes") for n in names), names


def test_exporting_again_keeps_what_you_wrote(creator, tmp_path):
    root = obsidian_export.export_obsidian_vault(str(tmp_path / "vault"))["path"]

    grace = os.path.join(root, "People", "Grace Hopper.md")
    with open(grace, "a", encoding="utf-8") as handle:
        handle.write("Met at the conference. Follow up in November.\n")
    mine = os.path.join(root, "My own idea.md")
    with open(mine, "w", encoding="utf-8") as handle:
        handle.write("Not generated.")

    again = obsidian_export.export_obsidian_vault(root)
    assert again["kept_your_notes"] >= 1
    text = _read(root, "People/Grace Hopper.md")
    assert "Met at the conference" in text, "re-exporting threw away the creator's notes"
    assert text.count(obsidian_export.YOUR_NOTES) == 1
    assert _read(root, "My own idea.md") == "Not generated."


def test_a_note_the_export_no_longer_writes_is_removed(creator, tmp_path):
    root = obsidian_export.export_obsidian_vault(str(tmp_path / "vault"))["path"]
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("DELETE FROM lead_interactions WHERE lead_id = 'lead-alan'")
    conn.execute("DELETE FROM leads WHERE id = 'lead-alan'")
    conn.commit()
    conn.close()

    result = obsidian_export.export_obsidian_vault(root)
    assert not os.path.exists(os.path.join(root, "People", "Alan Turing.md"))
    assert result["removed"] == 1


def test_it_will_not_write_into_someone_elses_folder(creator, tmp_path):
    existing = tmp_path / "my-vault"
    existing.mkdir()
    (existing / "Journal.md").write_text("private", encoding="utf-8")
    with pytest.raises(obsidian_export.ExportRefused):
        obsidian_export.export_obsidian_vault(str(existing))
    assert os.listdir(existing) == ["Journal.md"]


def test_credentials_never_reach_the_vault(creator, tmp_path):
    root = obsidian_export.export_obsidian_vault(str(tmp_path / "vault"))["path"]
    for folder, _, files in os.walk(root):
        for name in files:
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                assert LI_AT not in handle.read(), f"{name} carries the session cookie"


def test_an_unconfirmed_profile_is_not_exported_as_yours(creator, tmp_path):
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("UPDATE creator_identity SET confirmed_at = NULL")
    conn.commit()
    conn.close()
    root = obsidian_export.export_obsidian_vault(str(tmp_path / "vault"))["path"]
    me = _read(root, "Me.md")
    assert "Ada Lovelace" not in me
    assert "has not confirmed" in me


def test_the_json_export_carries_the_linkedin_record(creator):
    path = support.export_data(fmt="json")
    tables = json.load(open(path, encoding="utf-8"))["tables"]
    for table in ("own_posts", "post_metric_observations", "outbound_engagements",
                  "lead_stage_events", "creator_identity", "creator_positions", "creator_skills"):
        assert tables.get(table), f"{table} is missing from the export"
    assert "settings" not in tables
    assert LI_AT not in json.dumps(tables)


def test_the_support_export_writes_a_vault(creator):
    path = support.export_data(fmt="obsidian")
    assert os.path.isfile(os.path.join(path, "Home.md"))
    assert os.path.isfile(os.path.join(path, obsidian_export.MANIFEST))
    assert path.startswith(paths.get_app_home())
