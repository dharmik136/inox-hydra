"""
LinkedIn's Analytics Export: the Creator's Exact Figures, Handed Over by LinkedIn.
=================================================================================
LinkedIn's creator analytics page has an Export button that writes an .xlsx
of the member's own analytics "from the past seven days up to the past 365
days" (LinkedIn Help a701208, a704175), and a post's own analytics page is
reported to export one too. It is the one sanctioned source of exact
figures: the page readers see LinkedIn's rounded "1.2K", and the network
reader that saw exact figures is off by default and regarded by LinkedIn as
automation. A file the creator downloads and hands over touches no clause
of LinkedIn's terms (capture report, item 28).

The flow is the archive importer's, and keeps the creator in charge:

  1. request   Setup opens LinkedIn's analytics page in the bridge browser,
               where the creator presses Export themselves.
  2. find      Once they say they exported it, Setup looks in Downloads for
               a spreadsheet named like LinkedIn's, and offers it. They can
               also choose the file by hand.
  3. preview   Nothing is written until they have seen, sheet by sheet,
               what the studio recognises and what it does not.
  4. import    What they kept ticked is imported, its source named.

Where each sheet goes, every figure exact, source 'linkedin_export':

  ENGAGEMENT    impressions and engagements by day   -> analytics_daily
  FOLLOWERS     new followers by day, and the total   -> analytics_daily
  TOP POSTS     impressions and engagements of each   -> post_metric_observations,
                of your posts published in the range     dated at the range's end
  a post's own  its figures, each under its name      -> post_metric_observations,
  export                                                 dated when it was exported
  DISCOVERY     totals over the range                 -> the import's own record
  DEMOGRAPHICS  recognised, not imported

A day's engagements go in analytics_daily.reactions, where the page reader
has always put LinkedIn's engagements card and where the Analytics screen
reads Engagements: one definition for one figure. One row is one source: a
day the analytics page already read is kept as it was read, and said so.

Verified against a real file: not yet. LinkedIn documents neither the sheets
nor the columns, and no real export has been supplied, so every sheet and
column name here is this module's best understanding, treated as
unverified. A sheet or column it does not recognise is reported in the
preview as not recognised and left out, never guessed at.

Strict Invariants:
- Zero em-dashes in any code, docstring or comment.
- Zero egress: reads a local file, writes the local database. No network
  library is imported (tests/test_qc4_t6_analytics_export.py holds that).
- Nothing invented: a total is never split into parts it does not name, a
  figure never lands under a name it was not read under, a date whose day
  and month order cannot be told is no date, and a top post's figure that
  covers only part of its life is not a reading of it.
- An .xlsx is a zip of XML, read with the standard library because openpyxl
  is not a dependency; every part is bounded, and markup a spreadsheet never
  carries (a DOCTYPE, an entity) is refused.
"""

import json
import os
import re
import threading
import uuid
import zipfile
import zlib
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree

try:
    from . import archive_import, paths, post_summary
    from .database import get_db
except ImportError:
    import archive_import
    import paths
    import post_summary
    from database import get_db

ANALYTICS_PAGE = "https://www.linkedin.com/analytics/creator/content/"
REQUESTED_KEY = "analytics_export_requested_at"
IMPORTS_KEY = "analytics_export_imports"
IMPORTS_KEPT = 20
SOURCE = "linkedin_export"
PRECISION = "exact"
PERIOD = "1d"

VERIFIED_AGAINST_REAL_FILE = False
VERIFICATION = ("Checked against a real LinkedIn export: not yet. The sheet and column names the studio looks for "
                "are its best understanding of LinkedIn's export; anything it does not recognise is listed as not "
                "recognised and left out, never guessed at.")

# Offered from Downloads by name (unverified: LinkedIn's file names are not
# documented either; the dashboard's is reported as Content_<start>_<end>_<name>).
EXPORT_SUFFIX = ".xlsx"
NAME_HINTS = ("content_", "linkedin", "analytics", "postanalytics", "post_analytics")
NAME_RANGE = re.compile(r"(\d{4}-\d{2}-\d{2})[_ ](\d{4}-\d{2}-\d{2})")
NAME_ACTIVITY = re.compile(r"(?<!\d)(\d{19})(?!\d)")

MAX_FILE_BYTES = 25 * 1024 * 1024
# A real export's parts are well under a megabyte (a year of days, fifty
# posts). The reader builds each part's whole tree in memory, about a hundred
# times the part's size, so these keep a hostile file to a bounded cost.
MAX_PART_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 40 * 1024 * 1024
MAX_RATIO = 200
MAX_MEMBERS = 400
MAX_SHEETS = 25
MAX_ROWS = 20_000
MAX_COLUMNS = 64
MAX_CELL_CHARS = 2000
HEADER_SCAN = 15
UPLOAD_TTL = timedelta(hours=24)
# Day 0 of a workbook's serial dates. Excel's usual system counts from the
# last day of 1899; a workbook marked date1904 (Excel for Mac could save one)
# counts from 1 January 1904, 1,462 days later. Read in the wrong system, a
# date lands four years and a day away and still looks certain.
EXCEL_EPOCH = date(1899, 12, 30)
EXCEL_EPOCH_1904 = date(1904, 1, 1)

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
NS_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"

_BUSY = threading.Lock()
BUSY_MESSAGE = "The studio is already importing an analytics export. Wait for it to finish, then try again."
NOT_YOURS = "not one of your recorded posts; import your posts first"

# ---------------------------------------------------------------------------
# The layout, every name unverified
# ---------------------------------------------------------------------------

SHEET_NAMES = {
    "discovery": "discovery",
    "engagement": "engagement", "engagements": "engagement",
    "top posts": "top_posts",
    "followers": "followers", "new followers": "followers",
    "demographics": "demographics", "top demographics": "demographics",
    "performance": "post", "post performance": "post", "post analytics": "post",
}

VOCABULARY: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "engagement": {"date": ("date",), "impressions": ("impressions",), "engagements": ("engagements",)},
    "followers": {"date": ("date",), "new_followers": ("new followers", "followers gained")},
    "top_posts": {"url": ("post url", "post link", "url", "link"),
                  "published": ("post publish date", "publish date", "post date", "date"),
                  "engagements": ("engagements",), "impressions": ("impressions",)},
    "discovery": {"range": ("overall performance",), "impressions": ("impressions",),
                  "members_reached": ("members reached", "unique members reached")},
    "post": {"url": ("post url", "post link", "url", "link"),
             "published": ("post publish date", "publish date", "post date", "posted", "date"),
             "impressions": ("impressions",),
             "members_reached": ("members reached", "unique viewers", "unique views", "reach"),
             "reactions": ("reactions",), "comments": ("comments",), "reposts": ("reposts", "shares"),
             "saves": ("saves",), "sends": ("sends", "sends on linkedin"), "engagements": ("engagements",)},
}

