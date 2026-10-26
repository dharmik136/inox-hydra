"""
Audience: among the people the bridge has seen, who keeps coming back, who has
gone quiet, and who is already a connection?
==============================================================================

Cycle 4, track 4, batch 4 of the sections report, and decision 3 (Leads keeps
its label; the set is called Audience).

Every list here is ordered by facts: how many of the creator's posts a person
engaged with, then how recently the studio first saw them do it. Never by the
ICP score, which is a keyword guess about a job title (today.py states the
rule). The repeat list says how many posts it rests on, because the bridge
reads engagers only on the posts the creator opened.

The connections join is by profile, and the two sides do not store the same
string: the extension writes https://www.linkedin.com/in/<percent-encoded>/
with a trailing slash for a comment, and the raw link for a reaction, which is
often a member id (/in/ACoAA...); LinkedIn's archive writes
https://www.linkedin.com/in/<vanity> with no slash. Both are read through
onboarding.normalise_vanity, the one canonical spelling, and a person the
bridge knows only by a member id is counted as unmatched, never guessed.

Strict Invariants:
- Zero em-dashes.
- No ordering of people by score.
"""

import io
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

UI = os.path.join(REPO_ROOT, "studio", "ui", "src")
ME = "audience-creator"


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _stamp(days_ago, hours=0):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


def _urn(days_ago, salt):
    moment = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


# Seven posts of the creator's, and one of someone else's.
POSTS = {name: (_urn(days, n), days) for n, (name, days) in enumerate(
    (("P1", 60), ("P2", 50), ("P3", 40), ("P4", 30), ("P5", 20), ("P6", 10), ("P7", 3)), start=1)}
SOMEONE_ELSES = _urn(45, 99)

# (lead id, name, score, company, profile link as the bridge stored it,
#  [(post, days ago first seen, kind, times seen)])
PEOPLE = (
    ("lead-a", "Asha Rao", 5.0, "Acme", "https://www.linkedin.com/in/Asha-Rao/",
     [("P1", 59, "COMMENT", 1), ("P2", 49, "LIKE", 3)]),
    ("lead-b", "Ben Okoro", 99.0, "Acme", "https://www.linkedin.com/in/ACoAABxyz123",
     [("P6", 9, "LIKE", 1), ("P7", 1, "COMMENT", 2)]),
    ("lead-c", "Cora Lind", 1.0, None, "https://www.linkedin.com/in/cora-lind",
     [("P5", 19, "LIKE", 1), ("P6", 8, "LIKE", 1), ("P7", 2, "LIKE", 1)]),
    ("lead-d", "Dev Patel", 50.0, "Northwind", "https://www.linkedin.com/in/dev-patel",
     [("P1", 58, "LIKE", 1)]),
    ("lead-e", "Eli Moss", 40.0, "", "https://www.linkedin.com/in/eli-moss",
     [("X", 44, "COMMENT", 1), ("P2", 48, "LIKE", 1)]),
    ("lead-f", "Fay Wu", 30.0, "Northwind", "https://www.linkedin.com/in/fay-wu",
     [("P3", 39, "LIKE", 1), ("P4", 29, "COMMENT", 1)]),
    ("lead-z", "Zoë Ölander", 20.0, "Ölander AB", "https://www.linkedin.com/in/zo%C3%AB-%C3%B6lander/",
     [("P4", 28, "LIKE", 1)]),
)

CONNECTIONS = (
    # As LinkedIn's archive writes them: no trailing slash, decoded.
    ("https://www.linkedin.com/in/asha-rao", "Asha", "Rao", "Acme", "Head of Platform", "05 Mar 2024"),
    ("https://www.linkedin.com/in/zoë-ölander", "Zoë", "Ölander", "Ölander AB", "Founder", "11 Jan 2023"),
    ("https://www.linkedin.com/in/someone-else", "Someone", "Else", "Elsewhere", "Engineer", "02 Feb 2022"),
)
IMPORTED_AT = "2026-09-01T10:00:00+00:00"


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t4_audience_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    from migrations import interaction_comment_key
    init_db()
    conn = get_db()
    with conn:
        conn.execute("INSERT OR REPLACE INTO creator_identity (id, vanity, display_name, confirmed_at) "
                     "VALUES (1, ?, 'Audience Creator', '2026-09-01T00:00:00+00:00')", (ME,))
        for name, (urn, days) in POSTS.items():
            published = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                         "VALUES (?, ?, ?, ?, ?)", (urn, f"Post {name}", published, _stamp(days), _stamp(days)))
        for lead_id, name, score, company, url, engagements in PEOPLE:
            conn.execute("INSERT INTO leads (id, name, full_name, headline, company, profile_url, linkedin_urn, "
                         "icp_score, lead_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'NEW', ?)",
                         (lead_id, name, name, f"Head of things at {company}", company, url, url, score, _stamp(1)))
            for post, days, kind, seen in engagements:
                urn = SOMEONE_ELSES if post == "X" else POSTS[post][0]
                text = f"{name} on {post}" if kind == "COMMENT" else None
                conn.execute(
                    "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text, interacted_at, "
                    "comment_key, first_seen_at, last_seen_at, seen_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (lead_id, urn, kind, text, _stamp(days), interaction_comment_key(text), _stamp(days),
                     _stamp(max(days - 1, 0)), seen))
        for url, first, last, company, position, connected in CONNECTIONS:
            conn.execute("INSERT INTO connections (profile_url, first_name, last_name, company, position, connected_on, "
                         "source, imported_at) VALUES (?, ?, ?, ?, ?, ?, 'archive', ?)",
                         (url, first, last, company, position, connected, IMPORTED_AT))
    conn.close()
    yield home
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture
def client(studio):
    from fastapi.testclient import TestClient
    import app as app_module
    return TestClient(app_module.app)


