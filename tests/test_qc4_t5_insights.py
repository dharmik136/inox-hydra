"""
Cycle 4, track 5, phase 2: the creator's own surfaces nothing read before.
==========================================================================

On the owner's direction to capture more and show it:

  account figures   profile views, search appearances and new followers by
                    day, each a dated series with its window and precision
  own content       an article's and a newsletter's analytics pages, and a
                    video's watch time on its post analytics page
  account pages     "Who viewed your profile" and search appearances:
                    counts and their windows only, never a viewer's name
  activity tab      the creator's own reposts (that it is one, its date, its
                    own figures; never the original's author or words) and
                    the "edited" flag on their own posts

Every new label follows the owner's rule of 2026-10-26: absent is not read,
never drift, never 0, and each new field joins the sightings route. Each
test runs in a throwaway home of its own.
"""

import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
sys.path.insert(0, BACKEND)

ME = "t5p2-creator"
NOW = datetime.now(timezone.utc).replace(microsecond=0)
TODAY = NOW.strftime("%Y-%m-%d")
ARTICLE = "urn:li:linkedInArticle:7390000000000000001"
NEWSLETTER = "urn:li:fsd_contentSeries:7390000000000000002"


def urn_hours_ago(hours, salt=0):
    moment = NOW - timedelta(hours=hours)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc4_t5p2_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    import results
    init_db()
    results.forget_cache()
    yield path
    results.forget_cache()
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def client(home):
    from fastapi.testclient import TestClient
    import app as app_module
    c = TestClient(app_module.app)
    c.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                             "display_name": "T5 Phase Two"})
    c.post("/api/v1/identity/confirm", json={"vanity": ME})
    return c


def _db():
    from database import get_db
    return get_db()


def _page(client, page, readings=None, **extra):
    return client.post("/api/analytics/page-figures", json={"author": ME, "page": page, "readings": readings or [],
                                                             **extra})


def _rows(sql, *params):
    conn = _db()
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The migration
# ---------------------------------------------------------------------------

def test_the_phase_has_one_migration_named_for_what_it_adds(home):
    import migrations
    mine = [m for m in migrations.MIGRATIONS if "account figures" in m[1].lower()]
    assert len(mine) == 1, "exactly one migration for this phase, found by its name"
    conn = _db()
    try:
        def columns(table):
            return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        assert {"page", "content_urn", "observed_at", "observed_hour", "period_label", "precision", "profile_views",
                "search_appearances", "views", "impressions", "members_reached", "reactions", "comments", "reposts",
                "subscribers", "email_sends", "email_open_rate_pct"} <= columns("insight_readings")
        assert {"date", "figure", "value", "precision", "source", "observed_at"} <= columns("insight_daily_points")
        assert {"activity_urn", "reposted_at", "reactions", "comments", "reposts", "impressions", "first_seen_at",
                "last_seen_at"} <= columns("own_reposts")
        assert not {"author", "actor", "text", "original_urn"} & columns("own_reposts"), "nothing about the original"
        assert "edited_first_seen_at" in columns("own_posts")
        assert {"watch_time_seconds", "average_watch_seconds"} <= columns("post_metric_observations")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Account figures: each with its window and precision, never without one
# ---------------------------------------------------------------------------

def test_account_figures_are_kept_with_their_window_and_never_without_one(client):
    answer = _page(client, "account_analytics", readings=[
        {"period_label": "90d", "precision": "exact", "figures": {"profile_views": 412}},
        {"period_label": "7d", "precision": "rounded", "figures": {"search_appearances": 1200}},
        {"period_label": "", "precision": "exact", "figures": {"profile_views": 999}},
        {"period_label": "unrecognised", "figures": {"search_appearances": 5}},
    ]).json()
    assert answer["status"] == "success" and answer["readings_recorded"] == 2
    rows = _rows("SELECT page, period_label, precision, profile_views, search_appearances, views FROM insight_readings "
                 "ORDER BY period_label")
    assert rows == [
        {"page": "account_analytics", "period_label": "7d", "precision": "rounded", "profile_views": None,
         "search_appearances": 1200, "views": None},
        {"page": "account_analytics", "period_label": "90d", "precision": "exact", "profile_views": 412,
         "search_appearances": None, "views": None},
    ], "a count with no window it names is not stored, and nothing unread becomes 0"


