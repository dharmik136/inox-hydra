"""
Obsidian Vault Export: The Creator's LinkedIn Record as Linked Notes.
=====================================================================
Writes what the studio knows about the creator's own LinkedIn as a folder of
markdown notes that Obsidian opens as a vault. Posts are hubs, the people who
engaged sit around them, and the people who turn up on several posts sit
between them, so the graph view is the creator's audience drawn to scale.

    Me.md          who the creator is: headline, about, roles, skills
    Home.md        the map, with counts
    Posts/         one note per own post: text, readings over time, who engaged
    People/        one note per lead: every post they engaged with, comments, stage history
    Topics/        one note per topic, linking its posts
    Outbound/      one note per author whose posts the creator engages with
    Drafts/        the studio's drafts

A vault is a place people think in, so an export must be safe to repeat into
the same folder. Three rules make it so:

  - It refuses a folder that has files in it and is not a previous export.
  - It rewrites only the notes it wrote last time, listed in a manifest, and
    removes those it no longer writes. Notes the creator added are untouched.
  - Anything written under a "## Your notes" heading inside a generated note
    survives the next export.

Nothing invented: a figure nobody read says "not measured", never 0, and
seeded demo analytics are not exported as measurements.

Captured text (posts, comments, notes) is exported exactly as written. It is
the creator's record, and an archive that edits it is not one.

Strict Invariants:
- Zero em-dashes in any code, docstring or comment.
- Zero network: this module reads the local database and writes local files.
- Credentials are never read. `settings` is not queried.
"""

import json
import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from . import paths
    from .evidence_briefing import classify_post_topic
except ImportError:
    import paths
    from evidence_briefing import classify_post_topic

MANIFEST = ".inox-hydra-export.json"
YOUR_NOTES = "## Your notes"
FOLDERS = ("Posts", "People", "Topics", "Outbound", "Drafts")

# Graph colours per folder, written only into a vault that has no Obsidian
# settings of its own yet. Values are Obsidian's packed RGB integers.
GRAPH_COLOURS = {
    "Posts": 0xE9552C,
    "People": 0x2867C7,
    "Topics": 0xD4A017,
    "Outbound": 0x168A61,
    "Drafts": 0x7F8C8D,
}

# Characters Obsidian or a filesystem refuses in a note name, plus the ones
# that change what a wiki link means.
_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f]')
_ACTIVITY_ID = re.compile(r"urn:li:(?:activity|share|ugcPost):(\d+)")

NOT_MEASURED = "not measured"
NO_POSTS = "No posts imported yet. Import your history in Setup, then export again."