# ---------------------------------------------------------------------------
# Who keeps coming back
# ---------------------------------------------------------------------------

def test_repeat_engagers_are_ordered_by_posts_engaged_then_recency_never_by_score(client):
    body = client.get("/api/v1/audience").json()
    repeat = body["repeat"]
    assert repeat["posts_read"] == 7
    assert repeat["label"] == "among the 7 posts whose engagers were read"
    names = [(p["name"], p["posts_engaged"]) for p in repeat["people"]]
    # Cora (score 1) engaged with three posts and leads; Ben's 99 puts him no
    # higher than his two posts and his recency do. Eli's comment on someone
    # else's post does not count, so he is not a repeat engager.
    assert names == [("Cora Lind", 3), ("Ben Okoro", 2), ("Fay Wu", 2), ("Asha Rao", 2)]
    assert repeat["count"] == 4
    source = _read(os.path.join(REPO_ROOT, "studio", "backend", "audience.py"))
    assert "icp_score" not in source, "the audience module reads the score"


def test_a_repeat_engager_says_when_the_studio_first_and_last_saw_them_engage(client):
    people = {p["name"]: p for p in client.get("/api/v1/audience").json()["repeat"]["people"]}
    asha = people["Asha Rao"]
    assert asha["first_seen_at"][:10] == _stamp(59)[:10]
    assert asha["latest_at"][:10] == _stamp(49)[:10]


# ---------------------------------------------------------------------------
# Who has gone quiet
# ---------------------------------------------------------------------------

def test_gone_quiet_is_a_repeat_engager_not_seen_since_the_last_five_read_posts_began(client):
    quiet = client.get("/api/v1/audience").json()["quiet"]
    assert quiet["judged"] is True
    assert quiet["recent_posts"] == 5
    # The fifth most recent post whose engagers were read is P3, forty days old.
    assert quiet["since"][:10] == (datetime.now(timezone.utc) - timedelta(days=40)).date().isoformat()
    assert [p["name"] for p in quiet["people"]] == ["Asha Rao"]


def test_gone_quiet_abstains_until_enough_posts_were_read(client):
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM lead_interactions WHERE post_urn IN (?, ?, ?)",
                     (POSTS["P3"][0], POSTS["P4"][0], POSTS["P5"][0]))
    conn.close()
    quiet = client.get("/api/v1/audience").json()["quiet"]
    assert quiet["judged"] is False
    assert quiet["people"] == []
    assert quiet["posts_read"] == 4


# ---------------------------------------------------------------------------
# New people per week, a partial figure
# ---------------------------------------------------------------------------

def test_new_people_are_counted_in_the_week_the_studio_first_saw_them(client):
    weeks = client.get("/api/v1/audience").json()["new_people"]
    assert weeks["partial"] is True
    assert len(weeks["weeks"]) == 12
    by_week = {w["week"]: w for w in weeks["weeks"]}

    def monday(days_ago):
        d = (datetime.now(timezone.utc) - timedelta(days=days_ago)).date()
        return (d - timedelta(days=d.weekday())).isoformat()

    # Cora was first seen 19 days ago on P5; Fay 39 days ago.
    assert by_week[monday(19)]["new"] >= 1
    assert by_week[monday(39)]["new"] >= 1
    # Every person whose first engagement on one of your posts is inside the
    # twelve weeks is counted once, in a week the bridge read.
    assert sum(w["new"] for w in weeks["weeks"] if w["read"]) == 7


