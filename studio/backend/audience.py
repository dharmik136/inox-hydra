"""
Audience: among the people the bridge has seen, who keeps coming back, who has
gone quiet, and who is already a connection?
=============================================================================

Leads is a stream and a dossier: one person and the next step. This is the
set. Every list here is ordered by facts, how many of the creator's posts a
person engaged with and how recently the studio first saw them do it, and
never by the ICP score, which is a keyword guess about a job title (today.py
states the rule; nothing in this module reads the score).

The figures are partial by construction, and say so. The bridge reads who
engaged with a post only when the creator opens that post, so "engaged with
three of your posts" means three of the posts whose engagers were read, and
the repeat list carries how many posts that is. A week in which the bridge
read nothing is not a week in which nobody new arrived.

Gone quiet is relative to what was read: a person who engaged with two or
more of your posts and has not been seen engaging since the last
QUIET_RECENT_POSTS posts whose engagers were read began. Until that many posts
have been read the list abstains, because "not seen" would only mean "not
looked". The silent-lead review in Storage and privacy is a different
question (who can be removed after 24 months untouched) and keeps its own
rule in retention.py.

Connections come from LinkedIn's archive, as of the day it was imported. They
are joined to leads by profile, and the two sides do not store the same
string: the extension writes https://www.linkedin.com/in/<percent-encoded>/
with a trailing slash for a comment and the page's own link for a reaction,
which is often a member id (/in/ACoAA...), while the archive writes
https://www.linkedin.com/in/<vanity> with none. Both are read through
onboarding.normalise_vanity, the one canonical spelling, and a person known
only by a member id is counted as unmatched rather than guessed.

The funnel is crm.get_crm_telemetry's, read as it is (one definition), and
only its counts are shown: none of its score tiers.

Strict Invariants:
- Zero em-dashes.
- No ordering of people by score.
- No network request.
"""

import heapq
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from . import onboarding, paths
    from .crm import reverse_crm
    from .database import get_db
    from .leads import LEAD_STATUS_TO_PIPELINE
    from .text_cut import clip
except ImportError:
    import onboarding
    import paths
    from crm import reverse_crm
    from database import get_db
    from leads import LEAD_STATUS_TO_PIPELINE
    from text_cut import clip

# A repeat engager engaged with at least this many of the creator's posts.
REPEAT_MIN_POSTS = 2
# People listed in each of the first view's lists; the count beside each is the whole set.
PEOPLE_SHOWN = 25
# Gone quiet: not seen since this many of the most recent posts whose engagers were read began.
QUIET_RECENT_POSTS = 5
# New people, by week, for this many weeks ending with this one.
WEEKS_SHOWN = 12
COMPANIES_SHOWN = 15
CONNECTIONS_PAGE = 50
CONNECTIONS_MAX = 200

# A LinkedIn link that names a member id rather than a public name. The
# reactions list links people this way, and such a link cannot be matched to
# the archive's connections, which name people by their public name.
MEMBER_ID_PREFIX = "acoaa"

