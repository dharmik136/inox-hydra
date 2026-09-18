"""
Intelligence Sync Engine: Asymmetric CDN Hook & Trend Distribution
===================================================================
Provides asynchronous, zero-egress intelligence synchronization against
the distributed GitHub Releases CDN for viral hook archetypes.

Design Constraints:
1. Asymmetric Distribution: Zero compute/cloud cost ($0.00/mo) via GitHub CDN.
2. HTTP ETag Caching: If-None-Match header ensures 0 bytes payload on 304 Not Modified.
3. Offline Resilience: Built-in high-velocity templates for air-gapped environments.
4. Zero Em-Dashes: The character \\u2014 is strictly prohibited.
"""

import os
import json
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import requests

try:
    from .database import get_db
except ImportError:
    from database import get_db

DEFAULT_CDN_URL = os.environ.get(
    "INTELLIGENCE_CDN_URL",
    "https://raw.githubusercontent.com/dharmik136/inox-hydra-intelligence/main/viral_hooks_v1.json"
)

try:
    from .paths import get_data_dir
except ImportError:
    from paths import get_data_dir

CACHE_ETAG_FILE = os.path.join(get_data_dir(), ".intelligence_etag")

FALLBACK_TEMPLATES = [
    {
        "archetype": "The Contrarian Confession",
        "hook_text": "I spent $2,400 on creator SaaS before realizing this one uncomfortable truth.",
        "velocity_score": 9.4,
        "engagement_multiplier": "3.2x",
        "pacing_style": "1-line hook + blank line + 2-line context",
        "example_post_id": "urn:li:activity:7234981"
    },
    {
        "archetype": "The Architecture Breakdown",
        "hook_text": "90% of software engineers misunderstand local-first architectures. Here is how it actually works:",
        "velocity_score": 9.1,
        "engagement_multiplier": "2.8x",
        "pacing_style": "Contrarian statistic + direct colon promise",
        "example_post_id": "urn:li:activity:7234992"
    },
    {
        "archetype": "The Reverse Engineering Deep Dive",
        "hook_text": "Stop scraping the DOM. Here is how to passively extract LinkedIn creator telemetry without bot risk:",
        "velocity_score": 8.9,
        "engagement_multiplier": "2.6x",
        "pacing_style": "Expository problem + 3-step solution",
        "example_post_id": "urn:li:activity:7235003"
    },
    {
        "archetype": "The Failure-to-Scale Lesson",
        "hook_text": "Our first ingestion worker crashed at 10,000 events. Here is what broke and how we fixed it:",
        "velocity_score": 8.7,
        "engagement_multiplier": "2.4x",
        "pacing_style": "Vulnerable milestone + systemic reflection",
        "example_post_id": "urn:li:activity:7235014"
    },
    {
        "archetype": "The Teardown Benchmark",
        "hook_text": "We benchmarked SQLite WAL vs Postgres connection pool on localhost. The numbers surprised us:",
        "velocity_score": 8.6,
        "engagement_multiplier": "2.3x",
        "pacing_style": "Numerical comparison table + actionable takeaway",
        "example_post_id": "urn:li:activity:7235025"
    },
    {
        "archetype": "The Asymmetric Advantage",
        "hook_text": "Why $0/month infrastructure beats a $500/month cloud cluster for desktop developer tools:",
        "velocity_score": 8.4,
        "engagement_multiplier": "2.1x",
        "pacing_style": "Paradox declaration + economic proof",
        "example_post_id": "urn:li:activity:7235036"
    }
]