# Labels a LinkedIn export is reported to carry that the studio keeps no
# figure for yet: listed as left out with that reason, not as unrecognised.
NO_HOME_YET = ("profile viewers from this post", "followers gained from this post", "profile viewers",
               "link visits", "link clicks", "premium button clicks", "premium custom button clicks")

POST_FIGURES = ("impressions", "members_reached", "reactions", "comments", "reposts", "saves", "sends", "engagements")

LABELS = {
    "engagement": "Impressions and engagements by day",
    "followers": "New followers by day, and your follower total",
    "top_posts": "Your top posts of the range",
    "discovery": "Totals over the range",
    "demographics": "Audience demographics",
    "post": "One post's own figures",
}
WRITES = {
    "engagement": "Your daily analytics: impressions and engagements for each day, exact.",
    "followers": "Your daily analytics: new followers for each day, and your follower total on the day it names.",
    "top_posts": ("A reading of each of your recorded posts that was published inside the export's range: its "
                  "impressions and engagements up to the range's last day. A post published before the range "
                  "is left out, because the figure covers only part of its life."),
    "discovery": "Kept with the record of this import, as read. A total over the range is not a day's figure.",
    "post": ("A reading of the post the file names, dated when it was exported, with each figure under its own "
             "name."),
}
DEMOGRAPHICS_NOTE = "Recognised, not imported: the studio keeps no audience demographics from exports."
DEFAULTS = {"engagement": True, "followers": True, "top_posts": True, "discovery": True, "post": True}


class ExportError(ValueError):
    """Shown to the creator as it is."""


class ExportBusy(ExportError):
    pass


# ---------------------------------------------------------------------------
# Finding and keeping the file
# ---------------------------------------------------------------------------

def find_exports(limit: int = 5) -> List[Dict[str, Any]]:
    """Spreadsheets in Downloads named like LinkedIn's analytics export, newest first. Names and sizes only."""
    hits = []
    for directory in archive_import.downloads_dirs():
        try:
            names = os.listdir(directory)
        except OSError:
            continue
        listed = set(names)
        for name in names:
            final, partial = archive_import._partial(name)
            lower = final.lower()
            if not lower.endswith(EXPORT_SUFFIX) or not any(hint in lower for hint in NAME_HINTS):
                continue
            if partial and final in listed:
                continue
            full = os.path.join(directory, name)
            try:
                stat = os.stat(full)
            except OSError:
                continue
            if not os.path.isfile(full):
                continue
            hits.append({
                "name": final,
                "path": full,
                "bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "downloading": partial or stat.st_size == 0
                               or any(final + s in listed for s in archive_import.PARTIAL_SUFFIXES),
            })
    hits.sort(key=lambda h: h["modified"], reverse=True)
    return hits[:limit]


def _uploads_dir() -> str:
    return paths._ensure(os.path.join(paths.get_data_dir(), "analytics_export_uploads"))


def sweep_uploads() -> None:
    """Removes copies chosen by hand that are older than a day. Run at startup as well as on each upload."""
    _sweep_uploads()


def _sweep_uploads() -> None:
    directory = _uploads_dir()
    cutoff = datetime.now().timestamp() - UPLOAD_TTL.total_seconds()
    for name in os.listdir(directory):
        full = os.path.join(directory, name)
        try:
            if os.path.getmtime(full) < cutoff:
                os.remove(full)
        except OSError:
            pass


class UploadWriter:
    """
    Writes an uploaded spreadsheet to the profile's uploads folder as it
    arrives, capped chunk by chunk. `modified` is when the browser says the
    file was last changed, which for a download is when LinkedIn wrote it.
    """

    def __init__(self, filename: str, modified: Optional[datetime] = None):
        _sweep_uploads()
        self.token = uuid.uuid4().hex
        self.path = os.path.join(_uploads_dir(), f"{self.token}.xlsx")
        self.filename = os.path.basename(filename or "analytics.xlsx")[:200]
        self.modified = modified
        self.written = 0
        self._handle = open(self.path, "wb")

    def write(self, chunk: bytes) -> None:
        self.written += len(chunk)
        if self.written > MAX_FILE_BYTES:
            self.abort()
            raise ExportError("That file is larger than any LinkedIn analytics export the studio expects.")
        self._handle.write(chunk)

    def finish(self) -> str:
        self._handle.close()
        with open(self.path + ".json", "w", encoding="utf-8") as handle:
            json.dump({"name": self.filename,
                       "modified": self.modified.isoformat() if self.modified else None}, handle)
        return f"upload:{self.token}"

    def abort(self) -> None:
        self._handle.close()
        if os.path.exists(self.path):
            os.remove(self.path)


def _resolve(source: str) -> Tuple[str, str, Optional[datetime]]:
    """(path, display name, when the file was written) for a source the studio itself offered."""
    source = source or ""
    if source.startswith("upload:"):
        token = source.split(":", 1)[1]
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            raise ExportError("That upload is not one the studio kept.")
        path = os.path.join(_uploads_dir(), f"{token}.xlsx")
        if not os.path.isfile(path):
            raise ExportError("That upload has expired. Choose the file again.")
        try:
            with open(path + ".json", "r", encoding="utf-8") as handle:
                meta = json.load(handle)
        except (OSError, ValueError):
            meta = {}
        modified = _instant(meta.get("modified"))
        return path, str(meta.get("name") or "analytics.xlsx"), modified
    if source.startswith("downloads:"):
        wanted = source.split(":", 1)[1]
        for hit in find_exports(limit=50):
            if hit["path"] == wanted:
                if hit["downloading"]:
                    raise ExportError(archive_import.STILL_DOWNLOADING)
                return hit["path"], hit["name"], _instant(hit["modified"])
        raise ExportError("That file is no longer in your Downloads folder.")
    raise ExportError("Choose an export from your Downloads folder, or upload one.")


