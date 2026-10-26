"""
Nobody is ordered by the ICP score.
===================================

today.py states the rule for one screen: "What it will not do is rank people
by the ICP score. That number is a keyword guess about a job title; who
engaged with you twice this week is a fact." Two routes broke it anyway.
GET /api/v1/posts/{id}/engagers answered ORDER BY l.icp_score DESC, and the
Posts detail drew the list in that order; crm.get_post_attribution answered
ORDER BY sort_score DESC, an alias of the same column, and Analytics drew
it in server order. So a creator who opened a post saw the people it brought
listed by a guess about their job titles, under a product that says it does
not do that (cycle 4, track 3, batch 0).

The rule is now the backend's rather than one screen's. No SQL in the
backend orders people by a score column or by an alias of one, and no
Python sort keys on one. People come out in the order of facts: when they
engaged, newest first.

The guard is falsified below by handing it the exact ordering the engagers
route used to carry and asserting it is caught; it was also planted back
into the route once, and this file failed, before it was kept.
"""

import os
import re
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
sys.path.insert(0, BACKEND)

# Orderings that mention a score but are not about people: viral templates are
# ranked by their own velocity score, which is a property of a hook, not a
# guess about a person.
NOT_PEOPLE = {"velocity_score"}

_ORDER_BY = re.compile(r"ORDER\s+BY\s+([^\n]*)", re.IGNORECASE)
_ALIAS = re.compile(r"\b[\w.]*score\w*\s+AS\s+(\w+)", re.IGNORECASE)
_PY_SORT = re.compile(r"\bsort(?:ed)?\([^\n]*(icp_score|sort_score)", re.IGNORECASE)


def _ranked_by_score(source: str):
    """Every line of `source` that orders rows by a score, as (line number, line)."""
    aliases = {name.lower() for name in _ALIAS.findall(source)}
    found = []
    for number, line in enumerate(source.splitlines(), 1):
        code = line.split("#")[0]
        match = _ORDER_BY.search(code)
        if match:
            for term in match.group(1).split(","):
                name = re.sub(r"\b(ASC|DESC|NULLS\s+(FIRST|LAST))\b", "", term, flags=re.IGNORECASE).strip()
                name = name.split(".")[-1].strip(" ()").lower()
                if (("score" in name and name not in NOT_PEOPLE) or name in aliases):
                    found.append((number, line.strip()))
                    break
        if _PY_SORT.search(code):
            found.append((number, line.strip()))
    return found


def _python_files():
    for root, _dirs, files in os.walk(BACKEND):
        for name in sorted(files):
            if name.endswith(".py"):
                path = os.path.join(root, name)
                yield os.path.relpath(path, BACKEND), path


def test_the_guard_catches_the_orderings_that_were_shipped():
    """A guard that cannot fail protects nothing: the three shapes the backend carried."""
    plain = "SELECT l.id FROM lead_interactions i JOIN leads l ON l.id = i.lead_id\n" \
            "ORDER BY l.icp_score DESC, l.rowid, i.id\n"
    assert _ranked_by_score(plain), "the engagers route's ordering is not caught"
    aliased = "SELECT l.icp_score as sort_score, l.rowid as lead_row FROM leads l\n" \
              "ORDER BY sort_score DESC, interacted_at DESC, lead_row\n"
    assert _ranked_by_score(aliased), "an alias of the score column is not caught"
    renamed = "SELECT l.icp_score AS priority FROM leads l\nORDER BY priority DESC\n"
    assert _ranked_by_score(renamed), "an alias that does not say score is not caught"
    in_python = "people.sort(key=lambda p: p['icp_score'], reverse=True)\n"
    assert _ranked_by_score(in_python), "a Python sort by the score is not caught"
    facts = "SELECT l.id FROM leads l ORDER BY i.interacted_at DESC, l.rowid, i.id\n"
    assert not _ranked_by_score(facts), "an ordering by facts is flagged"
    templates = "SELECT * FROM viral_templates ORDER BY velocity_score DESC\n"
    assert not _ranked_by_score(templates), "a ranking of hook templates is not a ranking of people"


def test_no_backend_query_orders_people_by_their_score():
    offenders = []
    for relative, path in _python_files():
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        for number, line in _ranked_by_score(source):
            offenders.append(f"{relative}:{number}: {line}")
    assert not offenders, "people are ordered by a score, which is a guess about a job title:\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# The two routes, on a history built so that the facts order and the score
# order disagree: the highest scored person engaged first, the lowest last.
# ---------------------------------------------------------------------------

URN = "urn:li:activity:7380000000000000001"
# Headlines carry the score, because a score written into the column by hand
# is recomputed from the headline, the company and the engagements whenever
# any of them changes (crm.catch_up_scores). Earliest engagement first.
PEOPLE = [
    ("lead-founder", "Fatima Founder", "Founder at Northwind Cloud", "2026-10-01T09:00:00+00:00"),
    ("lead-manager", "Morgan Manager", "Engineering Manager at Northwind Cloud", "2026-10-02T09:00:00+00:00"),
    ("lead-intern", "Ira Intern", "Intern", "2026-10-03T09:00:00+00:00"),
]


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_no_rank_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status, activity_urn) VALUES ('post-1', 'A post.', 'published', ?)",
                     (URN,))
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, reactions, first_seen_at, last_seen_at) "
                     "VALUES (?, 'A post.', '2026-09-20T09:00:00+00:00', 12, '2026-10-01', '2026-10-01')", (URN,))
        for lead_id, name, headline, when in PEOPLE:
            conn.execute("INSERT INTO leads (id, name, full_name, headline, company) VALUES (?, ?, ?, ?, ?)",
                         (lead_id, name, name, headline, "Northwind Cloud" if "at " in headline else None))
            conn.execute("INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text, interacted_at) "
                         "VALUES (?, ?, 'COMMENT', 'A real question?', ?)", (lead_id, URN, when))
    conn.close()
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _scores(conn):
    import crm
    crm.scores_current(conn)
    return {row["id"]: row["icp_score"] for row in conn.execute("SELECT id, icp_score FROM leads")}


def test_a_posts_engagers_come_out_newest_first_whatever_their_scores(home):
    from database import get_db
    from routers import posts as posts_router
    conn = get_db()
    try:
        scores = _scores(conn)
    finally:
        conn.close()
    assert len(set(scores.values())) == 3, f"the three headlines did not score apart: {scores}"
    answer = posts_router.get_post_engagers("post-1")
    ids = [person["id"] for person in answer["engagers"]]
    assert ids == ["lead-intern", "lead-manager", "lead-founder"], ids
    by_score = sorted(ids, key=lambda lead: -scores[lead])
    assert ids != by_score, "the facts order and the score order coincide, so this proves nothing"


def test_a_posts_attribution_lists_people_newest_first_whatever_their_scores(home):
    import crm
    from database import get_db
    conn = get_db()
    try:
        scores = _scores(conn)
    finally:
        conn.close()
    answer = crm.reverse_crm.get_post_attribution("post-1")
    ids = [person["lead_id"] for person in answer["leads"]]
    assert ids == ["lead-intern", "lead-manager", "lead-founder"], ids
    assert ids != sorted(ids, key=lambda lead: -scores[lead])
