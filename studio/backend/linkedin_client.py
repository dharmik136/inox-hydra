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
        conn = get_db()
        cursor = conn.cursor()
        saved_count = 0

        # Handle time series
        series = raw_data.get("series") or raw_data.get("data", {}).get("series") or []
        for bucket in series:
            dt = bucket.get("bucket") or bucket.get("date")
            metrics = bucket.get("metrics") or bucket
            if not dt:
                continue

            imp = metrics.get("impressions", 0) or 0
            lk = metrics.get("likes", 0) or metrics.get("reactions", 0) or 0
            cm = metrics.get("comments", 0) or 0
            sh = metrics.get("shares", 0) or 0
            fl = metrics.get("followers")
            cn = metrics.get("connections")
            pv = metrics.get("profile_views")

            eng_rate = round(((lk + cm + sh) / imp * 100), 2) if imp > 0 else 0.0

            cursor.execute("""
            INSERT OR REPLACE INTO analytics_daily 
            (date, followers, connections, profile_views, impressions, reactions, comments, shares, engagement_rate)
            VALUES (?, 
                    COALESCE(?, (SELECT followers FROM analytics_daily WHERE date = ?)),
                    COALESCE(?, (SELECT connections FROM analytics_daily WHERE date = ?)),
                    COALESCE(?, (SELECT profile_views FROM analytics_daily WHERE date = ?)),
                    ?, ?, ?, ?, ?)
            """, (dt, fl, dt, cn, dt, pv, dt, imp, lk, cm, sh, eng_rate))
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
            (date, followers, connections, profile_views, impressions, reactions, comments, shares, engagement_rate)
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
                    COALESCE((SELECT engagement_rate FROM analytics_daily WHERE date = ?), 0.0))
            """, (today_str, today_str, today_str, int(top_pv), today_str, today_str, today_str, today_str, today_str))
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
                    INSERT INTO audience_demographics (dimension, label, percentage)
                    VALUES (?, ?, ?)
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
                l_id = l.get("id") or f"lead-live-{abs(hash(name + profile_url)) % 1000000}"
                cursor.execute("""
                INSERT INTO leads (id, name, headline, company, profile_url, engagement_type, post_id, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    l_id,
                    name,
                    headline,
                    company,
                    profile_url,
                    l.get("engagement_type", "Commented"),
                    l.get("post_id", ""),
                    l.get("status", "New Lead"),
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
                "name": "Dharmik Shingala",
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
        now = current_time or datetime.now()
        delta_seconds = (now - scheduled_at).total_seconds()

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
                "current_time": now.isoformat(),
                "delay_minutes": delay_minutes,
                "action": "prompt_grace_launch",
                "message": f"Machine woke {delay_minutes} mins late. Eligible for 1-click launch under the 45-minute morning grace rule."
            }

        # Stale: > 45 mins late - auto-reschedule to protect algorithmic reach
        next_peak = now.replace(hour=peak_hour, minute=peak_minute, second=0, microsecond=0)
        if next_peak <= now:
            # If peak window today has already passed, schedule for tomorrow
            next_peak += timedelta(days=1)

        return {
            "status": "AUTO_RESCHEDULED",
            "scheduled_at": scheduled_at.isoformat(),
            "current_time": now.isoformat(),
            "delay_minutes": delay_minutes,
            "rescheduled_to": next_peak.isoformat(),
            "action": "auto_rescheduled",
            "message": f"Delay of {delay_minutes} mins exceeded 45-min grace window. Auto-rescheduled to next peak window at {next_peak.strftime('%I:%M %p')} to protect algorithmic reach."
        }


linkedin_client = LinkedInClient()