def _instant(text: Any) -> Optional[datetime]:
    if not text:
        return None
    try:
        when = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _discard(source: str) -> None:
    if (source or "").startswith("upload:"):
        try:
            path, _name, _modified = _resolve(source)
        except ExportError:
            return
        for leftover in (path, path + ".json"):
            try:
                os.remove(leftover)
            except OSError:
                pass


def discard(source: str) -> Dict[str, Any]:
    """Deletes an uploaded copy the creator decided not to import. A Downloads file is never touched."""
    _discard(source or "")
    return {"status": "success"}


# ---------------------------------------------------------------------------
# Reading the spreadsheet
# ---------------------------------------------------------------------------

class _Parts:
    """The zip's parts, read with a running total so the whole file is bounded too."""

    def __init__(self, archive: zipfile.ZipFile):
        self.archive = archive
        self.read_bytes = 0

    def get(self, name: str) -> Optional[bytes]:
        try:
            info = self.archive.getinfo(name)
        except KeyError:
            return None
        if info.file_size > MAX_PART_BYTES or (info.compress_size and info.file_size > info.compress_size * MAX_RATIO):
            raise ExportError("A part of that file is far larger than a spreadsheet should be, so it was not read.")
        self.read_bytes += info.file_size
        if self.read_bytes > MAX_TOTAL_BYTES:
            raise ExportError("That file unpacks to far more than a spreadsheet should, so it was not read.")
        try:
            data = self.archive.read(name)
        except (zipfile.BadZipFile, zlib.error, EOFError) as error:
            raise ExportError("A part of that file is damaged, so it could not be read. Export it from LinkedIn "
                              "again and choose the new file.") from error
        except NotImplementedError as error:
            # Before RuntimeError, of which it is a subclass: an unknown
            # compression method, or strong encryption.
            raise ExportError("That file is packed in a way a spreadsheet is not, so it could not be read.") from error
        except RuntimeError as error:
            # zipfile's answer to an encrypted member with no password.
            raise ExportError("That file is protected with a password, which LinkedIn's export never is, so it "
                              "could not be read.") from error
        except OSError as error:
            raise ExportError(f"That file could not be read: {error.strerror or 'the disk refused it'}.") from error
        # Every part of a spreadsheet is UTF-8. One in UTF-16 would also slip
        # past the byte check below, which reads 8-bit text.
        if data[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in data[:4096]:
            raise ExportError("A part of that file is not written in UTF-8, as every part of a spreadsheet is, "
                              "so it was not read.")
        if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
            raise ExportError("That file carries markup a spreadsheet never does, so it was not read.")
        return data


def _xml(data: bytes) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        raise ExportError(f"That file could not be read as a spreadsheet: {error}") from error


def _text_of(item: ElementTree.Element) -> str:
    """A shared or inline string: its own text runs, without phonetic guides."""
    parts = []
    for child in item:
        if child.tag == f"{NS_MAIN}t":
            parts.append(child.text or "")
        elif child.tag == f"{NS_MAIN}r":
            run = child.find(f"{NS_MAIN}t")
            if run is not None:
                parts.append(run.text or "")
    return "".join(parts)[:MAX_CELL_CHARS]


def _shared_strings(parts: _Parts) -> List[str]:
    data = parts.get("xl/sharedStrings.xml")
    if data is None:
        return []
    return [_text_of(item) for item in _xml(data).iter(f"{NS_MAIN}si")]


def _sheet_parts(parts: _Parts) -> Tuple[List[Tuple[str, str]], date]:
    """(sheet name, part name) in workbook order, and the day its serial dates count from."""
    workbook = parts.get("xl/workbook.xml")
    if workbook is None:
        raise ExportError("That file is not a spreadsheet: it has no workbook in it.")
    root = _xml(workbook)
    settings = root.find(f"{NS_MAIN}workbookPr")
    date1904 = settings is not None and (settings.get("date1904") or "").strip().lower() in ("1", "true")
    targets: Dict[str, str] = {}
    rels = parts.get("xl/_rels/workbook.xml.rels")
    if rels is not None:
        for rel in _xml(rels).iter(f"{NS_PKG}Relationship"):
            target = rel.get("Target") or ""
            target = target[1:] if target.startswith("/") else (target if target.startswith("xl/") else "xl/" + target)
            targets[rel.get("Id") or ""] = target
    found = []
    for sheet in root.iter(f"{NS_MAIN}sheet"):
        part = targets.get(sheet.get(f"{NS_REL}id") or "") or f"xl/worksheets/sheet{len(found) + 1}.xml"
        found.append((sheet.get("name") or f"Sheet{len(found) + 1}", part))
        if len(found) >= MAX_SHEETS:
            break
    return found, (EXCEL_EPOCH_1904 if date1904 else EXCEL_EPOCH)


def _column_index(reference: str) -> Optional[int]:
    letters = "".join(ch for ch in reference if ch.isalpha()).upper()
    if not letters:
        return None
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch) - 64)
    return index - 1


def _cell_value(cell: ElementTree.Element, strings: List[str]) -> Any:
    kind = cell.get("t") or "n"
    if kind == "inlineStr":
        inline = cell.find(f"{NS_MAIN}is")
        return (_text_of(inline).strip() or None) if inline is not None else None
    value = cell.find(f"{NS_MAIN}v")
    text = (value.text or "") if value is not None else ""
    if kind == "s":
        try:
            return strings[int(text)].strip() or None
        except (ValueError, IndexError):
            return None
    if kind in ("str", "d"):
        return text.strip()[:MAX_CELL_CHARS] or None
    if kind == "b":
        return text.strip() == "1"
    if kind == "e":
        return None
    text = text.strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return text[:MAX_CELL_CHARS]
    return int(number) if number.is_integer() and abs(number) < 1e15 else number


def _rows(data: bytes, strings: List[str]) -> Tuple[List[List[Any]], bool]:
    rows: List[List[Any]] = []
    for row in _xml(data).iter(f"{NS_MAIN}row"):
        if len(rows) >= MAX_ROWS:
            return rows, True
        cells: List[Any] = []
        for cell in row.findall(f"{NS_MAIN}c"):
            index = _column_index(cell.get("r") or "")
            if index is None:
                index = len(cells)
            if index >= MAX_COLUMNS:
                continue
            while len(cells) <= index:
                cells.append(None)
            cells[index] = _cell_value(cell, strings)
        rows.append(cells)
    return rows, False