class IntelligenceSyncEngine:
    """
    Engine orchestrating asymmetric intelligence synchronization with GitHub CDN.
    Maintains local SQLite viral_templates table and ETag status.
    """

    def __init__(self, cdn_url: Optional[str] = None, etag_file: Optional[str] = None):
        self.cdn_url = cdn_url or DEFAULT_CDN_URL
        self.etag_file = etag_file or CACHE_ETAG_FILE
        self._ensure_offline_seeded()

    def _ensure_offline_seeded(self) -> None:
        """Seeds offline fallback templates if viral_templates table is empty."""
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM viral_templates")
            count = cursor.fetchone()[0]
            if count == 0:
                self.seed_offline_templates(conn)
            conn.close()
        except Exception:
            pass

    def seed_offline_templates(self, conn: Optional[sqlite3.Connection] = None) -> int:
        """Inserts built-in fallback viral templates into the local SQLite store."""
        should_close = False
        if conn is None:
            conn = get_db()
            should_close = True
        try:
            cursor = conn.cursor()
            inserted = 0
            for t in FALLBACK_TEMPLATES:
                cursor.execute("""
                INSERT INTO viral_templates (
                    archetype, hook_text, velocity_score, engagement_multiplier,
                    pacing_style, example_post_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    t["archetype"],
                    t["hook_text"],
                    t["velocity_score"],
                    t["engagement_multiplier"],
                    t["pacing_style"],
                    t["example_post_id"]
                ))
                inserted += 1
            conn.commit()
            return inserted
        finally:
            if should_close:
                conn.close()

    def get_cached_etag(self) -> Optional[str]:
        """Reads cached ETag from local filesystem."""
        if os.path.exists(self.etag_file):
            try:
                with open(self.etag_file, "r", encoding="utf-8") as f:
                    return f.read().strip() or None
            except Exception:
                return None
        return None

    def save_etag(self, etag: str) -> None:
        """Persists ETag string to local cache file."""
        os.makedirs(os.path.dirname(self.etag_file), exist_ok=True)
        with open(self.etag_file, "w", encoding="utf-8") as f:
            f.write(etag.strip())

    def sync(self, force: bool = False, cdn_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes HTTP conditional GET with If-None-Match header.
        - 304 Not Modified: 0 bytes transferred, data already up to date.
        - 200 OK: Ingests new templates and records new ETag.
        - Network Error: Graceful fallback to offline cached templates.
        """
        target_url = cdn_url or self.cdn_url
        etag = None if force else self.get_cached_etag()

        headers = {
            "User-Agent": "PrudentStudio/2.5 (Windows; x64)",
            "Accept": "application/json"
        }
        if etag:
            headers["If-None-Match"] = etag

        try:
            res = requests.get(target_url, headers=headers, timeout=5.0)

            if res.status_code == 304:
                return {
                    "status": "up_to_date",
                    "http_code": 304,
                    "etag": etag,
                    "bytes_transferred": 0,
                    "message": "Zero bytes transferred. Local intelligence cache is fresh."
                }

            if res.status_code == 200:
                payload = res.json()
                categories = payload.get("categories") or payload.get("templates") or []
                new_etag = res.headers.get("ETag") or res.headers.get("etag")

                conn = get_db()
                cursor = conn.cursor()

                # Clean existing and insert fresh synced templates
                cursor.execute("DELETE FROM viral_templates")
                for h in categories:
                    cursor.execute("""
                    INSERT INTO viral_templates (
                        archetype, hook_text, velocity_score, engagement_multiplier,
                        pacing_style, example_post_id, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (
                        h.get("archetype", "General"),
                        h.get("hook_text") or h.get("hook", ""),
                        float(h.get("velocity_score") or h.get("velocity", 8.0)),
                        h.get("engagement_multiplier", "1.0x"),
                        h.get("pacing_style") or h.get("pacing", "Standard"),
                        h.get("example_post_id", "synced-remote")
                    ))
                conn.commit()
                conn.close()

                if new_etag:
                    self.save_etag(new_etag)

                return {
                    "status": "updated",
                    "http_code": 200,
                    "hooks_count": len(categories),
                    "etag": new_etag,
                    "version": payload.get("version", "2026.09.1"),
                    "generated_at": payload.get("generated_at")
                }

            # Unexpected HTTP code
            return {
                "status": "error",
                "http_code": res.status_code,
                "message": f"Unexpected HTTP status {res.status_code} from CDN."
            }

        except Exception as err:
            self._ensure_offline_seeded()
            return {
                "status": "offline_fallback",
                "message": str(err),
                "is_fallback": True,
                "templates_available": len(self.get_templates())
            }

    def get_templates(self, archetype: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieves ranked viral hook archetypes ordered by velocity score descending.
        """
        self._ensure_offline_seeded()
        conn = get_db()
        cursor = conn.cursor()
        if archetype:
            cursor.execute("""
            SELECT id, archetype, hook_text, velocity_score, engagement_multiplier,
                   pacing_style, example_post_id, updated_at
            FROM viral_templates
            WHERE archetype = ?
            ORDER BY velocity_score DESC
            LIMIT ?
            """, (archetype, limit))
        else:
            cursor.execute("""
            SELECT id, archetype, hook_text, velocity_score, engagement_multiplier,
                   pacing_style, example_post_id, updated_at
            FROM viral_templates
            ORDER BY velocity_score DESC
            LIMIT ?
            """, (limit,))

        rows = cursor.fetchall()
        results = [dict(r) for r in rows]
        conn.close()
        return results

    def get_status(self) -> Dict[str, Any]:
        """Returns intelligence sync diagnostics and local cache freshness."""
        etag = self.get_cached_etag()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM viral_templates")
        total_count = cursor.fetchone()[0]
        cursor.execute("SELECT MAX(updated_at) FROM viral_templates")
        last_updated = cursor.fetchone()[0]
        conn.close()

        return {
            "status": "success",
            "cdn_url": self.cdn_url,
            "cached_etag": etag,
            "total_templates": total_count,
            "last_synced_at": last_updated,
            "is_fresh": bool(etag)
        }

    def compile_local_bundle(self) -> Dict[str, Any]:
        """
        Compiles all local viral templates and archetypes into a compressed,
        portable JSON intelligence bundle (< 50KB) adhering to Day 06 specifications.
        """
        templates = self.get_templates(limit=200)
        status = self.get_status()
        gen_at = status.get("last_synced_at") or "2026-09-18T00:00:00Z"
        return {
            "version": "2026.09.1",
            "format": "asymmetric_intelligence_bundle",
            "generated_at": gen_at,
            "templates_count": len(templates),
            "templates": templates
        }

    def import_local_bundle(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        """
        Imports an asymmetric intelligence bundle directly into local SQLite,
        supporting 100% offline, air-gapped workstations without external network requests.
        """
        templates = bundle.get("templates") or bundle.get("categories") or []
        if not templates:
            return {"status": "error", "message": "Empty or invalid intelligence bundle format."}

        conn = get_db()
        cursor = conn.cursor()
        inserted = 0
        try:
            with conn:
                cursor.execute("DELETE FROM viral_templates")
                for h in templates:
                    cursor.execute("""
                    INSERT INTO viral_templates (
                        archetype, hook_text, velocity_score, engagement_multiplier,
                        pacing_style, example_post_id, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (
                        h.get("archetype", "General"),
                        h.get("hook_text") or h.get("hook", ""),
                        float(h.get("velocity_score") or h.get("velocity", 8.0)),
                        h.get("engagement_multiplier", "1.0x"),
                        h.get("pacing_style") or h.get("pacing", "Standard"),
                        h.get("example_post_id", "imported-bundle")
                    ))
                    inserted += 1
            return {
                "status": "success",
                "imported_count": inserted,
                "version": bundle.get("version", "2026.09.1")
            }
        finally:
            conn.close()


# Global singleton instance
intelligence_sync_engine = IntelligenceSyncEngine()