def test_the_author_must_be_the_confirmed_creator(client):
    refused = client.post("/api/analytics/page-figures", json={
        "author": "someone-else", "page": "profile_views",
        "readings": [{"period_label": "90d", "figures": {"profile_views": 4}}]})
    assert refused.status_code == 409
    nobody = client.post("/api/analytics/page-figures", json={
        "page": "profile_views", "readings": [{"period_label": "90d", "figures": {"profile_views": 4}}]})
    assert nobody.status_code == 409
    assert _rows("SELECT COUNT(*) AS n FROM insight_readings")[0]["n"] == 0


def test_a_page_the_studio_does_not_know_and_a_figure_it_does_not_know_store_nothing(client):
    assert _page(client, "somewhere_else", readings=[{"period_label": "7d", "figures": {"views": 3}}]).status_code == 409
    _page(client, "profile_views", readings=[{"period_label": "90d", "figures": {"viewer_names": ["Ada"], "views": 7}}])
    assert _rows("SELECT COUNT(*) AS n FROM insight_readings")[0]["n"] == 0, (
        "the profile views page keeps profile views and nothing else")


def test_the_profile_views_and_search_appearances_pages_keep_counts_and_windows_only(client):
    _page(client, "profile_views", readings=[{"period_label": "90d", "precision": "exact",
                                              "figures": {"profile_views": 412}}])
    _page(client, "search_appearances", readings=[{"period_label": "7d", "precision": "exact",
                                                   "figures": {"search_appearances": 57}}])
    rows = _rows("SELECT page, period_label, profile_views, search_appearances FROM insight_readings ORDER BY page")
    assert rows == [
        {"page": "profile_views", "period_label": "90d", "profile_views": 412, "search_appearances": None},
        {"page": "search_appearances", "period_label": "7d", "profile_views": None, "search_appearances": 57},
    ]


def test_new_followers_by_day_are_a_dated_series(client):
    _page(client, "account_analytics", points=[
        {"date": "2031-03-01", "figure": "new_followers", "value": 12, "precision": "exact"},
        {"date": "2031-03-02", "figure": "new_followers", "value": 9, "precision": "exact"},
        {"date": "March 3", "figure": "new_followers", "value": 4},
        {"date": "2031-03-04", "figure": "new_followers", "value": -1},
        {"date": "2031-03-05", "figure": "unfollowers", "value": 2},
    ])
    _page(client, "account_analytics", points=[{"date": "2031-03-02", "figure": "new_followers", "value": 11}])
    rows = _rows("SELECT date, figure, value FROM insight_daily_points ORDER BY date")
    assert rows == [{"date": "2031-03-01", "figure": "new_followers", "value": 12},
                    {"date": "2031-03-02", "figure": "new_followers", "value": 11}], (
        "a point with no readable day, a negative count or an unknown figure is not kept; a re-read updates the day")


def test_the_account_figures_route_shows_profile_views_again(client):
    """Sections decision 8 removed profile views from Analytics until a reader existed."""
    _page(client, "profile_views", readings=[{"period_label": "90d", "precision": "exact",
                                              "figures": {"profile_views": 412}}])
    _page(client, "account_analytics", readings=[{"period_label": "7d", "precision": "exact",
                                                  "figures": {"search_appearances": 57}}],
          points=[{"date": TODAY, "figure": "new_followers", "value": 12, "precision": "exact"}])
    body = client.get("/api/analytics/account-figures?range=30d").json()
    assert body["status"] == "success"
    views = body["profile_views"]
    assert [(r["value"], r["period_label"], r["covers"], r["source"]) for r in views] == [
        (412, "90d", "90 days", "profile_views")]
    assert [(r["value"], r["covers"]) for r in body["search_appearances"]] == [(57, "7 days")]
    assert [(p["date"], p["value"]) for p in body["new_followers"]] == [(TODAY, 12)]


# ---------------------------------------------------------------------------
# Own content: an article's and a newsletter's analytics pages
# ---------------------------------------------------------------------------

