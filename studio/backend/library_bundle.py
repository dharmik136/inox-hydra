"""
The Inox library: a signed bundle of forms, patterns and examples, matched on this machine.
==========================================================================================
Stage 3 of From your record, and the answer to "good posts related to them"
that sends nothing of the creator's anywhere. The company writes a library
of forms, patterns and examples (its own words, or words it has written
permission for; never a post copied from LinkedIn, ideas report decision
11), signs it once on the vendor's machine (tools/library_bundle.py), and
publishes it as one file. The studio:

  fetches it   only when the creator presses Fetch on the section's What the
               studio knows page, by a conditional GET under the `library`
               egress category, to one of a fixed list of hosts. The request
               carries the address, a User-Agent naming this channel, and the
               tag of the copy already held: nothing about the creator
  verifies it  with the Ed25519 verifier the licence uses (ed25519.py)
               against a public key committed below. An unsigned file, a
               changed byte or a key not listed is refused, said in words,
               and nothing is stored
  keeps it     in library_entries, a table of its own. The unsigned sync
               this replaces (intelligence_sync.py, deleted, decision 10)
               emptied the creator's hook library on every answer; nothing
               here touches viral_templates
  matches it   on this machine: an entry's tags and title read through the
               creator's own recurring words, so an entry about hiring is
               offered to a creator whose posts go under Hiring; labelled
               curated, not measured for them

A file can also be imported by hand (Import a library file), for a machine
that never connects; it is verified exactly as a fetched one is.

Strict Invariants:
- Zero em-dashes in any code, docstring or comment.
- The request carries nothing of the creator's; the bundle is data, never code.
- A refusal is never silent, and a refused file changes nothing.
"""

import base64
import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urlsplit

try:
    from . import ed25519, evidence_briefing
    from . import egress as _egress
    from .database import get_db
except ImportError:  # top-level import mode
    import ed25519
    import egress as _egress
    import evidence_briefing
    from database import get_db

PREFIX = "ILB1"
FORMAT = "inox-library"
FORMAT_VERSION = 1
PUBLISHER = "Inox Hydra"
CONTENT_POLICY = "company-authored"
KINDS = ("form", "pattern", "example")

# Base64 Ed25519 public keys whose signatures this build accepts, by key id.
# The secret halves are kept by the vendor, outside this repository
# (tools/library_bundle.py new-keypair). A different key from the licence's.
PUBLIC_KEYS: Dict[str, str] = {
    # The company's library key, made 2026-10-26 with tools/library_bundle.py
    # new-keypair; the secret half is in the vendor's library-signing folder.
    "inox-library-2026-10": "OXIZaFi/qp05IYvVjICkjmr6F2CK80JMOM7dBH2ZpP8=",
}

DEFAULT_URL = "https://raw.githubusercontent.com/dharmik136/inox-hydra-intelligence/main/library_v1.ilb"
URL_ENV = "INOX_LIBRARY_URL"
# Exact host names, never a suffix: "evil-githubusercontent.com" ends with the
# same letters as the real host. The host of INOX_LIBRARY_URL is accepted as
# well, since setting a variable already needs the machine.
ALLOWED_HOSTS = ("raw.githubusercontent.com", "github.com", "objects.githubusercontent.com")
TIMEOUT_SECONDS = 10.0
MAX_BYTES = 2 * 1024 * 1024
MAX_ENTRIES = 1000
MAX_TAGS = 12
ETAG_KEY = "library_etag"
SOURCE_KEY = "library_source"
USER_AGENT = f"InoxHydra-Library/{FORMAT_VERSION}"

CONTAINS = ("Forms, patterns and examples the Inox Hydra team wrote, each tagged with the topics it suits: no post "
            "copied from LinkedIn, no person's name, no figure.")
SENDS = ("Fetching asks one fixed address for one file. The request carries that address, a User-Agent naming this "
         "channel, and the tag of the copy already held, and nothing of yours: no post, ask, mark, name or setting.")

_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")