def test_a_week_the_bridge_read_nothing_is_not_a_week_of_zero(client):
    weeks = client.get("/api/v1/audience").json()["new_people"]["weeks"]
    silent = [w for w in weeks if not w["read"]]
    assert silent, "the fixture has weeks with nothing read"
    for week in silent:
        assert week["new"] is None, "a week the bridge read nothing reads as zero new people"


# ---------------------------------------------------------------------------
# Who is already a connection: the join by profile
# ---------------------------------------------------------------------------

def test_connections_are_joined_by_the_one_canonical_profile_spelling(client):
    body = client.get("/api/v1/audience").json()["connections"]
    assert body["count"] == 3
    assert body["as_of"] == IMPORTED_AT
    assert body["leads_matched"] == 2, "Asha (slash and capitals) and Zoë (percent-encoded) are both connections"
    assert body["leads_by_member_id"] == 1, "Ben is known only by a member id and cannot be matched"


def test_the_connections_list_is_searchable_and_marks_who_is_a_lead(client):
    everyone = client.get("/api/v1/audience/connections").json()
    assert everyone["total"] == 3
    assert everyone["as_of"] == IMPORTED_AT
    found = client.get("/api/v1/audience/connections?q=asha").json()
    assert [c["name"] for c in found["connections"]] == ["Asha Rao"]
    assert found["connections"][0]["lead_id"] == "lead-a"
    assert found["connections"][0]["connected_on"] == "05 Mar 2024"
    zoe = client.get("/api/v1/audience/connections?q=lander").json()["connections"]
    assert [c["lead_id"] for c in zoe] == ["lead-z"]
    nobody = client.get("/api/v1/audience/connections?q=someone").json()["connections"]
    assert nobody[0]["lead_id"] is None


def test_the_connections_list_is_ordered_by_name_not_by_anything_about_the_person(client):
    names = [c["name"] for c in client.get("/api/v1/audience/connections").json()["connections"]]
    assert names == sorted(names, key=lambda n: (n.split()[-1].lower(), n.lower()))


def test_without_an_archive_the_connections_block_says_so(client):
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM connections")
    conn.close()
    body = client.get("/api/v1/audience").json()["connections"]
    assert body["count"] == 0 and body["as_of"] is None


# ---------------------------------------------------------------------------
# The second level: the funnel and companies, as counts
# ---------------------------------------------------------------------------

def test_the_funnel_is_the_crm_telemetry_funnel_and_nothing_else(client):
    from crm import reverse_crm
    counts = client.get("/api/v1/audience/counts").json()
    assert [(f["status"], f["people"]) for f in counts["funnel"]] == list(reverse_crm.get_crm_telemetry()["funnel"].items())
    assert all(f["label"] for f in counts["funnel"]), "a stage is shown by its code rather than its name"
    flat = repr(counts).lower()
    for guess in ("icp", "tier", "qualified", "seniority", "score", "conversion"):
        assert guess not in flat, f"the counts carry {guess}"


def test_companies_are_counted_as_the_headline_names_them(client):
    counts = client.get("/api/v1/audience/counts").json()
    companies = {c["company"]: c["people"] for c in counts["companies"]}
    assert companies["Acme"] == 2 and companies["Northwind"] == 2 and companies["Ölander AB"] == 1
    assert counts["no_company"] == 2, "Cora names none and Eli's is empty"
    assert [c["company"] for c in counts["companies"]][:2] == ["Acme", "Northwind"]


# ---------------------------------------------------------------------------
# The Leads dossier: first, last and times seen, and connected since
# ---------------------------------------------------------------------------

def test_the_dossier_facts_come_from_the_interactions(client):
    asha = client.get("/api/v1/audience/people/lead-a").json()
    assert asha["first_seen_at"][:10] == _stamp(59)[:10]
    assert asha["last_seen_at"][:10] == _stamp(48)[:10]
    assert asha["times_seen"] == 4, "one comment seen once and one reaction seen three times"
    assert asha["engagements"] == 2
    assert asha["connection"] == {"connected_on": "05 Mar 2024", "as_of": IMPORTED_AT}
    assert asha["member_id_only"] is False
    assert asha["connections_held"] == 3 and asha["connections_as_of"] == IMPORTED_AT


def test_the_dossier_says_why_a_person_cannot_be_matched_to_a_connection(client):
    ben = client.get("/api/v1/audience/people/lead-b").json()
    assert ben["connection"] is None and ben["member_id_only"] is True


def test_a_lead_the_bridge_never_saw_has_no_seen_figures(client):
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO leads (id, name, created_at) VALUES ('lead-hand', 'Added By Hand', ?)", (_stamp(3),))
    conn.close()
    hand = client.get("/api/v1/audience/people/lead-hand").json()
    assert hand["first_seen_at"] is None and hand["last_seen_at"] is None
    assert hand["times_seen"] is None and hand["engagements"] == 0


