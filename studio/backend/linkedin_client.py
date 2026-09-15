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
import requests
from datetime import datetime
try:
    from .database import get_db
except ImportError:
    from database import get_db

class LinkedInClient:
    """
    Client for communicating with LinkedIn internal Voyager endpoints
    using local session tokens (li_at, JSESSIONID).
    """
    def __init__(self):
        self.base_url = "https://www.linkedin.com/voyager/api"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

    def get_tokens(self) -> dict:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings WHERE key IN ('li_at', 'JSESSIONID')")
        rows = dict(cursor.fetchall())
        conn.close()
        return rows

    def is_authenticated(self) -> bool:
        tokens = self.get_tokens()
        return bool(tokens.get("li_at") and tokens.get("JSESSIONID"))

    def save_tokens(self, li_at: str, jsessionid: str):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('li_at', ?)", (li_at,))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('JSESSIONID', ?)", (jsessionid,))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('session_status', 'connected')")
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_token_update', ?)", (datetime.utcnow().isoformat(),))
        conn.commit()
        conn.close()
        print("Session tokens saved successfully!")

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

        # Handle demographics if present
        demographics = raw_data.get("demographics") or []
        if demographics:
            cursor.execute("DELETE FROM audience_demographics")
            for d in demographics:
                cursor.execute("""
                INSERT INTO audience_demographics (dimension, label, percentage)
                VALUES (?, ?, ?)
                """, (d.get("dimension"), d.get("label"), d.get("percentage", 0.0)))

        # Handle live posts updates from LinkedIn feed
        posts = raw_data.get("posts") or []
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
            "leads_added": leads_added
        }

    def sync_live_profile_and_stats(self) -> dict:
        """
        Queries LinkedIn's Voyager API using stored session cookies (li_at, JSESSIONID)
        to synchronize the creator's real profile name, headline, and recent post metrics.
        """
        tokens = self.get_tokens()
        li_at = tokens.get("li_at")
        jsessionid = tokens.get("JSESSIONID")
        if not li_at or not jsessionid:
            return {"status": "skipped", "message": "No tokens stored in settings"}

        headers = self.build_headers(tokens)
        cookies = {"li_at": li_at, "JSESSIONID": jsessionid}
        results = {"profile": None, "synced_at": datetime.utcnow().isoformat()}

        try:
            # Fetch authenticated user info
            res = requests.get(
                f"{self.base_url}/me",
                headers=headers,
                cookies=cookies,
                timeout=6
            )
            if res.status_code == 200:
                data = res.json()
                first = data.get("firstName", {}).get("localized", {}).get("en_US", "") or ""
                last = data.get("lastName", {}).get("localized", {}).get("en_US", "") or ""
                headline = data.get("headline", {}).get("localized", {}).get("en_US", "") or ""
                vanity = data.get("publicIdentifier", "") or ""
                full_name = f"{first} {last}".strip()

                conn = get_db()
                cur = conn.cursor()
                if full_name:
                    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('user_name', ?)", (full_name,))
                if headline:
                    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('user_headline', ?)", (headline,))
                if vanity:
                    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('user_vanity', ?)", (vanity,))
                cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_sync', ?)", (datetime.utcnow().isoformat(),))
                conn.commit()
                conn.close()

                results["profile"] = {
                    "name": full_name,
                    "headline": headline,
                    "vanity": vanity,
                    "status": "authenticated"
                }
            else:
                results["profile_status"] = f"HTTP {res.status_code}"
        except Exception as err:
            results["error"] = str(err)

        return results


linkedin_client = LinkedInClient()