def read_workbook(path: str) -> Dict[str, Any]:
    """Every sheet's rows, in workbook order, bounded. Raises ExportError for anything that is not a spreadsheet."""
    try:
        size = os.path.getsize(path)
    except OSError as error:
        raise ExportError("That file could not be opened.") from error
    if size > MAX_FILE_BYTES:
        raise ExportError("That file is larger than any LinkedIn analytics export the studio expects.")
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, ValueError, OSError) as error:
        raise ExportError("That file is not an .xlsx spreadsheet: it does not open as one.") from error
    with archive:
        if len(archive.infolist()) > MAX_MEMBERS:
            raise ExportError("That file holds far more parts than a spreadsheet does, so it was not read.")
        parts = _Parts(archive)
        strings = _shared_strings(parts)
        sheets = []
        named, epoch = _sheet_parts(parts)
        if not named:
            raise ExportError("That file holds no sheets, so there is nothing in it to read.")
        for name, part in named:
            data = parts.get(part)
            if data is None:
                # Named by the workbook and absent from the file: listed, not dropped.
                sheets.append({"name": name, "rows": [], "truncated": False, "missing": True})
                continue
            rows, truncated = _rows(data, strings)
            sheets.append({"name": name, "rows": rows, "truncated": truncated})
    return {"bytes": size, "sheets": sheets, "epoch": epoch}


# ---------------------------------------------------------------------------
# Dates and counts
# ---------------------------------------------------------------------------

_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september",
           "october", "november", "december")
_ISO = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[T ].*)?$")
_SLASHED = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
_DAY_MONTH = re.compile(r"^(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})$")
_MONTH_DAY = re.compile(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})$")


def _month(word: str) -> Optional[int]:
    word = word.lower()
    for number, name in enumerate(_MONTHS, start=1):
        if len(word) >= 3 and name.startswith(word):
            return number
    return None


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _date_cell(value: Any, epoch: date = EXCEL_EPOCH) -> Tuple[Optional[date], Optional[Tuple[int, int, int]]]:
    """A date, or, for a slashed date, its (first, second, year) for the column to put in order."""
    if value is None or isinstance(value, bool):
        return None, None
    if isinstance(value, (int, float)):
        if 20000 <= value <= 80000:
            return epoch + timedelta(days=int(value)), None
        return None, None
    text = str(value).strip()
    found = _ISO.match(text)
    if found:
        return _safe_date(int(found.group(1)), int(found.group(2)), int(found.group(3))), None
    found = _DAY_MONTH.match(text)
    if found and _month(found.group(2)):
        return _safe_date(int(found.group(3)), _month(found.group(2)), int(found.group(1))), None
    found = _MONTH_DAY.match(text)
    if found and _month(found.group(1)):
        return _safe_date(int(found.group(3)), _month(found.group(1)), int(found.group(2))), None
    found = _SLASHED.match(text)
    if found:
        return None, (int(found.group(1)), int(found.group(2)), int(found.group(3)))
    return None, None


def _ordered(parts: Tuple[int, int, int], order: str) -> Optional[date]:
    first, second, year = parts
    return _safe_date(year, first, second) if order == "month_first" else _safe_date(year, second, first)


def _order(slashed: List[Tuple[int, int, int]], within: Optional[Tuple[date, date]]) -> Optional[str]:
    """
    Whether a column's slashed dates put the month first or the day, decided
    by the dates themselves: a part over 12 settles it; failing that, rows a
    day apart in only one order; failing that, the one order that keeps them
    inside the range the file's name gives. None when nothing settles it.
    """
    day_first = any(first > 12 for first, _s, _y in slashed)
    month_first = any(second > 12 for _f, second, _y in slashed)
    if day_first and month_first:
        return None
    if day_first or month_first:
        return "day_first" if day_first else "month_first"
    fitting = []
    for order in ("month_first", "day_first"):
        dates = [_ordered(parts, order) for parts in slashed]
        if any(d is None for d in dates):
            continue
        steps = [abs((b - a).days) for a, b in zip(dates, dates[1:])]
        if steps and all(step == 1 for step in steps):
            fitting.append(order)
    if len(fitting) == 1:
        return fitting[0]
    if within:
        inside = [order for order in ("month_first", "day_first")
                  if all((d := _ordered(parts, order)) is not None and within[0] <= d <= within[1]
                         for parts in slashed)]
        if len(inside) == 1:
            return inside[0]
    return None


UNORDERED = ("its dates are written as numbers with slashes and nothing in the file says whether the day or the "
             "month comes first")


def _dates(values: List[Any], within: Optional[Tuple[date, date]],
           epoch: date = EXCEL_EPOCH) -> Tuple[List[Optional[date]], Optional[str]]:
    """Each value's date, a column's slashed dates put in one order, or the reason they could not be."""
    parsed = [_date_cell(value, epoch) for value in values]
    slashed = [parts for _d, parts in parsed if parts]
    order = _order(slashed, within) if slashed else None
    if slashed and order is None:
        return [None] * len(values), UNORDERED
    return [found if found else (_ordered(parts, order) if parts else None) for found, parts in parsed], None