def test_an_unknown_lead_is_refused(client):
    assert client.get("/api/v1/audience/people/no-such-lead").status_code == 404


def test_the_dossier_draws_the_three_facts_and_the_connection():
    surface = _read(os.path.join(UI, "components", "LeadsSurface.tsx"))
    for words in ("First seen", "Last seen", "Times seen", "Connected since"):
        assert words in surface, f"the dossier does not draw {words}"
    assert "fetchAudiencePerson" in surface


# ---------------------------------------------------------------------------
# What the screen says
# ---------------------------------------------------------------------------

def test_the_screen_labels_each_list_with_what_it_rests_on():
    surface = _read(os.path.join(UI, "components", "AudienceSurface.tsx"))
    assert "repeat.label" in surface, "the repeat list is shown without the posts it rests on"
    assert "as of" in surface.lower(), "the connections are shown without their import date"
    assert "partial" in surface.lower(), "new people per week is shown without its partial label"


def test_audience_has_a_help_article_filed_for_a_creator():
    import docs_engine
    shipped = [path for section in docs_engine.HELP_SECTIONS if section["id"] != "maintainers"
               for path in section["paths"]]
    assert "help/see-who-keeps-coming-back.md" in shipped
    article = _read(os.path.join(REPO_ROOT, "docs", "help", "see-who-keeps-coming-back.md"))
    for words in ("whose engagers were read", "member", "as of", "score"):
        assert words in article, f"the help does not explain {words!r}"


# ---------------------------------------------------------------------------
# The kept answer is the answer a rebuild gives
#
# Summing every interaction on each visit cost about 700 ms on a three year
# install, so audience.py keeps the per-person engagement and brings it
# current from the rows added since. These hold that what it keeps is what a
# rebuild from nothing would say, in each way the rows can change.
# ---------------------------------------------------------------------------

def _rebuilt(client):
    import audience
    with audience._engagement_lock:
        audience._engagement.key = None
    return client.get("/api/v1/audience").json()


def _lists(body):
    return body["repeat"], body["quiet"], body["new_people"]


def _engage(lead_id, urn, kind="LIKE", days=0):
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, interacted_at, comment_key, "
            "first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, '', ?, ?)",
            (lead_id, urn, kind, _stamp(days), _stamp(days), _stamp(days)))
    conn.close()


def test_a_capture_after_the_first_visit_is_added_without_a_rebuild(client):
    import audience
    client.get("/api/v1/audience")
    rebuilds = audience._engagement.rebuilds
    _engage("lead-d", POSTS["P7"][0])
    kept = client.get("/api/v1/audience").json()
    assert audience._engagement.rebuilds == rebuilds, "one new capture rebuilt the whole history"
    dev = [p for p in kept["repeat"]["people"] if p["name"] == "Dev Patel"]
    assert dev and dev[0]["posts_engaged"] == 2
    # Checked as a value too: a fault in the code a rebuild shares would
    # make the two answers agree and still be wrong.
    assert dev[0]["latest_at"][:10] == _stamp(0)[:10], "the new engagement did not move when he was last seen"
    assert _lists(kept) == _lists(_rebuilt(client))


def test_a_removed_engagement_is_never_kept(client):
    from database import get_db
    client.get("/api/v1/audience")
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM leads WHERE id = 'lead-c'")
    conn.close()
    kept = client.get("/api/v1/audience").json()
    assert "Cora Lind" not in [p["name"] for p in kept["repeat"]["people"]], "a forgotten person is still listed"
    assert _lists(kept) == _lists(_rebuilt(client))


def test_a_post_that_becomes_yours_after_its_engagers_were_read_is_adopted(client):
    import audience
    from database import get_db
    late = _urn(15, 42)
    _engage("lead-e", late, days=14)
    _engage("lead-d", late, days=14)
    first = client.get("/api/v1/audience").json()
    assert "Eli Moss" not in [p["name"] for p in first["repeat"]["people"]]
    rebuilds = audience._engagement.rebuilds

    conn = get_db()
    with conn:
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                     "VALUES (?, 'A post read late', ?, ?, ?)",
                     (late, (datetime.now(timezone.utc) - timedelta(days=15)).isoformat(), _stamp(1), _stamp(1)))
    conn.close()
    kept = client.get("/api/v1/audience").json()
    assert audience._engagement.rebuilds == rebuilds, "a post read late rebuilt the whole history"
    assert kept["repeat"]["posts_read"] == 8
    names = {p["name"]: p["posts_engaged"] for p in kept["repeat"]["people"]}
    assert names.get("Eli Moss") == 2 and names.get("Dev Patel") == 2
    assert _lists(kept) == _lists(_rebuilt(client))