def test_a_content_page_needs_its_content_and_keeps_each_figure_by_content(client):
    assert _page(client, "article_analytics", readings=[{"period_label": "", "figures": {"views": 9}}]).status_code == 409
    _page(client, "article_analytics", content_urn=ARTICLE,
          readings=[{"period_label": "", "precision": "exact", "figures": {"views": 900, "reactions": 12}}])
    _page(client, "newsletter_analytics", content_urn=NEWSLETTER,
          readings=[{"period_label": "28d", "precision": "rounded",
                     "figures": {"subscribers": 1200, "email_sends": 800, "email_open_rate_pct": 42.5}}])
    rows = _rows("SELECT page, content_urn, period_label, views, reactions, comments, subscribers, email_sends, "
                 "email_open_rate_pct FROM insight_readings ORDER BY page")
    assert rows == [
        {"page": "article_analytics", "content_urn": ARTICLE, "period_label": "", "views": 900, "reactions": 12,
         "comments": None, "subscribers": None, "email_sends": None, "email_open_rate_pct": None},
        {"page": "newsletter_analytics", "content_urn": NEWSLETTER, "period_label": "28d", "views": None,
         "reactions": None, "comments": None, "subscribers": 1200, "email_sends": 800, "email_open_rate_pct": 42.5},
    ]
    content = {c["content_urn"]: c for c in client.get("/api/analytics/content-figures").json()["content"]}
    assert content[ARTICLE]["kind"] == "article" and content[ARTICLE]["latest"]["views"]["value"] == 900
    assert content[NEWSLETTER]["latest"]["subscribers"] == {
        "value": 1200, "read_at": content[NEWSLETTER]["latest"]["subscribers"]["read_at"], "period_label": "28d",
        "precision": "rounded"}


def test_each_content_figure_is_the_newest_reading_that_has_it(client):
    """The rule of review S2, for content readings too."""
    conn = _db()
    with conn:
        for hour, views, reactions in (("2031-03-01T10", 900, 12), ("2031-03-02T10", 950, None)):
            conn.execute("INSERT INTO insight_readings (page, content_urn, observed_at, observed_hour, period_label, "
                         "views, reactions) VALUES ('article_analytics', ?, ?, ?, '', ?, ?)",
                         (ARTICLE, hour + ":00:00+00:00", hour, views, reactions))
    conn.close()
    latest = client.get("/api/analytics/content-figures").json()["content"][0]["latest"]
    assert latest["views"]["value"] == 950 and latest["reactions"]["value"] == 12
    assert latest["reactions"]["read_at"] < latest["views"]["read_at"]


# ---------------------------------------------------------------------------
# A video's watch time, on its post analytics page
# ---------------------------------------------------------------------------

def test_watch_time_lands_in_the_post_reading(client):
    import onboarding
    mine = urn_hours_ago(30)
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": mine, "actor": ME, "text": "A video of mine"}]})
    client.post("/api/v1/self/posts/analytics", json={"author": ME, "activity_urn": mine, "metrics": {
        "impressions": 4100, "video_views": 900, "watch_time_seconds": 45000, "average_watch_seconds": 38}})
    reading = onboarding.post_readings(mine)[0]
    assert (reading["watch_time_seconds"], reading["average_watch_seconds"]) == (45000, 38)
    per_post = client.get(f"/api/v1/insights/posts/{mine}").json()["per_post"]
    assert per_post["watch_time_seconds"]["value"] == 45000 and per_post["average_watch_seconds"]["value"] == 38


# ---------------------------------------------------------------------------
# The activity tab: own reposts and the edited flag
# ---------------------------------------------------------------------------

def test_an_own_repost_keeps_only_that_it_is_one_its_date_and_its_own_figures(client):
    repost = urn_hours_ago(50, 3)
    instant = urn_hours_ago(60, 4)
    answer = client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": repost, "actor": "stranger-author", "text": "The original author's own words",
         "reactions": 300, "own_repost": True, "own_figures": {"reactions": 4, "comments": 1}},
        {"activity_urn": instant, "actor": "repost", "text": "More of someone else's words", "reactions": 80,
         "own_repost": True},
    ]}).json()
    assert answer["reposts_recorded"] == 2 and answer["written"] == 0
    rows = {r["activity_urn"]: r for r in _rows("SELECT * FROM own_reposts")}
    assert rows[repost]["reactions"] == 4 and rows[repost]["comments"] == 1 and rows[repost]["impressions"] is None
    assert rows[instant]["reactions"] is None, "the original's counts are never kept as the repost's own"
    assert rows[repost]["reposted_at"] and rows[repost]["reposted_at"].startswith(
        (NOW - timedelta(hours=50)).strftime("%Y-%m-%d"))
    stored = " ".join(str(v) for row in rows.values() for v in row.values())
    assert "stranger" not in stored and "words" not in stored, "nothing about the original is kept"
    assert _rows("SELECT COUNT(*) AS n FROM own_posts")[0]["n"] == 0, "a repost is never filed as the creator's post"
    listed = client.get("/api/v1/insights/reposts").json()["reposts"]
    assert {r["activity_urn"] for r in listed} == {repost, instant}
    assert not {"author", "actor", "text"} & set(listed[0])