# The pipeline stages by the names Leads shows, from the one mapping leads.py
# keeps; the two the screen never sets are named here.
FUNNEL_LABELS = {pipeline: label for label, pipeline in LEAD_STATUS_TO_PIPELINE.items()}
FUNNEL_LABELS.setdefault("DM_DRAFTED", "Message drafted")
FUNNEL_LABELS.setdefault("ARCHIVED", "Archived")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _post_moment(post_id: str) -> Optional[datetime]:
    """When a post was made, from its id: LinkedIn's ids carry the millisecond in their high bits."""
    try:
        return datetime.fromtimestamp((int(post_id) >> 22) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def vanity_of(url: Optional[str]) -> str:
    """The one canonical spelling of a profile link, or "". See the module notes."""
    return onboarding.normalise_vanity(url or "")


def is_member_id(vanity: str) -> bool:
    return vanity.startswith(MEMBER_ID_PREFIX)


# Normalising every profile link is the expensive part of the join (about
# fifty thousand on a three year install), and the links change only when a
# person is added, removed or given a link. So each side's map is kept until
# the table it came from changes, per database, because a profile switch
# changes which database is open.
_cache: Dict[str, Tuple[Tuple, Any]] = {}
_cache_lock = threading.Lock()


def _cached(name: str, key: Tuple, compute: Callable[[], Any]) -> Any:
    full_key = (paths.get_db_path(),) + key
    with _cache_lock:
        held = _cache.get(name)
        if held and held[0] == full_key:
            return held[1]
    value = compute()
    with _cache_lock:
        _cache[name] = (full_key, value)
    return value


def _lead_vanities(conn) -> Dict[str, str]:
    """Each lead's canonical profile spelling, by lead id."""
    key = tuple(conn.execute(
        "SELECT COUNT(*), MAX(rowid), TOTAL(LENGTH(COALESCE(profile_url, ''))), "
        "TOTAL(LENGTH(COALESCE(linkedin_urn, ''))) FROM leads").fetchone())

    def compute() -> Dict[str, str]:
        found = {}
        for row in conn.execute("SELECT id, profile_url, linkedin_urn FROM leads"):
            vanity = vanity_of(row["profile_url"]) or vanity_of(row["linkedin_urn"])
            if vanity:
                found[str(row["id"])] = vanity
        return found
    return _cached("leads", key, compute)


def _connection_vanities(conn) -> Dict[str, Dict[str, Any]]:
    """Each connection by its canonical profile spelling."""
    key = tuple(conn.execute("SELECT COUNT(*), MAX(imported_at), TOTAL(LENGTH(profile_url)) FROM connections").fetchone())

    def compute() -> Dict[str, Dict[str, Any]]:
        found = {}
        for row in conn.execute("SELECT profile_url, connected_on, imported_at FROM connections"):
            vanity = vanity_of(row["profile_url"])
            if vanity and vanity not in found:
                found[vanity] = {"connected_on": row["connected_on"], "as_of": row["imported_at"]}
        return found
    return _cached("connections", key, compute)


# ---------------------------------------------------------------------------
# Who engaged with which of the creator's posts
# ---------------------------------------------------------------------------

def _canonical(stamp: Optional[str]) -> Optional[str]:
    """A stored time as "YYYY-MM-DD HH:MM:SS" (UTC), so times written either way compare as times."""
    return stamp.replace("T", " ")[:19] if stamp else None


def _week_of(stamp: str) -> Optional[str]:
    try:
        return _monday(date.fromisoformat(stamp[:10])).isoformat()
    except ValueError:
        return None


class _Engagement:
    """
    Per person, over the creator's own posts: which posts, and when the studio
    first saw them engage at all and most recently. "When" is the first
    sighting of each engagement, so reopening a post moves nothing.

    Kept between requests and brought current from the rows added since,
    because summing half a million interactions on every visit cost about
    700 ms on a three year install against a 100 ms bar. It is rebuilt from
    nothing whenever what it summarises could have changed in a way that
    adding rows does not cover: a row removed (a forgotten person, the
    reaction fold), the creator's posts changing (a post read or bound,
    which can make earlier engagements count), or another profile's
    database. A post that becomes the creator's is adopted without a
    rebuild, because a post is read most days and the engagements on it may
    have been captured first. Rows are otherwise only ever added: the
    capture's conflict path updates when a row was last seen and how often,
    neither of which is read here. tests/test_qc4_t4_audience.py holds the
    kept answer to the answer a rebuild gives.
    """

    def __init__(self) -> None:
        self.key: Optional[Tuple] = None
        self.count = 0
        self.high_water = 0
        self.own_ids: Any = set()
        self.own_urns: Dict[str, Optional[str]] = {}
        # lead id -> [set of own post ids, first sighting, latest sighting]
        self.people: Dict[str, List[Any]] = {}
        self.posts_read: set = set()
        # Mondays of the weeks in which the bridge read any engagement at all.
        self.weeks_read: set = set()
        self.week_floor = ""
        self.rebuilds = 0

    def _post(self, urn: Optional[str]) -> Optional[str]:
        if not urn:
            return None
        if urn not in self.own_urns:
            post_id = onboarding._activity_id(urn)
            self.own_urns[urn] = post_id if post_id and post_id in self.own_ids else None
        return self.own_urns[urn]

    def _engaged(self, lead_id: str, post_id: str, seen: Optional[str]) -> None:
        self.posts_read.add(post_id)
        person = self.people.get(lead_id)
        if person is None:
            self.people[lead_id] = [{post_id}, seen, seen]
            return
        person[0].add(post_id)
        if seen and (person[1] is None or seen < person[1]):
            person[1] = seen
        if seen and (person[2] is None or seen > person[2]):
            person[2] = seen

    def add(self, rows: Any) -> None:
        for row_id, lead_id, urn, seen in rows:
            self.count += 1
            if row_id > self.high_water:
                self.high_water = row_id
            seen = _canonical(seen)
            if seen and seen >= self.week_floor:
                week = _week_of(seen)
                if week:
                    self.weeks_read.add(week)
            post_id = self._post(urn)
            if post_id is not None:
                self._engaged(lead_id, post_id, seen)

    def adopt(self, conn, own_ids: Any) -> bool:
        """
        The creator's posts changed. Engagements on a post that has just
        become theirs (read after its engagers were) are added; a post that
        stopped being theirs needs a rebuild, which this answers False for.
        """
        gained = []
        for urn, post_id in self.own_urns.items():
            now_id = onboarding._activity_id(urn)
            now_id = now_id if now_id and now_id in own_ids else None
            if post_id is not None and now_id is None:
                return False
            if post_id is None and now_id is not None:
                gained.append((urn, now_id))
        self.own_ids = own_ids
        for urn, post_id in gained:
            self.own_urns[urn] = post_id
            for _row_id, lead_id, _urn, seen in conn.execute(
                    _ROWS + " WHERE post_urn = ? AND id <= ?", (urn, self.high_water)):
                self._engaged(lead_id, post_id, _canonical(seen))
        return True

    def rebuild(self, conn, key: Tuple) -> None:
        rebuilds = self.rebuilds
        self.__init__()
        self.rebuilds = rebuilds + 1
        self.key = key
        self.own_ids = onboarding._own_activity_ids(conn)
        floor = _monday(datetime.now(timezone.utc).date()) - timedelta(weeks=WEEKS_SHOWN + 1)
        self.week_floor = floor.isoformat()
        self.add(conn.execute(_ROWS))


_ROWS = ("SELECT id, CAST(lead_id AS TEXT), post_urn, COALESCE(first_seen_at, interacted_at) "
         "FROM lead_interactions")

_engagement = _Engagement()
_engagement_lock = threading.Lock()


def _own_posts_key(conn) -> Tuple:
    """Changes whenever the set of the creator's posts, or a post's identity, changes."""
    return (tuple(conn.execute("SELECT COUNT(*), MAX(rowid), TOTAL(LENGTH(activity_urn)) FROM own_posts").fetchone())
            + tuple(conn.execute("SELECT COUNT(activity_urn), TOTAL(LENGTH(activity_urn)) FROM posts").fetchone()))


def _engagement_view(conn) -> Dict[str, Any]:
    """
    The kept engagement brought current, and what the first view needs from
    it: the repeat engagers and the people gone quiet (the first
    PEOPLE_SHOWN of each, and how many there are), new people by week, and
    the posts read. Computed under the lock, so a capture landing meanwhile
    cannot change it half way, and the reads are one transaction, so the
    count and the rows added are of the same moment.

    Times are compared as "YYYY-MM-DD HH:MM:SS" strings, not parsed: on a
    three year install nearly everyone engaged with two posts or more, and
    parsing each of their times cost 100 ms on its own.
    """
    this_week = _monday(datetime.now(timezone.utc).date())
    first_week = (this_week - timedelta(weeks=WEEKS_SHOWN - 1)).isoformat()
    conn.execute("BEGIN")
    try:
        key = (paths.get_db_path(),) + _own_posts_key(conn)
        count, high = conn.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM lead_interactions").fetchone()
        with _engagement_lock:
            state = _engagement
            if state.key is None or state.key[0] != key[0] or high < state.high_water:
                state.rebuild(conn, key)
            else:
                if high > state.high_water:
                    state.add(conn.execute(_ROWS + " WHERE id > ? AND id <= ? ORDER BY id", (state.high_water, high)))
                if state.key != key:
                    if state.adopt(conn, onboarding._own_activity_ids(conn)):
                        state.key = key
                    else:
                        state.rebuild(conn, key)
            if state.count != count:
                state.rebuild(conn, key)

            posts_read = sorted(state.posts_read, key=lambda p: int(p), reverse=True)
            judged = len(posts_read) >= QUIET_RECENT_POSTS
            since = _post_moment(posts_read[QUIET_RECENT_POSTS - 1]) if judged else None
            since_at = _canonical(since.isoformat()) if since else None

            repeat: List[Tuple[int, str, str, Optional[str]]] = []
            quiet: List[Tuple[int, str, str, Optional[str]]] = []
            new: Dict[str, int] = {}
            for lead, (posts, first, latest) in state.people.items():
                if first and first >= first_week:
                    week = _week_of(first)
                    if week:
                        new[week] = new.get(week, 0) + 1
                engaged = len(posts)
                if engaged < REPEAT_MIN_POSTS:
                    continue
                entry = (engaged, latest or "", lead, first)
                repeat.append(entry)
                if since_at and latest and latest < since_at:
                    quiet.append(entry)
            # By posts engaged, then the most recent engagement, then the lead
            # id, so ties come out the same every time. Never by score.
            def by_facts(entry: Tuple[int, str, str, Optional[str]]) -> Tuple[int, str, str]:
                return entry[0], entry[1], entry[2]
            weeks_read = set(state.weeks_read)
    finally:
        conn.commit()
    return {
        "posts_read": len(posts_read),
        "judged": judged,
        "since": since.isoformat() if since else None,
        "repeat_count": len(repeat),
        "repeat": heapq.nlargest(PEOPLE_SHOWN, repeat, key=by_facts),
        "quiet_count": len(quiet),
        "quiet": heapq.nlargest(PEOPLE_SHOWN, quiet, key=by_facts),
        "new_by_week": new,
        "weeks_read": weeks_read,
        "first_week": first_week,
    }


def _named(conn, lead_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    named: Dict[str, Dict[str, Any]] = {}
    for start in range(0, len(lead_ids), 500):
        chunk = lead_ids[start:start + 500]
        marks = ",".join("?" for _ in chunk)
        for row in conn.execute(
                f"SELECT id, COALESCE(full_name, name) AS name, headline FROM leads WHERE id IN ({marks})", chunk):
            named[str(row["id"])] = {"name": row["name"], "headline": clip(row["headline"], 160) if row["headline"] else None}
    return named


def _person(entry: Tuple[int, str, str, Optional[str]], named: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    engaged, latest, lead_id, first = entry
    who = named.get(lead_id, {})
    return {"lead_id": lead_id, "name": who.get("name"), "headline": who.get("headline"),
            "posts_engaged": engaged, "first_seen_at": first, "latest_at": latest or None}


def _weeks(view: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    New people by the week the studio first saw them engage with one of your
    posts, Monday to Sunday in UTC. A week in which the bridge read no
    engagement at all, on any post, says so instead of counting nobody.
    """
    first_week = date.fromisoformat(view["first_week"])
    weeks = []
    for n in range(WEEKS_SHOWN):
        week = (first_week + timedelta(weeks=n)).isoformat()
        was_read = week in view["weeks_read"]
        weeks.append({"week": week, "read": was_read, "new": view["new_by_week"].get(week, 0) if was_read else None})
    return weeks


# ---------------------------------------------------------------------------
# The first view
# ---------------------------------------------------------------------------

def _connections_summary(conn) -> Dict[str, Any]:
    """How many connections, as of when, and how many leads they match or cannot."""
    count, as_of = conn.execute("SELECT COUNT(*), MAX(imported_at) FROM connections").fetchone()
    lead_vanities = _lead_vanities(conn)
    connected = _connection_vanities(conn) if count else {}
    key = (id(lead_vanities), id(connected), count, as_of)

    def compute() -> Dict[str, Any]:
        return {
            "count": count,
            "as_of": as_of,
            "leads_matched": sum(1 for vanity in lead_vanities.values() if vanity in connected),
            "leads_by_member_id": sum(1 for vanity in lead_vanities.values() if is_member_id(vanity)),
        }
    return _cached("connections_summary", key, compute)


def overview() -> Dict[str, Any]:
    conn = get_db()
    try:
        view = _engagement_view(conn)
        shown = [entry[2] for entry in view["repeat"]] + [entry[2] for entry in view["quiet"]]
        named = _named(conn, list(dict.fromkeys(shown)))
        own_posts = conn.execute("SELECT COUNT(*) FROM own_posts").fetchone()[0]
        connected = _connections_summary(conn)
    finally:
        conn.close()

    n_read = view["posts_read"]
    return {
        "status": "success",
        "own_posts": own_posts,
        "repeat": {
            "posts_read": n_read,
            "label": f"among the {n_read} posts whose engagers were read",
            "min_posts": REPEAT_MIN_POSTS,
            "count": view["repeat_count"],
            "people": [_person(entry, named) for entry in view["repeat"]],
        },
        "quiet": {
            "judged": view["judged"],
            "recent_posts": QUIET_RECENT_POSTS,
            "posts_read": n_read,
            "since": view["since"],
            "count": view["quiet_count"],
            "people": [_person(entry, named) for entry in view["quiet"]],
        },
        "new_people": {
            "partial": True,
            "label": "first seen by the studio engaging with one of your posts, in the weeks the bridge read engagers",
            "weeks": _weeks(view),
        },
        "connections": connected,
    }


# ---------------------------------------------------------------------------
# The searchable connections list
# ---------------------------------------------------------------------------

def connections(q: Optional[str] = None, offset: int = 0, limit: int = CONNECTIONS_PAGE) -> Dict[str, Any]:
    """The archive's connections, by name, as of the import, each marked when they are also a lead."""
    limit = max(1, min(int(limit), CONNECTIONS_MAX))
    offset = max(0, int(offset))
    where, params = "", []
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        where = ("WHERE first_name LIKE ? OR last_name LIKE ? OR (COALESCE(first_name, '') || ' ' || "
                 "COALESCE(last_name, '')) LIKE ? OR company LIKE ? OR position LIKE ?")
        params = [like] * 5
    conn = get_db()
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM connections {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT profile_url, first_name, last_name, company, position, connected_on, imported_at "
            f"FROM connections {where} ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE, profile_url "
            f"LIMIT ? OFFSET ?", params + [limit, offset]).fetchall()
        as_of = conn.execute("SELECT MAX(imported_at) FROM connections").fetchone()[0]
        by_vanity: Dict[str, str] = {}
        for lead_id, vanity in sorted(_lead_vanities(conn).items()):
            by_vanity.setdefault(vanity, lead_id)
    finally:
        conn.close()
    listed = []
    for row in rows:
        name = " ".join(part for part in (row["first_name"], row["last_name"]) if part) or None
        listed.append({
            "name": name,
            "company": row["company"],
            "position": row["position"],
            "connected_on": row["connected_on"],
            "as_of": row["imported_at"],
            "profile_url": row["profile_url"],
            "lead_id": by_vanity.get(vanity_of(row["profile_url"])),
        })
    following = offset + len(listed)
    return {"status": "success", "q": term, "total": total, "as_of": as_of, "offset": offset, "limit": limit,
            "next_offset": following if following < total else None, "connections": listed}


# ---------------------------------------------------------------------------
# The second level: the funnel and companies, as counts
# ---------------------------------------------------------------------------

def counts() -> Dict[str, Any]:
    """
    How many people are at each stage the creator set in Leads, from
    crm.get_crm_telemetry's funnel as it is, and how many name each company
    in their headline. None of the telemetry's score tiers is passed on.
    """
    funnel = reverse_crm.get_crm_telemetry()["funnel"]
    conn = get_db()
    try:
        companies = [{"company": row["company"], "people": row["people"]} for row in conn.execute(
            "SELECT TRIM(company) AS company, COUNT(*) AS people FROM leads WHERE TRIM(COALESCE(company, '')) != '' "
            "GROUP BY TRIM(company) ORDER BY people DESC, company COLLATE NOCASE LIMIT ?", (COMPANIES_SHOWN,))]
        distinct, no_company, total = conn.execute(
            "SELECT COUNT(DISTINCT CASE WHEN TRIM(COALESCE(company, '')) != '' THEN TRIM(company) END), "
            "SUM(CASE WHEN TRIM(COALESCE(company, '')) = '' THEN 1 ELSE 0 END), COUNT(*) FROM leads").fetchone()
    finally:
        conn.close()
    return {
        "status": "success",
        "people": total,
        "funnel": [{"status": key, "label": FUNNEL_LABELS.get(key, key.replace("_", " ").title()), "people": value}
                   for key, value in funnel.items()],
        "companies": companies,
        "companies_named": distinct or 0,
        "no_company": no_company or 0,
    }


# ---------------------------------------------------------------------------
# One person, for the Leads dossier
# ---------------------------------------------------------------------------

def person(lead_id: str) -> Optional[Dict[str, Any]]:
    """
    When the studio first and last saw this person, how many times it read an
    engagement of theirs, and whether they are a connection in the archive.
    None for a lead the studio does not hold.
    """
    conn = get_db()
    try:
        lead = conn.execute("SELECT id, profile_url, linkedin_urn FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if lead is None:
            return None
        first, last, times, engagements = conn.execute(
            "SELECT MIN(COALESCE(first_seen_at, interacted_at)), "
            "MAX(COALESCE(last_seen_at, first_seen_at, interacted_at)), SUM(seen_count), COUNT(*) "
            "FROM lead_interactions WHERE lead_id = ?", (lead_id,)).fetchone()
        held, as_of = conn.execute("SELECT COUNT(*), MAX(imported_at) FROM connections").fetchone()
        connected = _connection_vanities(conn) if held else {}
    finally:
        conn.close()
    vanity = vanity_of(lead["profile_url"]) or vanity_of(lead["linkedin_urn"])
    return {
        "status": "success",
        "lead_id": lead_id,
        "first_seen_at": first,
        "last_seen_at": last,
        "times_seen": times if engagements else None,
        "engagements": engagements,
        "connection": connected.get(vanity) if vanity else None,
        # Whether "not a connection" can be said at all: only once an archive
        # with connections was imported, and as of that import.
        "connections_held": held,
        "connections_as_of": as_of,
        "member_id_only": bool(vanity) and is_member_id(vanity),
    }