def _count(value: Any) -> Optional[int]:
    """A whole, non-negative figure, or None. Nothing is rounded into existence."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value >= 0 else None
    text = str(value).strip()
    # A comma is read only as a thousands separator: "1,234" is 1234, while
    # "1,2,3" or "12,34" is no figure, not 123 or 1234.
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", text):
        return int(text.replace(",", ""))
    return int(text) if re.fullmatch(r"\d+", text) else None


# ---------------------------------------------------------------------------
# Recognising what is in a sheet
# ---------------------------------------------------------------------------

def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower().rstrip(":")).strip()


def _field(label: str, vocabulary: Dict[str, Tuple[str, ...]]) -> Optional[str]:
    return next((field for field, names in vocabulary.items() if label in names), None)


def _blocks(row: List[Any]) -> List[Tuple[int, int]]:
    """The runs of non-empty cells in a header row, as (first column, last column + 1)."""
    blocks, start = [], None
    for index, cell in enumerate(row + [None]):
        empty = cell is None or str(cell).strip() == ""
        if not empty and start is None:
            start = index
        elif empty and start is not None:
            blocks.append((start, index))
            start = None
    return blocks


def _header(row: List[Any], vocabulary: Dict[str, Tuple[str, ...]], start: int = 0,
            end: Optional[int] = None) -> Tuple[Dict[str, int], List[str]]:
    """(field -> column, header cells not recognised) for one block of a header row."""
    found: Dict[str, int] = {}
    unknown: List[str] = []
    for index in range(start, end if end is not None else len(row)):
        cell = row[index] if index < len(row) else None
        if cell is None or isinstance(cell, (int, float, bool)):
            continue
        label = _norm(cell)
        if not label:
            continue
        field = _field(label, vocabulary)
        if field and field not in found:
            found[field] = index
        else:
            unknown.append(str(cell).strip())
    return found, unknown


def _pairs(rows: List[List[Any]]) -> List[Tuple[str, str, Any]]:
    """Label and value rows: (normalised label, the label as written, the first value after it)."""
    out = []
    for row in rows:
        if not row or row[0] is None or isinstance(row[0], (int, float, bool)):
            continue
        value = next((cell for cell in row[1:] if cell is not None and str(cell).strip() != ""), None)
        out.append((_norm(row[0]), str(row[0]).strip(), value))
    return out


def _post_shape(rows: List[List[Any]]) -> Optional[str]:
    """'pairs' or 'table' when a sheet of unknown name holds one post's figures, by what it holds."""
    vocabulary = VOCABULARY["post"]
    pairs = [label for label, _raw, value in _pairs(rows[:60])
             if _field(label, vocabulary) in POST_FIGURES and _count(value) is not None]
    if len(pairs) >= 2:
        return "pairs"
    for row in rows[:HEADER_SCAN]:
        found, _unknown = _header(row, vocabulary)
        if len([f for f in found if f in POST_FIGURES]) >= 2:
            return "table"
    return None


def _kind(sheet: Dict[str, Any]) -> Optional[str]:
    kind = SHEET_NAMES.get(_norm(sheet["name"]))
    if kind:
        return kind
    return "post" if _post_shape(sheet["rows"]) else None


# ---------------------------------------------------------------------------
# Reading each kind of sheet into figures
# ---------------------------------------------------------------------------

def _daily_table(rows: List[List[Any]], kind: str, within: Optional[Tuple[date, date]],
                 epoch: date = EXCEL_EPOCH) -> Dict[str, Any]:
    """A table of days: {days: {date: {field: count}}, recognised, unknown, problem, rows}."""
    vocabulary = VOCABULARY[kind]
    for at, row in enumerate(rows[:HEADER_SCAN]):
        found, unknown = _header(row, vocabulary)
        if "date" in found and len(found) >= 2:
            body = [r for r in rows[at + 1:] if any(c is not None and str(c).strip() != "" for c in r)]
            column = found["date"]
            dates, problem = _dates([r[column] if column < len(r) else None for r in body], within, epoch)
            days: Dict[date, Dict[str, int]] = {}
            skipped = 0
            for r, day in zip(body, dates):
                figures = {f: _count(r[i]) for f, i in found.items() if f != "date" and i < len(r)}
                figures = {f: v for f, v in figures.items() if v is not None}
                if day is None or not figures:
                    skipped += 1
                    continue
                days.setdefault(day, {}).update(figures)
            return {"days": days, "recognised": sorted(found), "unknown": unknown, "problem": problem,
                    "rows": len(body), "skipped": skipped}
    return {"days": {}, "recognised": [], "unknown": [], "rows": 0, "skipped": 0,
            "problem": "none of its columns are the ones the studio knows"}


TOTAL_FOLLOWERS = re.compile(r"^total followers on (.+)$")


def _followers_total(rows: List[List[Any]], within: Optional[Tuple[date, date]],
                     epoch: date = EXCEL_EPOCH) -> Optional[Dict[str, Any]]:
    """The 'Total followers on <date>' line: {date, followers} or {problem}."""
    for label, raw, value in _pairs(rows[:HEADER_SCAN]):
        found = TOTAL_FOLLOWERS.match(label)
        if not found:
            continue
        count = _count(value)
        when_text = raw.split(" on ", 1)[1].rstrip(":").strip() if " on " in raw else found.group(1)
        dates, problem = _dates([when_text], within, epoch)
        if count is None or dates[0] is None:
            return {"problem": problem or "its date or its figure could not be read"}
        return {"date": dates[0], "followers": count}
    return None


def _top_posts(rows: List[List[Any]]) -> Dict[str, Any]:
    """
    Each post's figures, from one or more tables side by side under one
    header row: each table is read on its own, by its own post column, and
    the figures are joined by post. A row is never read across two tables.
    """
    vocabulary = VOCABULARY["top_posts"]
    for at, row in enumerate(rows[:HEADER_SCAN]):
        tables = []
        unknown: List[str] = []
        for start, end in _blocks(row):
            found, extra = _header(row, vocabulary, start, end)
            if "url" in found and ({"engagements", "impressions"} & set(found)):
                tables.append(found)
                unknown += extra
        if not tables:
            continue
        posts: Dict[str, Dict[str, Any]] = {}
        skipped = 0
        body = rows[at + 1:]
        for found in tables:
            for r in body:
                url = r[found["url"]] if found["url"] < len(r) else None
                if url is None or str(url).strip() == "":
                    continue
                urn = _urn(str(url))
                figures = {f: _count(r[i]) for f, i in found.items()
                           if f in ("engagements", "impressions") and i < len(r)}
                figures = {f: v for f, v in figures.items() if v is not None}
                if not urn or not figures:
                    skipped += 1
                    continue
                entry = posts.setdefault(urn, {"figures": {}, "published": None})
                entry["figures"].update(figures)
                if "published" in found and found["published"] < len(r):
                    entry["published"] = entry["published"] or r[found["published"]]
        recognised = sorted({f for found in tables for f in found})
        return {"posts": posts, "recognised": recognised, "unknown": unknown, "problem": None,
                "rows": len(posts), "skipped": skipped, "tables": len(tables)}
    return {"posts": {}, "recognised": [], "unknown": [], "rows": 0, "skipped": 0, "tables": 0,
            "problem": "none of its columns are the ones the studio knows"}


def _urn(url: str) -> Optional[str]:
    try:
        from . import post_identity
    except ImportError:
        import post_identity
    return post_identity.extract_activity_urn(url)