def test_the_edited_flag_is_kept_the_first_time_a_post_is_seen_edited(client):
    mine = urn_hours_ago(70, 5)
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": mine, "actor": ME, "text": "My post", "edited": True}]})
    first = _rows("SELECT edited_first_seen_at FROM own_posts WHERE activity_urn = ?", mine)[0]["edited_first_seen_at"]
    assert first
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": mine, "actor": ME, "text": "My post", "edited": True}]})
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": mine, "actor": ME, "text": "My post"}]})
    assert _rows("SELECT edited_first_seen_at FROM own_posts WHERE activity_urn = ?",
                 mine)[0]["edited_first_seen_at"] == first, "first seen edited stays the first time"
    assert client.get(f"/api/v1/insights/posts/{mine}").json()["edited_first_seen_at"] == first


# ---------------------------------------------------------------------------
# Every new field joins the sightings route
# ---------------------------------------------------------------------------

def test_every_new_field_joins_the_sightings_route(client):
    _page(client, "account_analytics", readings=[{"period_label": "90d", "figures": {"profile_views": 412}}])
    conn = _db()
    with conn:
        conn.execute("UPDATE insight_readings SET observed_hour = 'earlier', observed_at = ?",
                     ((NOW - timedelta(hours=3)).isoformat(),))
    conn.close()
    _page(client, "account_analytics", readings=[{"period_label": "7d", "figures": {"search_appearances": 57}}])
    body = client.get("/api/analytics/post-field-sightings").json()
    post_fields = {f["field"] for f in body["fields"]}
    assert {"watch_time_seconds", "average_watch_seconds"} <= post_fields
    pages = {p["page"]: p for p in body["pages"]}
    assert set(pages) == {"account_analytics", "profile_views", "search_appearances", "article_analytics",
                          "newsletter_analytics", "activity"}
    account = {f["field"]: f for f in pages["account_analytics"]["fields"]}
    assert set(account) == {"profile_views", "search_appearances", "new_followers"}
    assert pages["account_analytics"]["readings"] == 2
    assert account["profile_views"]["readings_since"] == 1 and account["search_appearances"]["readings_since"] == 0
    assert account["new_followers"]["last_read_at"] is None and account["new_followers"]["readings_since"] == 2
    assert account["profile_views"]["sentence"].startswith("profile views: not read on the latest")
    assert {f["field"] for f in pages["newsletter_analytics"]["fields"]} == {
        "subscribers", "views", "impressions", "email_sends", "email_open_rate_pct"}
    assert {f["field"] for f in pages["activity"]["fields"]} == {"own_reposts", "edited"}
    assert pages["profile_views"]["fields"][0]["sentence"] == "profile views: no profile views page read yet"


# ---------------------------------------------------------------------------
# The creator's record: export, and where the Storage panel files it
# ---------------------------------------------------------------------------

def test_the_export_carries_the_new_readings_and_the_storage_panel_files_them(client, tmp_path):
    import json
    import retention
    import support
    _page(client, "profile_views", readings=[{"period_label": "90d", "figures": {"profile_views": 412}}],)
    path = support.export_data(str(tmp_path / "export.json"), fmt="json")
    with open(path, encoding="utf-8") as handle:
        tables = json.load(handle)["tables"]
    assert [r["profile_views"] for r in tables["insight_readings"]] == [412]
    assert "insight_daily_points" in tables and "own_reposts" in tables
    filed = {table for _key, _label, names in retention.CATEGORIES for table in names}
    assert {"insight_readings", "insight_daily_points", "own_reposts", "analytics_windows",
            "audience_demographic_readings"} <= filed, "a table the Storage panel files under 'other' is lost in it"


# ---------------------------------------------------------------------------
# The extension's wiring: loaded where its helpers are, and its writes relayed
# ---------------------------------------------------------------------------

EXT = os.path.join(REPO_ROOT, "studio", "extension")


