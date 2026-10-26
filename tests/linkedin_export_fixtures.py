"""
LinkedIn analytics exports, built the way this track understands them.
=====================================================================

Fixtures for tests/test_qc4_t6_analytics_export.py and its browser test.
No real export has been supplied (PRD 5.3, an owner action), so every sheet
name, column name and layout here is this track's best understanding of
LinkedIn's export, the same understanding studio/backend/analytics_export.py
reads. When a real file arrives, it replaces these as the reference, and
VERIFIED_AGAINST_REAL_FILE changes with it.

The dashboard export, as reported (Content_<start>_<end>_<name>.xlsx):

  DISCOVERY     Overall Performance | <range>; Impressions | n; Members reached | n
  ENGAGEMENT    Date | Impressions | Engagements, one row a day, dates M/D/YYYY
  TOP POSTS     a note row, then two tables side by side under one header row:
                Post URL | Post publish date | Engagements, an empty column,
                Post URL | Post publish date | Impressions, each table in its
                own order, so a row's two posts are different posts
  FOLLOWERS     Total followers on <date>: | n, then Date | New followers
  DEMOGRAPHICS  Top Demographics | Value | Percentage

A post's own export, as reported: one sheet of label and value rows (Post
URL, Post Date, Impressions, Members reached, Reactions, Comments, Reposts,
Saves, Sends on LinkedIn, and two figures the studio has no place for yet),
and a demographics sheet.

Every person and post here is invented. Strict Invariants: zero em-dashes.
"""

import io
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Sequence, Tuple
from xml.sax.saxutils import escape

RANGE_START = date(2026, 9, 26)
RANGE_END = date(2026, 10, 25)
DASHBOARD_NAME = "Content_2026-09-26_2026-10-25_SampleCreator.xlsx"


def urn_on(day: date, salt: int = 0) -> str:
    """A real-shaped activity URN whose embedded time is noon UTC on `day`."""
    moment = datetime(day.year, day.month, day.day, 12, 0, tzinfo=timezone.utc)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


INSIDE = urn_on(date(2026, 10, 2), 1)      # published inside the range
BEFORE = urn_on(date(2026, 9, 20), 2)      # published before the range
STRANGER = urn_on(date(2026, 10, 5), 3)    # not one of the creator's posts


def feed_url(urn: str) -> str:
    return f"https://www.linkedin.com/feed/update/{urn}/"


def slash(day: date) -> str:
    return f"{day.month}/{day.day}/{day.year}"


def _column(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def build(sheets: Sequence[Tuple[str, List[List[Any]]]], inline: bool = False) -> bytes:
    """An .xlsx with these sheets: text as shared strings (as Excel writes it) or inline, numbers as numbers."""
    shared: List[str] = []
    index_of = {}

    def cell(ref: str, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return f'<c r="{ref}" t="b"><v>{int(value)}</v></c>'
        if isinstance(value, (int, float)):
            return f'<c r="{ref}"><v>{value}</v></c>'
        text = str(value)
        if inline:
            return f'<c r="{ref}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'
        if text not in index_of:
            index_of[text] = len(shared)
            shared.append(text)
        return f'<c r="{ref}" t="s"><v>{index_of[text]}</v></c>'

    parts = {}
    for number, (_name, rows) in enumerate(sheets, start=1):
        body = []
        for r, row in enumerate(rows, start=1):
            cells = "".join(cell(f"{_column(c)}{r}", value) for c, value in enumerate(row))
            body.append(f'<row r="{r}">{cells}</row>')
        parts[f"xl/worksheets/sheet{number}.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(body)}</sheetData></worksheet>')
    workbook_sheets = "".join(
        f'<sheet name="{escape(name)}" sheetId="{n}" r:id="rId{n}"/>' for n, (name, _rows) in enumerate(sheets, start=1))
    parts["xl/workbook.xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{workbook_sheets}</sheets></workbook>')
    rels = "".join(
        f'<Relationship Id="rId{n}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{n}.xml"/>' for n in range(1, len(sheets) + 1))
    parts["xl/_rels/workbook.xml.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + rels
        + "</Relationships>")
    if shared:
        items = "".join(f"<si><t>{escape(text)}</t></si>" for text in shared)
        parts["xl/sharedStrings.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(shared)}" '
            f'uniqueCount="{len(shared)}">{items}</sst>')
    parts["[Content_Types].xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/></Types>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in parts.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def days(start: date = RANGE_START, count: int = 30) -> List[date]:
    return [start + timedelta(days=n) for n in range(count)]


def dashboard_sheets(extra_engagement_column: bool = False) -> List[Tuple[str, List[List[Any]]]]:
    """The dashboard export's sheets, figures invented, one day's figure = 100 + day index."""
    engagement = [["Date", "Impressions", "Engagements"] + (["Engagement rate"] if extra_engagement_column else [])]
    for n, day in enumerate(days()):
        engagement.append([slash(day), 1000 + n, 20 + n] + ([0.02] if extra_engagement_column else []))
    followers = [["Total followers on 10/25/2026:", 1543], [], ["Date", "New followers"]]
    for n, day in enumerate(days()):
        followers.append([slash(day), n % 4])
    top_posts = [
        ["Maximum of 50 posts available to include in this list"],
        [],
        ["Post URL", "Post publish date", "Engagements", None, "Post URL", "Post publish date", "Impressions"],
        # Each table in its own order: the engagements table leads with
        # INSIDE, the impressions table with BEFORE.
        [feed_url(INSIDE), "10/2/2026", 45, None, feed_url(BEFORE), "9/20/2026", 3000],
        [feed_url(BEFORE), "9/20/2026", 30, None, feed_url(INSIDE), "10/2/2026", 2100],
        [feed_url(STRANGER), "10/5/2026", 9, None, feed_url(STRANGER), "10/5/2026", 400],
    ]
    return [
        ("DISCOVERY", [["Overall Performance", "9/26/2026 - 10/25/2026"], ["Impressions", 31435],
                       ["Members reached", 18002]]),
        ("ENGAGEMENT", engagement),
        ("TOP POSTS", top_posts),
        ("FOLLOWERS", followers),
        ("DEMOGRAPHICS", [["Top Demographics", "Value", "Percentage"],
                          ["Job titles", "Software Engineer", "0.12"]]),
    ]


def post_sheets(urn: str = INSIDE, with_url: bool = True) -> List[Tuple[str, List[List[Any]]]]:
    rows = ([["Post URL", feed_url(urn)]] if with_url else []) + [
        ["Post Date", "10/2/2026"],
        ["Post Publish Time", "9:15 AM"],
        ["Impressions", 2100],
        ["Members reached", 1500],
        ["Profile viewers from this post", 12],
        ["Followers gained from this post", 3],
        ["Reactions", 40],
        ["Comments", 5],
        ["Reposts", 2],
        ["Saves", 4],
        ["Sends on LinkedIn", 1],
    ]
    return [("PERFORMANCE", rows), ("TOP DEMOGRAPHICS", [["Category", "Value", "Percentage"]])]