def _pairs_sheet(rows: List[List[Any]], vocabulary: Dict[str, Tuple[str, ...]]) -> Dict[str, Any]:
    """A sheet of label and value rows: {values, unknown, no_home}."""
    values: Dict[str, Any] = {}
    unknown, no_home = [], []
    for label, raw, value in _pairs(rows):
        field = _field(label, vocabulary)
        if field and field not in values:
            values[field] = value
        elif label in NO_HOME_YET:
            no_home.append(raw)
        elif value is not None:
            unknown.append(raw)
    return {"values": values, "unknown": unknown, "no_home": no_home}


def _post_sheet(rows: List[List[Any]], file_name: str) -> Dict[str, Any]:
    """One post's own figures, in either shape: {urn, figures, recognised, unknown, no_home, problem}."""
    vocabulary = VOCABULARY["post"]
    shape = _post_shape(rows)
    values: Dict[str, Any] = {}
    unknown: List[str] = []
    no_home: List[str] = []
    if shape == "pairs":
        read = _pairs_sheet(rows, vocabulary)
        values, unknown, no_home = read["values"], read["unknown"], read["no_home"]
    elif shape == "table":
        for at, row in enumerate(rows[:HEADER_SCAN]):
            found, extra = _header(row, vocabulary)
            if len([f for f in found if f in POST_FIGURES]) >= 2:
                body = [r for r in rows[at + 1:] if any(c is not None and str(c).strip() != "" for c in r)]
                if len(body) != 1:
                    return {"problem": (f"it holds {len(body)} rows of figures where one post's export holds "
                                        "one, so which row is the post cannot be told"),
                            "recognised": sorted(found), "unknown": extra, "no_home": []}
                values = {f: body[0][i] for f, i in found.items() if i < len(body[0])}
                unknown = [c for c in extra if _norm(c) not in NO_HOME_YET]
                no_home = [c for c in extra if _norm(c) in NO_HOME_YET]
                break
    figures = {f: _count(values.get(f)) for f in POST_FIGURES}
    figures = {f: v for f, v in figures.items() if v is not None}
    urn = _urn(str(values["url"])) if values.get("url") else None
    if not urn:
        named = NAME_ACTIVITY.search(file_name or "")
        urn = f"urn:li:activity:{named.group(1)}" if named else None
    problem = None
    if not figures:
        problem = "none of its figures could be read"
    elif not urn:
        problem = "it does not say which post it is, by a post link or by the post's number in the file's name"
    return {"urn": urn, "figures": figures, "recognised": sorted(values), "unknown": unknown, "no_home": no_home,
            "problem": problem}


# ---------------------------------------------------------------------------
# The whole file
# ---------------------------------------------------------------------------

def _name_range(name: str) -> Optional[Tuple[date, date]]:
    found = NAME_RANGE.search(name or "")
    if not found:
        return None
    try:
        start, end = date.fromisoformat(found.group(1)), date.fromisoformat(found.group(2))
    except ValueError:
        return None
    return (start, end) if start <= end else None


def _understand(name: str, workbook: Dict[str, Any], modified: Optional[datetime]) -> Dict[str, Any]:
    """Every sheet recognised or not, what each would write, and the range the export covers."""
    within = _name_range(name)
    epoch = workbook.get("epoch", EXCEL_EPOCH)
    sheets = []
    daily_dates: List[date] = []
    for sheet in workbook["sheets"]:
        rows = sheet["rows"]
        kind = _kind(sheet)
        first = [str(c) for c in (rows[0] if rows else []) if c is not None][:10]
        entry: Dict[str, Any] = {"name": sheet["name"], "kind": kind, "truncated": sheet["truncated"],
                                 "recognised": [], "not_recognised": [], "left_out": [], "rows": 0}
        if sheet.get("missing"):
            entry.update(label=LABELS.get(kind, sheet["name"]) if kind else sheet["name"], importable=False,
                         default=False, writes=None,
                         note="Not read: the file names this sheet but holds no contents for it.")
            sheets.append(entry)
            continue
        if kind is None:
            entry.update(label=sheet["name"], importable=False, default=False, writes=None,
                         note=(f"Not recognised: the studio does not know a sheet called {sheet['name']}, so "
                               "nothing in it is imported. Its first row reads: " + (", ".join(first) or "nothing")
                               + "."))
            sheets.append(entry)
            continue
        entry.update(label=LABELS[kind], writes=WRITES.get(kind), default=DEFAULTS.get(kind, False))
        problem = None
        if kind in ("engagement", "followers"):
            read = _daily_table(rows, kind, within, epoch)
            entry.update(recognised=read["recognised"], not_recognised=read["unknown"], rows=read["rows"])
            entry["read"] = read
            if kind == "followers":
                total = _followers_total(rows, within, epoch)
                entry["total"] = total
                if total and "date" in total:
                    entry["recognised"] = entry["recognised"] + ["total followers"]
                if read["problem"] and total and "date" in total:
                    read = {**read, "problem": None}
                    entry["read"] = read
            problem = read["problem"]
            if not problem:
                daily_dates.extend(read["days"])
        elif kind == "top_posts":
            read = _top_posts(rows)
            read["epoch"] = epoch
            entry.update(recognised=read["recognised"], not_recognised=read["unknown"], rows=read["rows"])
            entry["read"] = read
            problem = read["problem"]
        elif kind == "discovery":
            read = _pairs_sheet(rows, VOCABULARY["discovery"])
            entry.update(recognised=sorted(read["values"]), not_recognised=read["unknown"],
                         left_out=read["no_home"], rows=len(read["values"]))
            entry["read"] = read
            if not read["values"]:
                problem = "none of its lines are the ones the studio knows"
        elif kind == "demographics":
            entry.update(importable=False, default=False, writes=None, note=DEMOGRAPHICS_NOTE)
            sheets.append(entry)
            continue
        elif kind == "post":
            read = _post_sheet(rows, name)
            entry.update(recognised=read["recognised"], not_recognised=read["unknown"],
                         left_out=read["no_home"], rows=1 if not read["problem"] else 0)
            entry["read"] = read
            problem = read["problem"]
            if not problem and modified is None:
                problem = "when it was exported cannot be read, so its figures cannot be dated"
        if problem:
            entry.update(importable=False, note=f"Recognised, but not imported: {problem}.")
        else:
            notes = []
            if entry["not_recognised"]:
                notes.append("Not recognised, and left out: " + ", ".join(entry["not_recognised"]) + ".")
            if entry["left_out"]:
                notes.append("Recognised, left out because the studio keeps no such figure yet: "
                             + ", ".join(entry["left_out"]) + ".")
            entry.update(importable=entry["rows"] > 0, note=" ".join(notes) or None)
        sheets.append(entry)
    if within:
        span = {"start": within[0].isoformat(), "end": within[1].isoformat(), "from": "the file's name"}
    elif daily_dates:
        span = {"start": min(daily_dates).isoformat(), "end": max(daily_dates).isoformat(),
                "from": "the days in the file"}
    else:
        span = {"start": None, "end": None, "from": None}
    return {"sheets": sheets, "range": span}