class LibraryRefused(ValueError):
    """A bundle the studio will not keep, with the reason to show."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encode(content: Dict[str, Any], signer: Callable[[bytes], bytes]) -> str:
    """The bundle text for some content, signed by signer(message) -> signature (the vendor's tool)."""
    body = _b64url(json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signed = f"{PREFIX}.{body}".encode("ascii")
    return f"{PREFIX}.{body}.{_b64url(signer(signed))}"


def verify(text: Any, keys: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    The content of a bundle whose signature verifies, or LibraryRefused.

    The key that verifies it must be the one its content names, so a bundle
    cannot claim one key and be signed by another listed one.
    """
    keys = PUBLIC_KEYS if keys is None else keys
    raw = str(text or "").strip()
    parts = raw.split(".")
    if len(parts) != 3 or parts[0] != PREFIX:
        raise LibraryRefused("This is not a signed Inox library file.")
    try:
        signature = _unb64url(parts[2])
    except (ValueError, TypeError):
        raise LibraryRefused("The file's signature cannot be read.") from None
    message = f"{PREFIX}.{parts[1]}".encode("ascii")
    verified_by = None
    for key_id, public in keys.items():
        try:
            public_bytes = base64.b64decode(public)
        except (ValueError, TypeError):
            continue
        if ed25519.verify(public_bytes, message, signature):
            verified_by = key_id
            break
    if verified_by is None:
        raise LibraryRefused("The file's signature does not match any library key this studio holds, so it was "
                             "not kept. It may have been changed after it was signed.")
    try:
        content = json.loads(_unb64url(parts[1]).decode("utf-8"))
    except (ValueError, TypeError):
        raise LibraryRefused("The signed part of the file cannot be read.") from None
    if not isinstance(content, dict) or content.get("key_id") != verified_by:
        raise LibraryRefused("The file names a different key from the one that signed it.")
    return content


def validate(content: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    The entries, checked against the content policy, or LibraryRefused. One
    bad entry refuses the file: a library is published whole.
    """
    if content.get("format") != FORMAT or content.get("format_version") != FORMAT_VERSION:
        raise LibraryRefused("This library file is in a format this studio does not read.")
    if content.get("publisher") != PUBLISHER or content.get("content_policy") != CONTENT_POLICY:
        raise LibraryRefused("This library file is not the company's own material, so it was not kept.")
    for field in ("version", "signed_at", "key_id"):
        if not isinstance(content.get(field), str) or not content[field].strip():
            raise LibraryRefused(f"This library file has no {field.replace('_', ' ')}.")
    try:
        date.fromisoformat(content["signed_at"])
    except ValueError:
        raise LibraryRefused("This library file's signing date cannot be read.") from None
    entries = content.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > MAX_ENTRIES:
        raise LibraryRefused(f"A library holds between 1 and {MAX_ENTRIES} entries.")
    seen = set()
    cleaned = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise LibraryRefused("An entry is not the shape a library entry has.")
        entry_id, kind = entry.get("id"), entry.get("kind")
        title, text, tags = entry.get("title"), entry.get("text"), entry.get("tags")
        if not isinstance(entry_id, str) or not _ID.match(entry_id) or entry_id in seen:
            raise LibraryRefused(f"An entry's id is missing, malformed or repeated: {str(entry_id)[:40]!r}.")
        seen.add(entry_id)
        if kind not in KINDS:
            raise LibraryRefused(f"Entry {entry_id} is a {kind!r}; a library holds forms, patterns and examples.")
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise LibraryRefused(f"Entry {entry_id} has no title, or one over 200 characters.")
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise LibraryRefused(f"Entry {entry_id} has no text, or over 2,000 characters.")
        if not isinstance(tags, list) or len(tags) > MAX_TAGS or not all(isinstance(t, str) and 0 < len(t) <= 40 for t in tags):
            raise LibraryRefused(f"Entry {entry_id} carries more than {MAX_TAGS} tags, or a tag that is not a short word.")
        if entry.get("author") != PUBLISHER:
            raise LibraryRefused(f"Entry {entry_id} names an author other than the company.")
        if "linkedin.com/" in (text + title).lower() or "lnkd.in/" in (text + title).lower():
            raise LibraryRefused(f"Entry {entry_id} links to LinkedIn. A library entry is the company's own words, "
                                 "never a pointer to someone's post.")
        dash = chr(0x2014)
        cleaned.append({"entry_id": entry_id, "kind": kind, "title": title.strip().replace(dash, ", "),
                        "text": text.strip().replace(dash, ", "), "tags": [t.strip().casefold() for t in tags]})
    return cleaned


def _setting(conn, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _put_setting(conn, key: str, value: Optional[str]) -> None:
    if value is None:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        return
    conn.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP", (key, value))


def store(content: Dict[str, Any], entries: List[Dict[str, Any]], source: str, etag: Optional[str] = None) -> int:
    """
    Replaces the library with this bundle, in one transaction, and only then
    records the tag of the copy held: a tag saved before a failed write would
    tell every later fetch it already had the file.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("DELETE FROM library_entries")
            for entry in entries:
                conn.execute(
                    "INSERT INTO library_entries (entry_id, kind, title, text, tags_json, author, bundle_version, "
                    "signed_at, key_id, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (entry["entry_id"], entry["kind"], entry["title"], entry["text"], json.dumps(entry["tags"]),
                     PUBLISHER, content["version"], content["signed_at"], content["key_id"], now))
            _put_setting(conn, SOURCE_KEY, source)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        with conn:
            _put_setting(conn, ETAG_KEY, etag)
    finally:
        conn.close()
    return len(entries)


def configured_url() -> str:
    return (os.environ.get(URL_ENV) or "").strip() or DEFAULT_URL


def allowed_host(hostname: Optional[str]) -> bool:
    if not hostname:
        return False
    candidate = hostname.strip().lower()
    if candidate in ALLOWED_HOSTS:
        return True
    configured = urlsplit(configured_url()).hostname
    return bool(configured) and candidate == configured.strip().lower()


def fetch() -> Dict[str, Any]:
    """
    The creator pressed Fetch: one conditional GET for the library file, then
    verify, check and keep it, or say in words why not. Nothing about the
    creator travels with the request.
    """
    target = configured_url()
    parts = urlsplit(target)
    if parts.scheme != "https":
        return {"status": "refused", "message": "The library is fetched over https only."}
    if not allowed_host(parts.hostname):
        return {"status": "refused", "message": f"The library is not fetched from {parts.hostname}."}
    conn = get_db()
    try:
        held = conn.execute("SELECT COUNT(*) FROM library_entries").fetchone()[0]
        etag = _setting(conn, ETAG_KEY) if held else None
    finally:
        conn.close()
    headers = {"User-Agent": USER_AGENT, "Accept": "text/plain"}
    if etag:
        headers["If-None-Match"] = etag
    request = urllib.request.Request(target, headers=headers, method="GET")
    try:
        # Refuses rather than connecting when this category is off. See egress.py.
        _egress.require(target, "library")
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(MAX_BYTES + 1)
            new_etag = response.headers.get("ETag")
    except _egress.EgressRefused as refused:
        return {"status": "refused", "message": str(refused)}
    except urllib.error.HTTPError as error:
        if error.code == 304:
            return {"status": "up_to_date", "message": "The library you hold is the current one. Nothing was "
                                                       "transferred but the request."}
        if error.code == 404:
            return {"status": "error", "message": "The library file was not found at its address. It may not be "
                                                  "published yet."}
        return {"status": "error", "message": f"The library's host answered HTTP {error.code}. Nothing was changed."}
    except (urllib.error.URLError, OSError) as error:
        return {"status": "error", "message": f"The library could not be reached: {_egress.redact(error)}. "
                                              "Nothing was changed."}
    if len(body) > MAX_BYTES:
        return {"status": "refused", "message": "That file is far larger than a library is. Nothing was kept."}
    try:
        content = verify(body.decode("ascii", errors="replace"))
        entries = validate(content)
    except LibraryRefused as refused:
        return {"status": "refused", "message": str(refused)}
    count = store(content, entries, source=f"fetched from {parts.hostname}", etag=new_etag)
    return {"status": "updated", "version": content["version"], "signed_at": content["signed_at"], "entries": count,
            "message": f"Kept the Inox library, bundle {content['version']} signed {content['signed_at']}: {count} entries."}


def import_text(text: Any) -> Dict[str, Any]:
    """A library file chosen by hand, for a machine that never connects. Verified exactly as a fetched one."""
    if len(str(text or "")) > MAX_BYTES:
        return {"status": "refused", "message": "That file is far larger than a library is. Nothing was kept."}
    try:
        content = verify(text)
        entries = validate(content)
    except LibraryRefused as refused:
        return {"status": "refused", "message": str(refused)}
    count = store(content, entries, source="imported from a file", etag=None)
    return {"status": "updated", "version": content["version"], "signed_at": content["signed_at"], "entries": count,
            "message": f"Kept the Inox library, bundle {content['version']} signed {content['signed_at']}: {count} entries."}


def status() -> Dict[str, Any]:
    """What the library holds, where it came from, what it contains and what fetching it sends."""
    conn = get_db()
    try:
        row = conn.execute("SELECT COUNT(*), MAX(bundle_version), MAX(signed_at), MAX(key_id), MAX(fetched_at) "
                           "FROM library_entries").fetchone()
        source = _setting(conn, SOURCE_KEY)
    finally:
        conn.close()
    return {"entries": row[0], "version": row[1], "signed_at": row[2], "key_id": row[3], "fetched_at": row[4],
            "source": source or "not fetched yet", "address": configured_url(), "contains": CONTAINS, "sends": SENDS,
            "keys": sorted(PUBLIC_KEYS)}


# ---------------------------------------------------------------------------
# Matching, on this machine
# ---------------------------------------------------------------------------

def match_card(conn, day: date, seed: int, avoid: Optional[Set[str]] = None) -> Optional[Dict[str, Any]]:
    """
    The open slot's card from the library: an entry whose tags and title go
    under one of the creator's own recurring words, drawn by the same rule as
    the other slots, or None when the library is empty or matches nothing.
    """
    try:
        from . import record_cards
    except ImportError:
        import record_cards
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM library_entries")]
    except sqlite3.OperationalError:
        return None
    if not rows:
        return None
    texts = [r[0] for r in conn.execute("SELECT text FROM own_posts WHERE text IS NOT NULL")]
    vocabulary = evidence_briefing.derive_topic_vocabulary(texts)
    if not vocabulary:
        return None
    counts: Dict[str, int] = {}
    for text in texts:
        label = evidence_briefing.classify_post_topic(text, vocabulary)
        counts[label] = counts.get(label, 0) + 1
    total = max(1, len(texts))
    items = []
    for row in rows:
        words = " ".join(json.loads(row["tags_json"] or "[]")) + " " + row["title"]
        topic = evidence_briefing.classify_post_topic(words, vocabulary)
        if topic == evidence_briefing.OTHER_TOPIC:
            continue
        items.append((f"lib:{row['entry_id']}", (row, topic), counts.get(topic, 1) / total))
    drawn = record_cards._draw(items, record_cards._history(conn, day), day, seed + 5, avoid, lambda item: item[1])
    if not drawn:
        return None
    card_id, (row, topic) = drawn
    count = counts.get(topic, 0)
    rule = ("matched on this computer: the entry's tags and title read through your own recurring words; "
            "nothing of yours was sent to fetch the library")
    payload = {
        "title": row["title"],
        "badge": "curated, not measured for you",
        "excerpt": record_cards._excerpt(row["text"], 200),
        "date": None,
        "url": None,
        "figures": [],
        "figure_sentence": "",
        "because": (f"Because {count} of your posts go under {topic}, and this {row['kind']} from the Inox library is "
                    f"tagged for it · rule: From the Inox library"),
        "source_sentence": (f"from the Inox library, bundle {row['bundle_version']} signed {row['signed_at']}; curated, "
                            "not measured for you"),
        "method_sentence": rule,
        "draft_text": row["text"],
        "topic": topic,
        "block_label": "From the Inox library",
    }
    card = record_cards._card(card_id, 5, "library", "library", "curated", rule, payload,
                              [{"table": "library_entries", "id": row["entry_id"]}])
    card["provenance"]["bundle"] = {"version": row["bundle_version"], "signed_at": row["signed_at"], "key_id": row["key_id"]}
    return card