def _text_of(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as handle:
        return handle.read()


def test_the_manifest_loads_own_insights_after_the_helpers_it_uses():
    """It calls content.js's parseMetricValue, analyticsPeriodOf and studioApi, which exist only after content.js."""
    import json
    manifest = json.loads(_text_of(EXT, "manifest.json"))
    entries = [entry["js"] for entry in manifest["content_scripts"] if "own_insights.js" in entry["js"]]
    assert len(entries) == 1, "own_insights.js is loaded once"
    scripts = entries[0]
    assert "content.js" in scripts and scripts.index("content.js") < scripts.index("own_insights.js")
    assert scripts.index("own_pages.js") < scripts.index("own_insights.js")


def test_every_studio_path_own_insights_calls_is_relayed_and_served():
    own = _text_of(EXT, "own_insights.js")
    background = _text_of(EXT, "background.js")
    called = set(re.findall(r'"(/api/[^"]+)"', own))
    assert called == {"/api/analytics/page-figures"}
    allow = set(re.findall(r'"(/api/[^"]+)"', background.split("RELAYABLE_PATHS")[1].split("]);")[0]))
    assert called <= allow, f"the worker refuses to relay {sorted(called - allow)}, so those reads are lost silently"
    routers = _text_of(BACKEND, "routers", "analytics.py")
    for path in called:
        assert f'@router.post("{path}")' in routers


def test_own_insights_never_requests_anything_from_linkedin():
    own = _text_of(EXT, "own_insights.js")
    assert not re.search(r"\bfetch\s*\(|XMLHttpRequest|\.open\(\s*['\"](GET|POST)", own)


# ---------------------------------------------------------------------------
# The privacy policy names what own_insights.js keeps
# ---------------------------------------------------------------------------

POLICY_PATH = os.path.join(REPO_ROOT, "docs", "PRIVACY_POLICY.md")
INSIGHT_WORDS = {
    "profile_views": "profile views", "search_appearances": "search appearances", "views": "article views",
    "impressions": "impressions", "members_reached": "members reached", "reactions": "reactions",
    "comments": "comments", "reposts": "reposts", "subscribers": "subscribers", "email_sends": "email sends",
    "email_open_rate_pct": "open rate",
}


def _insight_keys(source):
    match = re.search(r"const LABELS = \{(.*?)\n  \};", source, re.DOTALL)
    assert match, "LABELS is gone from own_insights.js"
    return set(re.findall(r'\["[^"]+", "([a-z_]+)"\]', match.group(1)))


def _insight_paragraph(policy):
    match = re.search(r"From \*\*your own account and content analytics pages\*\*.*?(?:\n\n|\Z)", policy, re.DOTALL)
    assert match, "the policy has no paragraph for the pages own_insights.js reads"
    return " ".join(match.group(0).split()).lower()


def _insight_disagreements(source, policy):
    keys, paragraph = _insight_keys(source), _insight_paragraph(policy)
    problems = [f"own_insights.js keeps {key}, which the test does not know how the policy names"
                for key in sorted(keys - set(INSIGHT_WORDS))]
    problems += [f"the policy does not name {INSIGHT_WORDS[key]!r}" for key in sorted(keys & set(INSIGHT_WORDS))
                 if INSIGHT_WORDS[key] not in paragraph]
    for words in ("own_insights.js", "new followers", "never a viewer", "reposted", "never the original",
                  "marked edited", "window"):
        if words not in paragraph:
            problems.append(f"the paragraph does not say {words!r}")
    return problems


def test_the_privacy_policy_names_everything_own_insights_keeps():
    problems = _insight_disagreements(_text_of(EXT, "own_insights.js"), _text_of(POLICY_PATH))
    assert not problems, "the policy and own_insights.js disagree:\n" + "\n".join(problems)


def test_the_own_insights_policy_guard_is_not_vacuous():
    source, policy = _text_of(EXT, "own_insights.js"), _text_of(POLICY_PATH)
    planted = source.replace('["subscribers", "subscribers"],', '["subscribers", "subscribers"], ["unsubscribes", "unsubscribes"],', 1)
    assert any("unsubscribes" in p for p in _insight_disagreements(planted, policy))
    start = policy.index("From **your own account and content analytics pages**")
    end = policy.index("\n\n", start)
    dropped = policy[:start] + policy[start:end].replace("subscribers", "readers", 1) + policy[end:]
    assert any("'subscribers'" in p for p in _insight_disagreements(source, dropped))