def _public(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in entry.items() if k not in ("read", "total")}


def preview(source: str) -> Dict[str, Any]:
    """What the export holds, sheet by sheet, and what would be imported. Writes nothing."""
    path, name, modified = _resolve(source)
    workbook = read_workbook(path)
    understood = _understand(name, workbook, modified)
    return {
        "status": "success",
        "source": source,
        "file": {"name": name, "bytes": workbook["bytes"]},
        "range": understood["range"],
        "sheets": [_public(entry) for entry in understood["sheets"]],
        "recognised": any(entry.get("importable") for entry in understood["sheets"]),
        "verified_against_real_file": VERIFIED_AGAINST_REAL_FILE,
        "verification": VERIFICATION,
    }


def preview_upload(stream, filename: str, modified: Optional[datetime] = None) -> Dict[str, Any]:
    """Keeps an upload and previews it, deleting the copy again if it cannot be read."""
    writer = UploadWriter(filename, modified)
    try:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            writer.write(chunk)
    except BaseException:
        writer.abort()
        raise
    source = writer.finish()
    try:
        return preview(source)
    except BaseException:
        _discard(source)
        raise


# ---------------------------------------------------------------------------
# Writing it
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _columns(conn, table: str) -> set:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


DAILY_COLUMNS = {"impressions": "impressions", "engagements": "reactions", "new_followers": "new_followers",
                 "followers": "followers"}


def _write_days(conn, days: Dict[date, Dict[str, int]]) -> Dict[str, int]:
    """
    One row per day, one source per row. A day nothing has read is written
    whole, every figure the export does not carry NULL, never the table's
    default 0. A day an earlier export wrote is brought up to date. A day
    another source wrote (the analytics page) is kept as it was read.
    """
    added = updated = kept = 0
    for day in sorted(days):
        figures = {DAILY_COLUMNS[f]: v for f, v in days[day].items() if f in DAILY_COLUMNS}
        if not figures:
            continue
        held = conn.execute("SELECT source FROM analytics_daily WHERE date = ?", (day.isoformat(),)).fetchone()
        if held is None:
            row = {"date": day.isoformat(), "impressions": None, "reactions": None, "comments": None, "shares": None,
                   "engagement_rate": None, "followers": None, "connections": None, "profile_views": None,
                   "unique_members_reached": None, "new_followers": None, "source": SOURCE, "period_label": PERIOD,
                   "precision": PRECISION}
            row.update(figures)
            names = list(row)
            conn.execute(f"INSERT INTO analytics_daily ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)})",
                         tuple(row[n] for n in names))
            added += 1
        elif held["source"] == SOURCE:
            sets = ", ".join(f"{column} = COALESCE(?, {column})" for column in figures)
            conn.execute(f"UPDATE analytics_daily SET {sets} WHERE date = ?",
                         tuple(figures.values()) + (day.isoformat(),))
            updated += 1
        else:
            kept += 1
    return {"added": added, "updated": updated, "kept_as_read": kept}


def _published(conn, urn: str, fallback: Any, epoch: date = EXCEL_EPOCH) -> Optional[date]:
    """When a post was published: the studio's record of it, its activity id, or the export's own date."""
    row = conn.execute("SELECT published_at FROM own_posts WHERE activity_urn = ?", (urn,)).fetchone()
    when = _instant(row["published_at"]) if row and row["published_at"] else None
    if when is None:
        try:
            from . import onboarding
        except ImportError:
            import onboarding
        when = _instant(onboarding.published_at_from_urn(urn))
    if when is not None:
        return when.date()
    dates, _problem = _dates([fallback], None, epoch)
    return dates[0]


def _observe(conn, urn: str, at: datetime, figures: Dict[str, int], columns: set) -> None:
    """One exact reading of a post, under the export's own source, so it never overwrites a page's."""
    row = conn.execute("SELECT published_at FROM own_posts WHERE activity_urn = ?", (urn,)).fetchone()
    born = _instant(row["published_at"]) if row and row["published_at"] else None
    if born is None:
        try:
            from . import onboarding
        except ImportError:
            import onboarding
        born = _instant(onboarding.published_at_from_urn(urn))
    age = round((at - born).total_seconds() / 3600.0, 2) if born else None
    values: Dict[str, Any] = {"activity_urn": urn, "observed_at": at.isoformat(),
                              "observed_hour": at.strftime("%Y-%m-%dT%H"), "age_hours": age, "source": SOURCE}
    values.update({f: v for f, v in figures.items() if f in columns})
    if "precision" in columns:
        values["precision"] = PRECISION
    names = list(values)
    updates = ", ".join(f"{n} = excluded.{n}" for n in names if n not in ("activity_urn", "observed_hour", "source"))
    conn.execute(
        f"INSERT INTO post_metric_observations ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)}) "
        f"ON CONFLICT(activity_urn, source, observed_hour) DO UPDATE SET {updates}",
        tuple(values[n] for n in names))


def _held(conn, urn: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM own_posts WHERE activity_urn = ?", (urn,)).fetchone())


def _write_top_posts(conn, read: Dict[str, Any], span: Dict[str, Any], columns: set) -> Tuple[Dict[str, Any], List[str]]:
    if not span.get("start") or not span.get("end"):
        return {"left_out": "the range the export covers could not be read, so whether a figure covers a post's "
                            "whole life cannot be told"}, []
    start, end = date.fromisoformat(span["start"]), date.fromisoformat(span["end"])
    # The end of the range's last day, or now when that is still to come: a
    # reading dated in the future would stand as the post's newest until then.
    at = min(datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc), datetime.now(timezone.utc))
    added = not_yours = before = undated = 0
    urns = []
    for urn, entry in read["posts"].items():
        if not _held(conn, urn):
            not_yours += 1
            continue
        published = _published(conn, urn, entry.get("published"), read.get("epoch", EXCEL_EPOCH))
        if published is None:
            undated += 1
            continue
        if published < start or published > end:
            before += 1
            continue
        _observe(conn, urn, at, entry["figures"], columns)
        urns.append(urn)
        added += 1
    out = {"added": added, "not_yours": not_yours, "published_outside_the_range": before,
           "undated": undated, "skipped": read["skipped"]}
    if not_yours:
        out["not_yours_because"] = NOT_YOURS
    return out, urns