class ExportRefused(ValueError):
    """The destination is not somewhere this export may write."""


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(paths.get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _tables(conn: sqlite3.Connection) -> set:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _rows(conn: sqlite3.Connection, available: set, table: str, sql: str, args: Tuple = ()) -> List[Dict[str, Any]]:
    """Rows as dicts, or nothing when an older database does not have the table yet."""
    if table not in available:
        return []
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def _activity_id(urn: Any) -> str:
    match = _ACTIVITY_ID.search(urn or "")
    return match.group(1) if match else ""


def read_record() -> Dict[str, Any]:
    """Everything the export draws on, read in one connection."""
    conn = _connect()
    try:
        have = _tables(conn)
        identity = _rows(conn, have, "creator_identity", "SELECT * FROM creator_identity WHERE id = 1")
        return {
            "identity": identity[0] if identity else None,
            "positions": _rows(conn, have, "creator_positions", "SELECT * FROM creator_positions ORDER BY ordinal"),
            "education": _rows(conn, have, "creator_education", "SELECT * FROM creator_education ORDER BY ordinal"),
            "skills": [
                r["skill"] for r in _rows(conn, have, "creator_skills", "SELECT skill FROM creator_skills ORDER BY skill")
            ],
            "posts": _rows(conn, have, "own_posts", "SELECT * FROM own_posts ORDER BY published_at, activity_urn"),
            "observations": _rows(
                conn, have, "post_metric_observations",
                "SELECT * FROM post_metric_observations ORDER BY activity_urn, observed_at",
            ),
            "leads": _rows(conn, have, "leads", "SELECT * FROM leads ORDER BY COALESCE(full_name, name)"),
            "interactions": _rows(
                conn, have, "lead_interactions", "SELECT * FROM lead_interactions ORDER BY lead_id, id"
            ),
            "stages": _rows(conn, have, "lead_stage_events", "SELECT * FROM lead_stage_events ORDER BY lead_id, changed_at"),
            "outbound": _rows(
                conn, have, "outbound_engagements", "SELECT * FROM outbound_engagements ORDER BY target_author, id"
            ),
            "drafts": _rows(conn, have, "drafts", "SELECT * FROM drafts ORDER BY id"),
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Naming and formatting
# ---------------------------------------------------------------------------

def safe_name(text: Any, limit: int = 80) -> str:
    """
    A note name Obsidian and every filesystem accept, from arbitrary text.

    LinkedIn posts are often set in mathematical bold, which is a different
    alphabet as far as a file name or a search is concerned: a note called
    "\U0001d5e6\U0001d601\U0001d5f2\U0001d5fd" is not found by typing "Step". NFKC folds those
    letters back to plain ones, and symbols (emoji among them) are dropped from
    the name. The note's text keeps everything exactly as written.
    """
    folded = unicodedata.normalize("NFKC", str(text or ""))
    folded = "".join(ch for ch in folded if unicodedata.category(ch) not in ("So", "Cs", "Co", "Cn"))
    name = _UNSAFE_NAME.sub(" ", folded)
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    if len(name) > limit:
        name = name[:limit].rsplit(" ", 1)[0].rstrip(" ,;-") or name[:limit]
    return name


class _Names:
    """Hands out unique note names inside one folder, case-insensitively."""

    def __init__(self) -> None:
        self.taken: set = set()

    def claim(self, wanted: str, fallback: str) -> str:
        base = safe_name(wanted) or safe_name(fallback) or "Untitled"
        name, n = base, 2
        while name.lower() in self.taken:
            name = f"{base} ({n})"
            n += 1
        self.taken.add(name.lower())
        return name


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _figure(value: Any) -> str:
    if value is None or value == "":
        return NOT_MEASURED
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _yaml_value(value: Any) -> str:
    # JSON strings are valid YAML scalars, and json.dumps escapes everything a
    # post or a name can contain, including quotes, colons and newlines.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _frontmatter(fields: Dict[str, Any], tags: Iterable[str]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if value is None or value == "":
            continue  # absent rather than a fabricated zero or empty string
        lines.append(f"{key}: {_yaml_value(value)}")
    tag_list = [t for t in tags if t]
    if tag_list:
        lines.append("tags:")
        lines += [f"  - {t}" for t in tag_list]
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _tag(text: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return slug or "unknown"


def _link(folder: str, name: str, label: Optional[str] = None) -> str:
    target = f"{folder}/{name}"
    return f"[[{target}|{label or name}]]"


def _quote(text: Any, limit: int = 400) -> str:
    body = str(text or "").strip()
    if len(body) > limit:
        body = body[:limit].rsplit(" ", 1)[0] + "..."
    return "\n".join("> " + line if line else ">" for line in body.splitlines())


def _indented(text: str) -> str:
    """Indents a block so it sits under the list item above it."""
    return "\n".join("  " + line for line in text.splitlines())


def _date(value: Any) -> str:
    return str(value or "")[:10]


# ---------------------------------------------------------------------------
# Building notes
# ---------------------------------------------------------------------------

def build_notes(record: Dict[str, Any]) -> Dict[str, str]:
    """Maps a vault-relative path to note text. Pure, so it can be tested without a disk."""
    notes: Dict[str, str] = {}

    posts = record["posts"]
    leads = {lead["id"]: lead for lead in record["leads"]}
    post_by_id = {_activity_id(p["activity_urn"]): p for p in posts if _activity_id(p["activity_urn"])}

    # Names first, so every note can link to every other one.
    post_names, people_names, topic_names, outbound_names, draft_names = _Names(), _Names(), _Names(), _Names(), _Names()
    post_note: Dict[str, str] = {}
    for post in posts:
        first_line = next((ln for ln in (post.get("text") or "").splitlines() if ln.strip()), "")
        day = _date(post.get("published_at"))
        wanted = f"{day} {first_line}" if day else first_line
        post_note[post["activity_urn"]] = post_names.claim(
            safe_name(wanted, 70), f"Post {_activity_id(post['activity_urn']) or len(post_note) + 1}"
        )

    person_note: Dict[str, str] = {}
    for lead in record["leads"]:
        name = lead.get("full_name") or lead.get("name") or ""
        person_note[lead["id"]] = people_names.claim(name, f"Person {lead['id']}")

    topic_of = {p["activity_urn"]: classify_post_topic(p.get("text")) for p in posts}
    topic_note = {t: topic_names.claim(t, "General") for t in sorted(set(topic_of.values()))}

    # Interactions joined to posts by the numeric activity id, which is how the
    # rest of the studio joins them: a lead's row may carry a share or ugcPost
    # URN for the same post.
    by_post: Dict[str, List[Dict[str, Any]]] = {}
    by_lead: Dict[str, List[Dict[str, Any]]] = {}
    for item in record["interactions"]:
        if item.get("lead_id") not in leads:
            continue
        by_lead.setdefault(item["lead_id"], []).append(item)
        post = post_by_id.get(_activity_id(item.get("post_urn")))
        if post:
            by_post.setdefault(post["activity_urn"], []).append(item)

    observations: Dict[str, List[Dict[str, Any]]] = {}
    for obs in record["observations"]:
        observations.setdefault(obs["activity_urn"], []).append(obs)

    stages: Dict[str, List[Dict[str, Any]]] = {}
    for event in record["stages"]:
        stages.setdefault(event["lead_id"], []).append(event)

    # Outbound authors are a display name only (see the planning vault's gap
    # note). A People note is linked when exactly one lead has that name.
    lead_by_name: Dict[str, List[str]] = {}
    for lead_id, lead in leads.items():
        key = (lead.get("full_name") or lead.get("name") or "").strip().lower()
        if key:
            lead_by_name.setdefault(key, []).append(lead_id)
    outbound: Dict[str, List[Dict[str, Any]]] = {}
    for item in record["outbound"]:
        author = (item.get("target_author") or "").strip()
        if author:
            outbound.setdefault(author, []).append(item)
    outbound_note = {a: outbound_names.claim(a, "Someone") for a in sorted(outbound)}

    # ---- Posts
    for post in posts:
        urn = post["activity_urn"]
        name = post_note[urn]
        topic = topic_of[urn]
        engaged = by_post.get(urn, [])
        fm = _frontmatter({
            "activity_urn": urn,
            "published": _date(post.get("published_at")),
            "topic": topic,
            "impressions": post.get("impressions"),
            "reactions": post.get("reactions"),
            "comments": post.get("comments"),
            "reposts": post.get("reposts"),
            "engagers": len({i["lead_id"] for i in engaged}),
            "url": f"https://www.linkedin.com/feed/update/{urn}/" if urn.startswith("urn:li:activity:") else None,
        }, ["linkedin/post", f"topic/{_tag(topic)}"])
        lines = [f"# {name}", "", f"Topic: {_link('Topics', topic_note[topic], topic)}", "", "## Post", "",
                 _quote(post.get("text"), 3000) or "> (no text captured)", "", "## Figures", "",
                 "| Impressions | Reactions | Comments | Reposts |", "|---|---|---|---|",
                 f"| {_figure(post.get('impressions'))} | {_figure(post.get('reactions'))} "
                 f"| {_figure(post.get('comments'))} | {_figure(post.get('reposts'))} |", ""]
        readings = observations.get(urn, [])
        if readings:
            lines += ["## Readings over time", "", "| Observed | Age (h) | Source | Impressions | Reactions | Comments |",
                      "|---|---|---|---|---|---|"]
            for r in readings:
                age = r.get("age_hours")
                lines.append(
                    f"| {str(r.get('observed_at') or '')[:16]} | {_figure(round(age) if isinstance(age, (int, float)) else None)}"
                    f" | {r.get('source') or ''} | {_figure(r.get('impressions'))} | {_figure(r.get('reactions'))}"
                    f" | {_figure(r.get('comments'))} |"
                )
            lines.append("")
        lines += ["## Who engaged", ""]
        if engaged:
            for item in engaged:
                person = _link("People", person_note[item["lead_id"]])
                kind = (item.get("interaction_type") or "engaged").lower()
                said = f": \"{str(item['comment_text']).strip()[:200]}\"" if item.get("comment_text") else ""
                lines.append(f"- {person} {kind}{said}")
        else:
            lines.append("Nobody the studio has seen yet.")
        notes[f"Posts/{name}.md"] = fm + "\n".join(lines) + "\n"

    # ---- People
    for lead_id, lead in leads.items():
        name = person_note[lead_id]
        own = by_lead.get(lead_id, [])
        status = lead.get("status") or lead.get("lead_status")
        urn_field = str(lead.get("linkedin_urn") or "")
        fm = _frontmatter({
            "headline": lead.get("headline"),
            "company": lead.get("company"),
            "status": status,
            "seniority": lead.get("seniority_level"),
            "icp_score": lead.get("icp_score"),
            "first_seen": _date(lead.get("created_at")),
            # The CRM capture path stores the profile URL in linkedin_urn.
            "profile": lead.get("profile_url") or (urn_field if urn_field.startswith("http") else None),
            "interactions": len(own),
        }, ["linkedin/person", f"status/{_tag(status)}" if status else ""])
        lines = [f"# {name}", ""]
        if lead.get("headline"):
            lines += [str(lead["headline"]), ""]
        lines += ["## Engaged with", ""]
        if own:
            for item in own:
                post = post_by_id.get(_activity_id(item.get("post_urn")))
                where = _link("Posts", post_note[post["activity_urn"]]) if post else "a post the studio has not imported"
                kind = (item.get("interaction_type") or "engaged").lower()
                lines.append(f"- {kind} on {where}")
                if item.get("comment_text"):
                    lines.append(_indented(_quote(item["comment_text"], 600)))
        else:
            lines.append("No interactions recorded.")
        history = stages.get(lead_id, [])
        if history:
            lines += ["", "## Stage history", ""]
            lines += [f"- {_date(e['changed_at'])}: {e.get('from_status') or 'new'} to {e['to_status']}" for e in history]
        if lead.get("notes"):
            lines += ["", "## Notes in the studio", "", str(lead["notes"])]
        notes[f"People/{name}.md"] = fm + "\n".join(lines) + "\n"

    # ---- Topics
    for topic, name in topic_note.items():
        members = [p for p in posts if topic_of[p["activity_urn"]] == topic]
        engagers = {i["lead_id"] for p in members for i in by_post.get(p["activity_urn"], [])}
        fm = _frontmatter({"posts": len(members), "people": len(engagers)}, ["linkedin/topic"])
        lines = [f"# {name}", "",
                 "Grouped by the studio's topic classifier, a keyword guess. Rename or merge freely.", "",
                 "## Posts", ""]
        lines += [f"- {_link('Posts', post_note[p['activity_urn']])}" for p in members]
        notes[f"Topics/{name}.md"] = fm + "\n".join(lines) + "\n"

    # ---- Outbound
    for author, items in outbound.items():
        name = outbound_note[author]
        matches = lead_by_name.get(author.lower(), [])
        fm = _frontmatter({
            "comments": sum(1 for i in items if i.get("kind") == "comment"),
            "reactions": sum(1 for i in items if i.get("kind") == "reaction"),
        }, ["linkedin/outbound"])
        lines = [f"# {name}", "", "Someone whose posts you engaged with.", ""]
        if len(matches) == 1:
            lines += [f"Engaged back: {_link('People', person_note[matches[0]])} (matched by name)", ""]
        lines += ["## What you did", ""]
        for item in items:
            mine = str(item.get("my_text") or "").strip()
            if item.get("kind") == "comment":
                lines.append(f"- commented: \"{mine[:240]}\"" if mine else "- commented")
            else:
                lines.append(f"- reacted ({item.get('reaction_kind') or 'like'})")
            if item.get("target_excerpt"):
                lines.append(_indented(_quote(item["target_excerpt"], 240)))
        notes[f"Outbound/{name}.md"] = fm + "\n".join(lines) + "\n"

    # ---- Drafts
    for draft in record["drafts"]:
        content = draft.get("raw_content") or draft.get("formatted_content") or ""
        title = draft.get("title") or next((ln for ln in content.splitlines() if ln.strip()), "")
        name = draft_names.claim(safe_name(title, 70), f"Draft {draft.get('id')}")
        fm = _frontmatter({"status": draft.get("status"), "archetype": draft.get("archetype"),
                           "created": _date(draft.get("created_at"))}, ["studio/draft"])
        notes[f"Drafts/{name}.md"] = fm + f"# {name}\n\n" + (content.strip() or "(empty)") + "\n"

    topic_links = [f"- {_link('Topics', n, t)}" for t, n in topic_note.items()]

    # ---- Me
    me = record["identity"] if record["identity"] and record["identity"].get("confirmed_at") else None
    me_lines: List[str] = []
    if me:
        me_lines = [f"# {me.get('display_name') or 'Me'}", ""]
        if me.get("headline"):
            me_lines += [str(me["headline"]), ""]
        if me.get("about"):
            me_lines += ["## About", "", str(me["about"]).strip(), ""]
        if record["positions"]:
            me_lines += ["## Roles", ""]
            for p in record["positions"]:
                bits = [b for b in (p.get("title"), p.get("company"), p.get("date_range")) if b]
                me_lines.append("- " + ", ".join(str(b) for b in bits))
            me_lines.append("")
        if record["education"]:
            me_lines += ["## Education", ""]
            me_lines += ["- " + ", ".join(str(b) for b in (e.get("school"), e.get("degree"), e.get("date_range")) if b)
                         for e in record["education"]]
            me_lines.append("")
        if record["skills"]:
            me_lines += ["## Skills", "", ", ".join(record["skills"]), ""]
        me_fm = _frontmatter({
            "vanity": me.get("vanity"), "profile": me.get("profile_url"), "location": me.get("location"),
            "company": me.get("current_company"), "followers": me.get("follower_count"),
            "connections": me.get("connection_count"),
        }, ["linkedin/me"])
    else:
        me_fm = _frontmatter({}, ["linkedin/me"])
        me_lines = ["# Me", "", "The studio has not confirmed which LinkedIn profile is yours yet. "
                    "Confirm it in Setup and export again."]
    me_lines += ["", "## Topics", ""] + (topic_links or [NO_POSTS])
    notes["Me.md"] = me_fm + "\n".join(me_lines) + "\n"

    # ---- Home
    repeat = sorted(
        ((len({_activity_id(i.get("post_urn")) for i in items} - {""}), lid) for lid, items in by_lead.items()),
        reverse=True,
    )
    home = [
        "# LinkedIn, from Inox Hydra", "",
        f"Exported {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC. "
        "Open the graph view to see posts as hubs and the people around them.", "",
        "- [[Me]]",
        "- " + ", ".join([
            _plural(len(posts), "post", "posts"),
            _plural(len(leads), "person", "people"),
            _plural(len(topic_note), "topic", "topics"),
            _plural(len(outbound), "person", "people") + " you engage with",
            _plural(len(record["drafts"]), "draft", "drafts"),
        ]), "",
    ]
    regulars = [(n, lid) for n, lid in repeat if n >= 2][:10]
    if regulars:
        home += ["## People who engaged on more than one post", ""]
        home += [f"- {_link('People', person_note[lid])}: {n} posts" for n, lid in regulars]
        home.append("")
    home += ["## Topics", ""] + (topic_links or [NO_POSTS])
    home += ["", "Notes this export writes are rewritten each time you export. Write your own below a "
             f"\"{YOUR_NOTES}\" heading in any of them, or in notes of your own, and they are kept."]
    notes["Home.md"] = "\n".join(home) + "\n"

    for path in list(notes):
        notes[path] = notes[path].rstrip("\n") + f"\n\n{YOUR_NOTES}\n\n"
    return notes


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _read_manifest(root: str) -> Optional[Dict[str, Any]]:
    try:
        with open(os.path.join(root, MANIFEST), encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) and isinstance(data.get("files"), list) else None
    except (OSError, ValueError):
        return None


def _kept_notes(path: str) -> str:
    """What the creator wrote under "## Your notes" in the previous copy of a note."""
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return ""
    index = text.find("\n" + YOUR_NOTES + "\n")
    return text[index + len(YOUR_NOTES) + 2:].strip("\n") if index >= 0 else ""


def _inside(root: str, relative: str) -> str:
    target = os.path.normpath(os.path.join(root, relative))
    if os.path.commonpath([root, target]) != root:
        raise ExportRefused(f"refusing to write outside the vault: {relative}")
    return target


def write_vault(notes: Dict[str, str], destination: str) -> Dict[str, Any]:
    root = os.path.abspath(destination)
    previous = None
    if os.path.isdir(root) and os.listdir(root):
        previous = _read_manifest(root)
        if previous is None:
            raise ExportRefused(
                f"{root} already has files in it and is not an earlier Inox Hydra export. "
                "Choose an empty folder, or the folder a previous export created."
            )
    os.makedirs(root, exist_ok=True)

    kept = 0
    for relative, text in notes.items():
        target = _inside(root, relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        own = _kept_notes(target) if previous else ""
        if own:
            kept += 1
            text = text.rstrip("\n") + "\n\n" + own + "\n"
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    removed = 0
    if previous:
        for relative in previous["files"]:
            if relative in notes:
                continue
            target = _inside(root, relative)
            if os.path.isfile(target) and not _kept_notes(target):
                os.remove(target)
                removed += 1

    obsidian = os.path.join(root, ".obsidian")
    if not os.path.exists(obsidian):
        os.makedirs(obsidian)
        with open(os.path.join(obsidian, "graph.json"), "w", encoding="utf-8") as handle:
            json.dump({
                "colorGroups": [{"query": f'path:"{f}"', "color": {"a": 1, "rgb": c}} for f, c in GRAPH_COLOURS.items()],
                "showArrow": False, "linkDistance": 180, "repelStrength": 10,
            }, handle, indent=2)

    with open(os.path.join(root, MANIFEST), "w", encoding="utf-8") as handle:
        json.dump({
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "files": sorted(notes),
        }, handle, indent=2)

    counts = {folder: sum(1 for p in notes if p.startswith(folder + "/")) for folder in FOLDERS}
    return {"path": root, "notes": len(notes), "counts": counts, "kept_your_notes": kept, "removed": removed}


def export_obsidian_vault(destination: Optional[str] = None) -> Dict[str, Any]:
    """Reads the local record and writes it as an Obsidian vault. Returns where, and how much."""
    if destination is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = os.path.join(paths.get_exports_dir(), f"obsidian_vault_{stamp}")
    return write_vault(build_notes(read_record()), destination)
