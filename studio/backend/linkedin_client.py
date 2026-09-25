"""
LinkedIn Passive Session Bridge & Ingestion Engine
===================================================
Manages authenticated session tokens (li_at, JSESSIONID) captured passively by the Chrome Extension.
Handles creator profile verification, telemetry ingestion, and commenter CRM populating.

Anti-Detection Safeguards:
- 0 synthetic automated request spam.
- Only executes lightweight read verification against /voyager/api/me.
- Ingestion is passive: receives structured payloads from browser content script observations.
"""

import json
import sqlite3
import os
import threading
import requests

try:  # package import
    from . import egress as _egress
except ImportError:  # flat import, when the backend is run as a script
    import egress as _egress

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
try:
    from .database import get_db
    from .vault import encrypt_token, decrypt_token
    from .rate_limiter import rate_limiter
except ImportError:
    from database import get_db
    from vault import encrypt_token, decrypt_token
    from rate_limiter import rate_limiter


# -------------------------------------------------------------
# The passive-observer boundary
# -------------------------------------------------------------
# This product observes pages the creator's own browser already loaded. It does
# not fetch on their behalf. That distinction is the product's stated design and
# it is worth enforcing in code rather than in a document, because three call
# sites in this file had already crossed it: a GET /me fired from a webRequest
# listener, a second GET behind the stats sync, and a live POST to
# contentcreation/normShares.
#
# Every outbound request to LinkedIn from this process now passes through
# egress_guard(). It refuses by default. Setting INOX_ALLOW_LINKEDIN_EGRESS=1
# opts back in deliberately, which is a decision someone has to make on purpose
# rather than one that happens by accident.
#
# egress_performed is what a test asserts against. Zero is the contract.
EGRESS_ENV_FLAG = "INOX_ALLOW_LINKEDIN_EGRESS"

# The same dict the shared module counts into, not a copy. Rebinding this to a
# fresh dict would detach it from the chokepoint and from the tests that write
# to it directly.
egress_stats = _egress.stats_for("linkedin")


def _stable_key(identity):
    """Deterministic id fragment. See crm.stable_lead_key for the reasoning."""
    import hashlib

    return hashlib.sha256((identity or "").encode("utf-8")).hexdigest()[:12]


def egress_allowed() -> bool:
    """True only when the operator has explicitly opted into active requests."""
    return _egress.allowed("linkedin")


def egress_guard(endpoint: str) -> Optional[Dict[str, Any]]:
    """
    Call before any outbound request to LinkedIn.

    Returns None when the request may proceed. Returns a result dict describing
    the refusal when it may not, which callers return to their own caller
    unchanged so the refusal is visible rather than silent.

    Delegates to egress.guard(). This used to be the only guard in the backend,
    and the six modules that did not have one reached nine hosts unchecked. It
    keeps its own name and its own env flag because the reasoning that put it
    here is specific to LinkedIn: the studio observes pages you open and does
    not request data on your behalf.
    """
    refusal = _egress.guard(endpoint, category="linkedin")
    if refusal is None:
        return None
    # The historical wording, which names the boundary rather than the flag.
    refusal["message"] = (
        "This studio observes LinkedIn pages you open yourself and does not "
        "request data on your behalf, so the session was not checked. Set "
        f"{EGRESS_ENV_FLAG}=1 to allow active requests."
    )
    return refusal


class CircuitBreaker:
    """
    Safeguards LinkedIn account against rate-limiting and challenge checkpoints.
    Trips open after consecutive 401, 403, or checkpoint responses, preventing
    further network requests during a 300-second cooldown window.
    """
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 300.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.last_failure_time: Optional[datetime] = None
        self.last_trip_reason: str = ""
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        with self._lock:
            if self.state == "CLOSED":
                return True
            if self.state == "OPEN":
                if self.last_failure_time:
                    elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
                    if elapsed >= self.cooldown_seconds:
                        self.state = "HALF_OPEN"
                        return True
                return False
            # In HALF_OPEN, allow probe execution
            return True

    def record_success(self):
        with self._lock:
            self.failure_count = 0
            self.state = "CLOSED"
            self.last_trip_reason = ""

    def record_failure(self, status_code: Optional[int] = None, reason: str = ""):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now(timezone.utc)
            desc = reason or f"HTTP status {status_code}"
            # Immediate trip on explicit security challenges (401, 403, checkpoint)
            if status_code in (401, 403) or "checkpoint" in desc.lower() or "challenge" in desc.lower():
                self.state = "OPEN"
                self.last_trip_reason = f"Security checkpoint / challenge detected ({desc})"
            elif self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                self.last_trip_reason = f"Failure threshold reached: {self.failure_count} consecutive failures ({desc})"

    def trip(self, reason: str = "Manual security trip"):
        with self._lock:
            self.state = "OPEN"
            self.last_failure_time = datetime.now(timezone.utc)
            self.last_trip_reason = reason

    def reset(self):
        with self._lock:
            self.failure_count = 0
            self.state = "CLOSED"
            self.last_failure_time = None
            self.last_trip_reason = ""

    def get_status(self) -> dict:
        with self._lock:
            cooldown_remaining = 0.0
            if self.state == "OPEN" and self.last_failure_time:
                elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
                cooldown_remaining = max(0.0, self.cooldown_seconds - elapsed)
            return {
                "state": self.state,
                "failure_count": self.failure_count,
                "cooldown_remaining_seconds": round(cooldown_remaining, 1),
                "last_trip_reason": self.last_trip_reason,
                "can_execute": self.state != "OPEN" or cooldown_remaining == 0.0
            }