def _write_post(conn, read: Dict[str, Any], modified: datetime, columns: set) -> Tuple[Dict[str, Any], List[str]]:
    urn = read["urn"]
    if not _held(conn, urn):
        return {"added": 0, "not_yours": 1, "not_yours_because": NOT_YOURS}, []
    _observe(conn, urn, modified, read["figures"], columns)
    return {"added": 1, "not_yours": 0}, [urn]


def _record_import(conn, name: str, size: int, span: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
    entry = {"file": name, "bytes": size, "imported_at": _now(), "range": span, "summary": summary,
             "verified_against_real_file": VERIFIED_AGAINST_REAL_FILE}
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (IMPORTS_KEY,)).fetchone()
    try:
        kept = json.loads(row["value"]) if row and row["value"] else []
    except (TypeError, ValueError):
        kept = []
    kept = ([e for e in kept if isinstance(e, dict)] + [entry])[-IMPORTS_KEPT:]
    conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                 (IMPORTS_KEY, json.dumps(kept, default=str)))
    return entry


def import_export(source: str, include: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Imports the sheets the creator kept ticked: `include` names sheets, and
    defaults to every importable one the preview ticks. An uploaded copy is
    deleted once imported.
    """
    path, name, modified = _resolve(source)
    workbook = read_workbook(path)
    understood = _understand(name, workbook, modified)
    sheets = understood["sheets"]
    known = {entry["name"] for entry in sheets}
    wanted = set(include) if include is not None else {e["name"] for e in sheets if e.get("default")}
    unknown_names = wanted - known
    if unknown_names:
        raise ExportError("Not a sheet of this file: " + ", ".join(sorted(unknown_names)))
    if not _BUSY.acquire(blocking=False):
        raise ExportBusy(BUSY_MESSAGE)
    try:
        conn = get_db()
        try:
            columns = _columns(conn, "post_metric_observations")
            summary: Dict[str, Any] = {}
            refreshed: List[str] = []
            days: Dict[date, Dict[str, int]] = {}
            with conn:
                for entry in sheets:
                    if entry["name"] not in wanted:
                        continue
                    if not entry.get("importable"):
                        summary[entry["name"]] = {"left_out": entry.get("note")}
                        continue
                    kind, read = entry["kind"], entry["read"]
                    if kind in ("engagement", "followers"):
                        for day, figures in read["days"].items():
                            days.setdefault(day, {}).update(figures)
                        tally: Dict[str, Any] = {"days_read": len(read["days"]), "rows_skipped": read["skipped"]}
                        total = entry.get("total")
                        if total and "date" in total:
                            days.setdefault(total["date"], {})["followers"] = total["followers"]
                            tally["total_followers"] = {"date": total["date"].isoformat(),
                                                        "followers": total["followers"]}
                        elif total:
                            tally["total_followers"] = {"left_out": total["problem"]}
                        summary[entry["name"]] = tally
                    elif kind == "top_posts":
                        summary[entry["name"]], urns = _write_top_posts(conn, read, understood["range"], columns)
                        refreshed += urns
                    elif kind == "post":
                        summary[entry["name"]], urns = _write_post(conn, read, modified, columns)
                        refreshed += urns
                    elif kind == "discovery":
                        summary[entry["name"]] = {"kept": {k: (_count(v) if k != "range" else str(v))
                                                           for k, v in read["values"].items()}}
                if days:
                    summary["days"] = _write_days(conn, days)
                if refreshed:
                    post_summary.refresh(conn, sorted(set(refreshed)))
                record = _record_import(conn, name, workbook["bytes"], understood["range"], summary)
        finally:
            conn.close()
    finally:
        _BUSY.release()
    _discard(source)
    return {"status": "success", "file": {"name": name, "bytes": workbook["bytes"]}, "range": understood["range"],
            "summary": summary, "imported_at": record["imported_at"],
            "verified_against_real_file": VERIFIED_AGAINST_REAL_FILE}


# ---------------------------------------------------------------------------
# Where the step stands
# ---------------------------------------------------------------------------

def mark_requested() -> Dict[str, Any]:
    """The creator says they pressed Export on LinkedIn, so Downloads may be looked in."""
    conn = get_db()
    try:
        with conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (REQUESTED_KEY, _now()))
    finally:
        conn.close()
    return export_state(look=True)


def imports() -> List[Dict[str, Any]]:
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (IMPORTS_KEY,)).fetchone()
    finally:
        conn.close()
    try:
        kept = json.loads(row["value"]) if row and row["value"] else []
    except (TypeError, ValueError):
        kept = []
    return [e for e in kept if isinstance(e, dict)]


def export_state(look: bool = False) -> Dict[str, Any]:
    """
    Whether an export was asked for, what is waiting in Downloads, and the
    imports made. Downloads is looked in only when asked, only once the
    creator has said they exported, and only until an import follows.
    """
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (REQUESTED_KEY,)).fetchone()
    finally:
        conn.close()
    _sweep_uploads()
    requested_at = row["value"] if row else None
    made = imports()
    waiting = bool(requested_at) and not any(str(e.get("imported_at") or "") >= requested_at for e in made)
    found = find_exports() if look and waiting else []
    imported_names = {e.get("file") for e in made}
    for hit in found:
        hit["imported"] = hit["name"] in imported_names
    return {
        "status": "success",
        "analytics_page": ANALYTICS_PAGE,
        "requested_at": requested_at,
        "waiting": waiting,
        "found": found,
        "watching": archive_import.downloads_dirs() if look and waiting else [],
        "last_import": made[-1] if made else None,
        "verified_against_real_file": VERIFIED_AGAINST_REAL_FILE,
        "verification": VERIFICATION,
    }


def forget(conn) -> None:
    """The record of the imports and any copy kept, for when the creator deletes what the studio holds about them."""
    conn.execute("DELETE FROM settings WHERE key IN (?, ?)", (REQUESTED_KEY, IMPORTS_KEY))
    for name in os.listdir(_uploads_dir()):
        try:
            os.remove(os.path.join(_uploads_dir(), name))
        except OSError:
            pass