def _pipeline_status(human_status):
    """
    Maps the human facing lead status to the machine one.

    A lead carries two status vocabularies: `status` is what the CRM screen
    shows a person, `lead_status` is what the funnel and conversion rate read.
    Writing one without the other is why a captured lead could never move a
    chart. The mapping is imported rather than duplicated so there is one
    definition of what "Meeting Booked" means.
    """
    try:
        from .leads import LEAD_STATUS_TO_PIPELINE
    except ImportError:
        from leads import LEAD_STATUS_TO_PIPELINE
    return LEAD_STATUS_TO_PIPELINE.get(human_status, "NEW")


class LinkedInClient:
    """
    Client for communicating with LinkedIn internal Voyager endpoints
    using local session tokens (li_at, JSESSIONID).
    """
    def __init__(self):
        self.base_url = "https://www.linkedin.com/voyager/api"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self.circuit_breaker = CircuitBreaker()

    def get_tokens(self) -> dict:
        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings WHERE key IN ('li_at', 'JSESSIONID')")
            rows = dict(cursor.fetchall())
        except Exception:
            rows = {}
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        decrypted = {}
        for k, v in rows.items():
            decrypted[k] = decrypt_token(v) if v else v
        return decrypted

    def is_authenticated(self) -> bool:
        tokens = self.get_tokens()
        return bool(tokens.get("li_at") and tokens.get("JSESSIONID"))

    def save_tokens(self, li_at: str, jsessionid: str):
        enc_li_at = encrypt_token(li_at)
        enc_jsessionid = encrypt_token(jsessionid)
        conn = None
        try:
            conn = get_db()
            with conn:
                cursor = conn.cursor()
                now_iso = datetime.now(timezone.utc).isoformat()
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('li_at', ?)", (enc_li_at,))
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('JSESSIONID', ?)", (enc_jsessionid,))
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('session_status', 'connected')")
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_token_update', ?)", (now_iso,))
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        self.circuit_breaker.reset()
        print("Session tokens encrypted and saved successfully!")

    def build_headers(self, tokens: dict) -> dict:
        jsessionid = tokens.get("JSESSIONID", "")
        csrf_token = jsessionid.strip('"').replace("ajax:", "")
        return {
            "csrf-token": csrf_token,
            "User-Agent": self.user_agent,
            "Accept": "application/vnd.linkedin.normalized+json+2.1",
            "X-Restli-Protocol-Version": "2.0.0"
        }

    def ingest_analytics_payload(self, raw_data: dict) -> dict:
        """
        Ingests Creator Analytics JSON payload (intercepted from browser extension
        or directly queried from Voyager) and stores it in SQLite.
        """
        # A daily row must hold a daily figure.
        #
        # The creator analytics page reports whatever window its range selector
        # is set to. Writing a 28 day total into a row keyed by today's date
        # made every downstream aggregate wrong in a way no later fix could
        # detect, so a positively identified multi-day window is refused here
        # rather than stored.
        #
        # An unknown window is still stored. Refusing it would mean capturing
        # nothing whenever the selector markup changes, and a row labelled
        # "period unknown" is more useful than no row at all.
        DAILY_WINDOWS = {"1d", "1D", "day", "daily"}
        declared_period = raw_data.get("period_label")

        # Check the buckets as well as the envelope. A payload that declared its
        # window only per bucket slipped past a top-level-only check and then had
        # that same multi-day label written onto the row.
        def _mismatched(label):
            return bool(label) and label not in DAILY_WINDOWS

        offending = declared_period if _mismatched(declared_period) else None
        if offending is None:
            for _b in (raw_data.get("series") or raw_data.get("data", {}).get("series") or []):
                if isinstance(_b, dict) and _mismatched(_b.get("period_label")):
                    offending = _b.get("period_label")
                    break

        if offending:
            return {
                "status": "window_mismatch",
                "saved": 0,
                "period_label": offending,
                "message": (
                    f"These figures cover {offending}, not a single day. "
                    f"Storing them as today's numbers would make every total "
                    f"that sums across days wrong."
                ),
            }

        declared_precision = raw_data.get("precision")

        conn = get_db()
        try:
            cursor = conn.cursor()
            saved_count = 0

            # Handle time series
            series = raw_data.get("series") or raw_data.get("data", {}).get("series") or []
            for bucket in series:
                dt = bucket.get("bucket") or bucket.get("date")
                metrics = bucket.get("metrics") or bucket
                if not dt:
                    continue

                # A metric that was not read is None, not zero. Coercing it meant a
                # payload where only the follower card had rendered wrote a zero over
                # the impressions figure captured earlier the same day, stamped
                # 'observed'. None flows into COALESCE below, which keeps what is
                # already stored.
                def _metric(*keys):
                    for k in keys:
                        v = metrics.get(k)
                        if v is not None:
                            return v
                    return None

                imp = _metric("impressions")
                lk = _metric("likes", "reactions")
                cm = _metric("comments")
                sh = _metric("shares")
                fl = metrics.get("followers")
                cn = metrics.get("connections")
                pv = metrics.get("profile_views")

                engaged = sum(v for v in (lk, cm, sh) if v is not None)
                eng_rate = round((engaged / imp * 100), 2) if (imp or 0) > 0 else None
                # An absent window is recorded as "unknown" rather than left
                # NULL. The gate above deliberately lets an undetected period
                # through, on the reasoning that a row labelled period unknown
                # beats no row at all, but it was then stored as NULL, which
                # is indistinguishable from a row nobody ever asked about.
                # Writing the state down is the point of migration 5.
                row_period = bucket.get("period_label") or declared_period or "unknown"
                row_precision = bucket.get("precision") or declared_precision

                cursor.execute("""
                -- INSERT OR REPLACE deletes the old row and writes a new one,
                -- so every column the statement does not name reverts to its
                -- default. This named twelve of fourteen, which silently reset
                -- unique_members_reached to 0 and created_at to now on every
                -- re-sync of a day. The top_pv branch below already carried
                -- reach forward with COALESCE; this one did not, so the two
                -- fought each other and the last writer erased the other's
                -- figure. Measured: a stored reach of 4200 became 0.
                INSERT OR REPLACE INTO analytics_daily
                (date, followers, connections, profile_views, impressions, reactions, comments, shares, engagement_rate, source, period_label, precision, unique_members_reached, created_at)
                VALUES (?, 
                        COALESCE(?, (SELECT followers FROM analytics_daily WHERE date = ?)),
                        COALESCE(?, (SELECT connections FROM analytics_daily WHERE date = ?)),
                        COALESCE(?, (SELECT profile_views FROM analytics_daily WHERE date = ?)),
                        COALESCE(?, (SELECT impressions FROM analytics_daily WHERE date = ?), 0),
                        COALESCE(?, (SELECT reactions FROM analytics_daily WHERE date = ?), 0),
                        COALESCE(?, (SELECT comments FROM analytics_daily WHERE date = ?), 0),
                        COALESCE(?, (SELECT shares FROM analytics_daily WHERE date = ?), 0),
                        COALESCE(?, (SELECT engagement_rate FROM analytics_daily WHERE date = ?), 0.0),
                        'observed', ?, ?,
                        COALESCE((SELECT unique_members_reached FROM analytics_daily WHERE date = ?), 0),
                        COALESCE((SELECT created_at FROM analytics_daily WHERE date = ?), CURRENT_TIMESTAMP))
                """, (dt, fl, dt, cn, dt, pv, dt,
                      imp, dt, lk, dt, cm, dt, sh, dt, eng_rate, dt,
                      row_period, row_precision, dt, dt))
                # The rate is derived from the row, never from the payload.
                #
                # `engaged` above sums only the metrics THIS payload carried,
                # and COALESCE cannot protect against it: the value is non
                # NULL whenever impressions are present, so it always wins.
                # An afternoon sync where only the reactions card had rendered
                # therefore divided a partial numerator by the new impressions
                # and overwrote a correct figure. An impressions only sync
                # wrote 0.0 while the reaction columns still held real numbers.
                #
                # Measured: 1000/50/10/5 gives 6.5. A follow up carrying only
                # impressions=1100 and likes=55 stored 5.0 against columns that
                # implied 6.36, and an impressions only follow up stored 0.0
                # against columns implying 5.83.
                #
                # Recomputing from the merged row makes the column and its
                # inputs agree by construction, whatever a payload omitted.
                cursor.execute("""
                UPDATE analytics_daily
                SET engagement_rate = CASE
                        WHEN COALESCE(impressions, 0) > 0
                        THEN ROUND(
                            (COALESCE(reactions, 0) + COALESCE(comments, 0)
                             + COALESCE(shares, 0)) * 100.0
                            / impressions, 2)
                        ELSE 0.0
                    END
                WHERE date = ?
                """, (dt,))
                # Same derivation as the series branch above: the stored row
                # is the source of truth for its own rate.
                cursor.execute("""
                UPDATE analytics_daily
                SET engagement_rate = CASE
                        WHEN COALESCE(impressions, 0) > 0
                        THEN ROUND(
                            (COALESCE(reactions, 0) + COALESCE(comments, 0)
                             + COALESCE(shares, 0)) * 100.0
                            / impressions, 2)
                        ELSE 0.0
                    END
                WHERE date = ?
                """, (dt,))
                saved_count += 1

            # Handle top-level profile views from identity profile responses
            top_pv = raw_data.get("profile_views")
            if top_pv is not None and not series:
                today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                # followers and connections carry forward from the most recent day
                # when today has no row yet. Selecting them bare wrote NULL, and
                # get_kpis subtracts one day's follower count from another, so a
                # profile views only payload took the whole dashboard down with a
                # TypeError on None.
                cursor.execute("""
                INSERT OR REPLACE INTO analytics_daily 
                (date, followers, connections, profile_views, impressions, reactions, comments, shares, engagement_rate, source, period_label, precision, unique_members_reached)
                VALUES (?, 
                        COALESCE((SELECT followers FROM analytics_daily WHERE date = ?),
                                 (SELECT followers FROM analytics_daily WHERE followers IS NOT NULL ORDER BY date DESC LIMIT 1), 0),
                        COALESCE((SELECT connections FROM analytics_daily WHERE date = ?),
                                 (SELECT connections FROM analytics_daily WHERE connections IS NOT NULL ORDER BY date DESC LIMIT 1), 0),
                        ?,
                        COALESCE((SELECT impressions FROM analytics_daily WHERE date = ?), 0),
                        COALESCE((SELECT reactions FROM analytics_daily WHERE date = ?), 0),
                        COALESCE((SELECT comments FROM analytics_daily WHERE date = ?), 0),
                        COALESCE((SELECT shares FROM analytics_daily WHERE date = ?), 0),
                        COALESCE((SELECT engagement_rate FROM analytics_daily WHERE date = ?), 0.0),
                        'observed',
                        (SELECT period_label FROM analytics_daily WHERE date = ?),
                        (SELECT precision FROM analytics_daily WHERE date = ?),
                        COALESCE((SELECT unique_members_reached FROM analytics_daily WHERE date = ?), 0))
                """, (today_str, today_str, today_str, int(top_pv), today_str, today_str,
                      today_str, today_str, today_str, today_str, today_str, today_str))
                saved_count += 1

            # Handle demographics and viewer seniority if present
            demographics = list(raw_data.get("demographics") or [])
            seniority = raw_data.get("viewer_seniority") or raw_data.get("seniority") or []
            if seniority and isinstance(seniority, list):
                for s in seniority:
                    if isinstance(s, dict):
                        demographics.append({
                            "dimension": "seniority",
                            "label": s.get("label") or s.get("title") or s.get("level", "Senior"),
                            "percentage": float(s.get("percentage") or s.get("pct", 0.0))
                        })

            if demographics:
                for d in demographics:
                    dim = d.get("dimension")
                    lbl = d.get("label")
                    pct = d.get("percentage", 0.0)
                    if dim and lbl:
                        cursor.execute("DELETE FROM audience_demographics WHERE dimension = ? AND label = ?", (dim, lbl))
                        cursor.execute("""
                        INSERT INTO audience_demographics (dimension, label, percentage, source)
                        VALUES (?, ?, ?, 'observed')
                        """, (dim, lbl, pct))

            # Handle live posts updates from LinkedIn feed (updatesV2 or elements)
            posts = raw_data.get("posts") or raw_data.get("feed_updates") or []
            if not posts and isinstance(raw_data.get("elements"), list):
                posts = raw_data.get("elements", [])
            posts_updated = 0
            for p in posts:
                p_id = p.get("id") or p.get("urn")
                if not p_id:
                    continue
                cursor.execute("""
                INSERT INTO posts (id, content, impressions, reactions, comments, shares, published_at, status)
                VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), 'published')
                ON CONFLICT(id) DO UPDATE SET
                    impressions = COALESCE(excluded.impressions, posts.impressions),
                    reactions = COALESCE(excluded.reactions, posts.reactions),
                    comments = COALESCE(excluded.comments, posts.comments),
                    shares = COALESCE(excluded.shares, posts.shares)
                """, (
                    p_id,
                    p.get("content", ""),
                    p.get("impressions", 0),
                    p.get("reactions", 0),
                    p.get("comments", 0),
                    p.get("shares", 0),
                    p.get("published_at")
                ))
                posts_updated += 1

            # Handle live leads & commenters captured from LinkedIn
            leads = raw_data.get("leads") or []
            leads_added = 0
            leads_updated = 0
            for l in leads:
                name = (l.get("name") or "").strip()
                if not name:
                    continue
                profile_url = (l.get("profile_url") or "").strip()
                headline = (l.get("headline") or "").strip()
                company = (l.get("company") or "").strip()
                notes = l.get("notes") or "Captured live from LinkedIn engagement"

                # Deduplicate by profile_url or exact name + headline
                existing_id = None
                if profile_url:
                    cursor.execute("SELECT id FROM leads WHERE profile_url = ?", (profile_url,))
                    row = cursor.fetchone()
                    if row:
                        existing_id = row[0]
                if not existing_id:
                    cursor.execute("SELECT id FROM leads WHERE name = ? AND headline = ?", (name, headline))
                    row = cursor.fetchone()
                    if row:
                        existing_id = row[0]

                if existing_id:
                    cursor.execute("UPDATE leads SET engagement_type = ?, notes = ? WHERE id = ?", (
                        l.get("engagement_type", "Commented"),
                        notes,
                        existing_id
                    ))
                    leads_updated += 1
                else:
                    l_id = l.get("id") or f"lead-live-{_stable_key(name + profile_url)}"
                    cursor.execute("""
                    INSERT INTO leads (id, name, headline, company, profile_url, engagement_type, post_id, status, lead_status, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        l_id,
                        name,
                        headline,
                        company,
                        profile_url,
                        l.get("engagement_type", "Commented"),
                        l.get("post_id", ""),
                        l.get("status", "New Lead"),
                        # The machine vocabulary, which every analytic reads.
                        # Written from the same mapping leads.py uses rather
                        # than a second copy of it, so the two cannot drift.
                        _pipeline_status(l.get("status", "New Lead")),
                        notes
                    ))
                    leads_added += 1

            conn.commit()
            conn.close()
            return {
                "status": "success",
                "buckets_ingested": saved_count,
                "posts_updated": posts_updated,
                "leads_added": leads_added,
                "leads_updated": leads_updated
            }
        finally:
            conn.close()

    def sync_live_profile_and_stats(self, mock: bool = False, enforce_rate_limit: bool = False) -> dict:
        """
        Queries LinkedIn's Voyager API using stored session cookies (li_at, JSESSIONID)
        to synchronize the creator's real profile name, headline, and recent post metrics.
        Supports instant offline mock/sandbox execution for testing and local development.
        """
        tokens = self.get_tokens()
        li_at = tokens.get("li_at", "")
        jsessionid = tokens.get("JSESSIONID", "")
        if not li_at or not jsessionid:
            return {"status": "skipped", "message": "No tokens stored in settings"}

        if enforce_rate_limit and not mock:
            if not rate_limiter.consume(1.0):
                wait_s = rate_limiter.wait_time_seconds(1.0)
                return {
                    "status": "rate_limited",
                    "message": f"Gaussian rate limiter active. Must wait {wait_s}s before next Voyager query.",
                    "wait_time_seconds": wait_s,
                    "diagnostics": rate_limiter.get_diagnostics()
                }

        # Offline / Sandbox Mock Fast-Path
        if mock or li_at.startswith(("mock_", "sandbox_", "test_")):
            now_iso = datetime.now(timezone.utc).isoformat()
            mock_profile = {
                "name": "Mock Creator",
                "headline": "Enterprise Systems Architect & Content Strategist",
                "vanity": "dharmik-shingala",
                "status": "authenticated"
            }
            conn = get_db()
            try:
                with conn:
                    cur = conn.cursor()
                    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('user_name', ?)", (mock_profile["name"],))
                    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('user_headline', ?)", (mock_profile["headline"],))
                    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('user_vanity', ?)", (mock_profile["vanity"],))
                    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_sync', ?)", (now_iso,))
            finally:
                conn.close()
            return {
                "status": "success",
                "mode": "sandbox_mock",
                "profile": mock_profile,
                "synced_at": now_iso
            }

        if not mock and not self.circuit_breaker.can_execute():
            cb_status = self.circuit_breaker.get_status()
            return {
                "status": "error",
                "message": f"Circuit breaker is OPEN. Calls paused for {cb_status['cooldown_remaining_seconds']}s.",
                "circuit_breaker": cb_status
            }

        refusal = egress_guard("voyager/api/me (profile sync)")
        if refusal is not None:
            return refusal

        headers = self.build_headers(tokens)
        cookies = {"li_at": li_at, "JSESSIONID": jsessionid}
        results = {"profile": None, "synced_at": datetime.now(timezone.utc).isoformat()}

        try:
            # Fetch authenticated user info
            res = requests.get(
                f"{self.base_url}/me",
                headers=headers,
                cookies=cookies,
                timeout=6
            )
            if res.status_code == 200:
                self.circuit_breaker.record_success()
                data = res.json()
                first = data.get("firstName", {}).get("localized", {}).get("en_US", "") or ""
                last = data.get("lastName", {}).get("localized", {}).get("en_US", "") or ""
                headline = data.get("headline", {}).get("localized", {}).get("en_US", "") or ""
                vanity = data.get("publicIdentifier", "") or ""
                full_name = f"{first} {last}".strip()

                conn = get_db()
                try:
                    with conn:
                        cur = conn.cursor()
                        if full_name:
                            cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('user_name', ?)", (full_name,))
                        if headline:
                            cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('user_headline', ?)", (headline,))
                        if vanity:
                            cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('user_vanity', ?)", (vanity,))
                        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_sync', ?)", (datetime.now(timezone.utc).isoformat(),))
                finally:
                    conn.close()

                results["profile"] = {
                    "name": full_name,
                    "headline": headline,
                    "vanity": vanity,
                    "status": "authenticated"
                }
            else:
                self.circuit_breaker.record_failure(status_code=res.status_code, reason=res.text[:100])
                results["profile_status"] = f"HTTP {res.status_code}"
        except Exception as err:
            self.circuit_breaker.record_failure(reason=str(err))
            results["error"] = str(err)

        return results

    def check_session_health(self, mock: bool = False) -> dict:
        """
        Lightweight health check against LinkedIn Voyager /voyager/api/me.
        Protected by the Circuit Breaker to prevent brute-force requests if challenged.
        """
        tokens = self.get_tokens()
        li_at = tokens.get("li_at", "")
        jsessionid = tokens.get("JSESSIONID", "")

        if not li_at or not jsessionid:
            return {
                "status": "unauthenticated",
                "healthy": False,
                "message": "No session tokens configured in vault.",
                "circuit_breaker": self.circuit_breaker.get_status()
            }

        if mock or li_at.startswith(("mock_", "sandbox_", "test_")):
            return {
                "status": "healthy",
                "healthy": True,
                "mode": "sandbox_mock",
                "circuit_breaker": self.circuit_breaker.get_status()
            }

        if not self.circuit_breaker.can_execute():
            cb_status = self.circuit_breaker.get_status()
            return {
                "status": "circuit_open",
                "healthy": False,
                "message": f"Circuit breaker is OPEN. Calls paused for {cb_status['cooldown_remaining_seconds']}s.",
                "circuit_breaker": cb_status
            }

        refusal = egress_guard("voyager/api/me")
        if refusal is not None:
            return refusal

        headers = self.build_headers(tokens)
        cookies = {"li_at": li_at, "JSESSIONID": jsessionid}

        try:
            res = requests.get(
                f"{self.base_url}/me",
                headers=headers,
                cookies=cookies,
                timeout=5
            )
            if res.status_code == 200:
                self.circuit_breaker.record_success()
                conn = get_db()
                try:
                    with conn:
                        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('session_status', 'connected')")
                finally:
                    conn.close()
                return {
                    "status": "healthy",
                    "healthy": True,
                    "http_status": 200,
                    "circuit_breaker": self.circuit_breaker.get_status()
                }
            elif res.status_code in (401, 403):
                self.circuit_breaker.record_failure(status_code=res.status_code, reason=res.text[:100])
                conn = get_db()
                try:
                    with conn:
                        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('session_status', 'challenged')")
                finally:
                    conn.close()
                return {
                    "status": "unauthorized",
                    "healthy": False,
                    "http_status": res.status_code,
                    "message": "Session challenged or expired. Extension recapture required.",
                    "circuit_breaker": self.circuit_breaker.get_status()
                }
            else:
                self.circuit_breaker.record_failure(status_code=res.status_code, reason=res.text[:100])
                return {
                    "status": "unexpected_status",
                    "healthy": False,
                    "http_status": res.status_code,
                    "circuit_breaker": self.circuit_breaker.get_status()
                }
        except Exception as e:
            self.circuit_breaker.record_failure(reason=str(e))
            return {
                "status": "error",
                "healthy": False,
                "error": str(e),
                "circuit_breaker": self.circuit_breaker.get_status()
            }

    def mock_ingestion_verification(self) -> dict:
        """
        Generates and ingests a simulated telemetry payload for local testing
        and contract verification without requiring external LinkedIn credentials.
        """
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        payload = {
            "series": [
                {
                    "date": today_str,
                    "impressions": 520,
                    "likes": 34,
                    "comments": 8,
                    "shares": 3,
                    "followers": 2345,
                    "connections": 2280,
                    "profile_views": 85
                }
            ],
            "demographics": [
                {"dimension": "job_title", "label": "Enterprise Architects", "percentage": 40.0},
                {"dimension": "industry", "label": "Cloud & Distributed Systems", "percentage": 60.0}
            ],
            "posts": [
                {
                    "id": "post-mock-verification",
                    "content": "Decoupled enterprise architectures ensure resilient zero downtime systems.",
                    "impressions": 520,
                    "reactions": 34,
                    "comments": 8,
                    "shares": 3
                }
            ],
            "leads": [
                {
                    "id": "lead-mock-verified",
                    "name": "Vikram Patel",
                    "headline": "Lead Systems Architect @ FinPlatform",
                    "company": "FinPlatform",
                    "profile_url": "https://linkedin.com/in/vikram-patel-mock",
                    "engagement_type": "Commented",
                    "notes": "Interested in event-driven state machines"
                }
            ]
        }
        return self.ingest_analytics_payload(payload)

    def schedule_norm_share(
        self,
        content: str,
        scheduled_at_ms: int,
        author_urn: Optional[str] = None,
        mock: bool = False,
    ) -> dict:
        """
        Pre-stages a post directly into LinkedIn's native cloud scheduler via Voyager API.
        POST https://www.linkedin.com/voyager/api/contentcreation/normShares
        Payload contains scheduledAt (epoch ms) and lifecycleState: SCHEDULED.
        Supports offline mock mode for testing and air-gapped execution.
        """
        tokens = self.get_tokens()
        li_at = tokens.get("li_at", "")
        jsessionid = tokens.get("JSESSIONID", "")

        # Determine member URN
        if not author_urn:
            author_urn = tokens.get("author_urn", "")
            if not author_urn:
                author_urn = "urn:li:person:current_creator"

        if not author_urn.startswith("urn:li:person:"):
            author_urn = f"urn:li:person:{author_urn}"

        payload = {
            "author": author_urn,
            "lifecycleState": "SCHEDULED",
            "visibility": "PUBLIC",
            "commentary": {
                "text": content,
                "attributes": []
            },
            "scheduledAt": scheduled_at_ms
        }

        # Offline / Mock fast-path
        if mock or not li_at or li_at.startswith(("mock_", "sandbox_", "test_")):
            return {
                "status": "success",
                "mode": "mock",
                "scheduled_urn": f"urn:li:share:mock-sched-{scheduled_at_ms}",
                "scheduled_at_ms": scheduled_at_ms,
                "payload": payload,
                "message": "Post pre-staged successfully into LinkedIn native scheduler (Mock Mode)"
            }

        if not self.circuit_breaker.can_execute():
            cb_status = self.circuit_breaker.get_status()
            return {
                "status": "error",
                "message": f"Circuit breaker is OPEN. Scheduling paused for {cb_status['cooldown_remaining_seconds']}s.",
                "circuit_breaker": cb_status
            }

        # Active Voyager call
        csrf_token = jsessionid.strip('"')
        headers = {
            "csrf-token": csrf_token,
            "User-Agent": self.user_agent,
            "Accept": "application/vnd.linkedin.normalized+json+2.1",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json"
        }
        cookies = {"li_at": li_at, "JSESSIONID": jsessionid}

        url = f"{self.base_url}/contentcreation/normShares"
        refusal = egress_guard("voyager/api/contentcreation/normShares")
        if refusal is not None:
            return refusal

        try:
            res = requests.post(url, json=payload, headers=headers, cookies=cookies, timeout=10)
            if res.status_code in (200, 201):
                self.circuit_breaker.record_success()
                data = res.json() if res.text else {}
                return {
                    "status": "success",
                    "mode": "live",
                    "scheduled_urn": data.get("value", {}).get("urn") or data.get("urn", ""),
                    "scheduled_at_ms": scheduled_at_ms,
                    "response": data
                }
            else:
                self.circuit_breaker.record_failure(status_code=res.status_code, reason=res.text[:100])
                return {
                    "status": "error",
                    "http_status": res.status_code,
                    "error": res.text
                }
        except Exception as err:
            self.circuit_breaker.record_failure(reason=str(err))
            return {
                "status": "error",
                "error": str(err)
            }

    @staticmethod
    def evaluate_schedule_recovery(
        scheduled_at: datetime,
        current_time: Optional[datetime] = None,
        peak_hour: int = 13,
        peak_minute: int = 15
    ) -> dict:
        """
        Evaluates local post queue state when waking from system sleep (Sleeping Laptop problem).
        Rules:
        - Delay <= 45 minutes: Apply 45-minute morning grace rule (eligible for 1-click launch).
        - Delay > 45 minutes: Auto-reschedule to the next peak creator window (default: 1:15 PM / 13:15).
        """
        # A scheduled_at that carries an offset and a now that does not cannot
        # be subtracted at all: Python raises rather than guessing, and the
        # route returned a 500. Stored schedule times go through
        # normalize_datetime_to_utc_iso, which always writes an offset, so the
        # common path was exactly the broken one.
        #
        # Both sides are put in UTC before any arithmetic. A naive value is
        # read as local time, which is what astimezone does with one, and is
        # the right reading here: naive datetimes in this studio come off the
        # creator's own clock or their date picker, never off a wire format.
        # scheduler.parse_datetime_flexible reads a naive value as UTC instead,
        # because it parses rows already normalized to UTC and a legacy row
        # without an offset is likeliest to be one of those.
        reference = current_time or datetime.now().astimezone()

        now = reference.astimezone(timezone.utc)
        scheduled_utc = scheduled_at.astimezone(timezone.utc)
        delta_seconds = (now - scheduled_utc).total_seconds()

        # If scheduled time is in future, it is on time
        if delta_seconds <= 0:
            return {
                "status": "ON_SCHEDULE",
                "scheduled_at": scheduled_at.isoformat(),
                "delay_minutes": 0,
                "action": "maintain_schedule",
                "message": "Scheduled time is in the future."
            }

        delay_minutes = int(delta_seconds / 60)

        # Grace Period: <= 45 mins late
        if delay_minutes <= 45:
            return {
                "status": "GRACE_PERIOD_ELIGIBLE",
                "scheduled_at": scheduled_at.isoformat(),
                "current_time": reference.isoformat(),
                "delay_minutes": delay_minutes,
                "action": "prompt_grace_launch",
                "message": f"Machine woke {delay_minutes} mins late. Eligible for 1-click launch under the 45-minute morning grace rule."
            }

        # Stale: > 45 mins late - auto-reschedule to protect algorithmic reach
        #
        # The peak window is built on `reference`, not on the UTC value. "1:15
        # PM" is a claim about the creator's working day, and 13:15 UTC is a
        # quarter to seven in the evening in Mumbai. Computing it in UTC would
        # move the window by the whole offset for every creator outside it.
        next_peak = reference.replace(hour=peak_hour, minute=peak_minute, second=0, microsecond=0)
        if next_peak <= reference:
            # If peak window today has already passed, schedule for tomorrow
            next_peak += timedelta(days=1)

        return {
            "status": "AUTO_RESCHEDULED",
            "scheduled_at": scheduled_at.isoformat(),
            "current_time": reference.isoformat(),
            "delay_minutes": delay_minutes,
            "rescheduled_to": next_peak.isoformat(),
            "action": "auto_rescheduled",
            "message": f"Delay of {delay_minutes} mins exceeded 45-min grace window. Auto-rescheduled to next peak window at {next_peak.strftime('%I:%M %p')} to protect algorithmic reach."
        }


linkedin_client = LinkedInClient()
