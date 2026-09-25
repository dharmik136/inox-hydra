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
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import requests

try:  # the shared egress chokepoint
    from . import egress as _egress
except ImportError:
    import egress as _egress

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

# -- Validation & Boundary Constants ----------------------------------------
MAX_HOOK_TEXT_LENGTH = 1000
MAX_ARCHETYPE_LENGTH = 100
MAX_PACING_LENGTH = 300
MAX_EXAMPLE_ID_LENGTH = 100
MAX_MULTIPLIER_LENGTH = 50
MAX_TEMPLATES_LIMIT = 500
MAX_SYNC_TEMPLATES_BATCH = 1000
ALLOWED_CDN_SCHEMES = ("https",)

# Hosts this studio will fetch intelligence from.
#
# The scheme was pinned to https and the host was not, which left the endpoint
# able to reach any https service the machine can see, including internal ones
# and https://127.0.0.1:<port>. The status code and parse outcome are returned
# to the caller, and fetched hook_text lands in the database where
# /api/v1/intelligence/templates reads it back, so it was both a probe and a
# way to put chosen text in front of the creator.
#
# The AI gateway got a host rule in the same pass and this did not, which is
# the only reason it survived. Subdomains are matched explicitly rather than by
# suffix, because "evil-githubusercontent.com" ends with the same characters as
# the real host and a naive endswith would accept it.
ALLOWED_CDN_HOSTS = (
    "raw.githubusercontent.com",
    "github.com",
    "objects.githubusercontent.com",
)


def is_allowed_cdn_host(hostname):
    """
    Exact host match, case insensitive. No suffix matching.

    The host configured through INTELLIGENCE_CDN_URL is accepted as well, so a
    creator running their own mirror is not blocked by this. That is a
    deliberate line: setting an environment variable requires access to the
    machine already, whereas the cdn_url request parameter is reachable by
    anything holding the studio token, and those are different levels of trust.
    """
    if not hostname:
        return False

    candidate = hostname.strip().lower()
    if candidate in ALLOWED_CDN_HOSTS:
        return True

    configured = urllib.parse.urlparse(DEFAULT_CDN_URL).hostname
    return bool(configured) and candidate == configured.strip().lower()

FALLBACK_TEMPLATES = [
    # Taxonomy 1: Contrarian Truths & Paradigm Shifts
    {
        "archetype": "Contrarian Truths",
        "hook_text": "I spent $2,400 on creator SaaS before realizing this one uncomfortable truth.",
        "velocity_score": 9.8,
        "engagement_multiplier": "3.5x",
        "pacing_style": "1-line confession hook + blank line + 2-line context + 3-point revelation",
        "example_post_id": "blueprint-contrarian-01"
    },
    {
        "archetype": "Contrarian Truths",
        "hook_text": "Most engineering leaders measure lines of code or commit velocity. Here is why that metric is silently destroying your team:",
        "velocity_score": 9.6,
        "engagement_multiplier": "3.3x",
        "pacing_style": "Provocative premise + diagnostic proof + alternate metric framework",
        "example_post_id": "blueprint-contrarian-02"
    },
    {
        "archetype": "Contrarian Truths",
        "hook_text": "Everyone tells early-stage founders to build in public. For 95% of technical products, it is completely lethal advice.",
        "velocity_score": 9.3,
        "engagement_multiplier": "3.0x",
        "pacing_style": "Counter-narrative thesis + 3 failure modes + sovereign alternative",
        "example_post_id": "blueprint-contrarian-03"
    },
    {
        "archetype": "Contrarian Truths",
        "hook_text": "The best software engineers write the fewest lines of code. Here is how top 1% principals actually allocate their 40 hours:",
        "velocity_score": 9.0,
        "engagement_multiplier": "2.7x",
        "pacing_style": "Inverted hierarchy declaration + weekly time-budget breakdown",
        "example_post_id": "blueprint-contrarian-04"
    },
    {
        "archetype": "Contrarian Truths",
        "hook_text": "Microservices did not solve your architectural bottlenecks. They just moved your function calls across an expensive network layer.",
        "velocity_score": 8.8,
        "engagement_multiplier": "2.5x",
        "pacing_style": "Direct reality check + cost comparison + monolithic reconciliation",
        "example_post_id": "blueprint-contrarian-05"
    },
    {
        "archetype": "Contrarian Truths",
        "hook_text": "An unmoderated Slack channel is where engineering focus goes to die. Our 3 strict async communication rules:",
        "velocity_score": 8.6,
        "engagement_multiplier": "2.4x",
        "pacing_style": "Strong opinion clearly stated + 3 actionable operational rules",
        "example_post_id": "blueprint-contrarian-06"
    },

    # Taxonomy 2: Architecture & Systems Engineering
    {
        "archetype": "Architecture",
        "hook_text": "90% of software engineers misunderstand local-first architectures. Here is how it actually works:",
        "velocity_score": 9.5,
        "engagement_multiplier": "3.2x",
        "pacing_style": "Contrarian statistic + direct colon promise + ASCII sequence diagram",
        "example_post_id": "blueprint-arch-01"
    },
    {
        "archetype": "Architecture",
        "hook_text": "How we eliminated cloud egress bills entirely by pushing intelligence caching to client-side SQLite WAL:",
        "velocity_score": 9.2,
        "engagement_multiplier": "2.9x",
        "pacing_style": "Problem statement + architecture diff before/after + exact latency impact",
        "example_post_id": "blueprint-arch-02"
    },
    {
        "archetype": "Architecture",
        "hook_text": "Moving from a multi-tenant cloud API to local loopback IPC cut our tail latency from 850ms to 4ms. The architectural anatomy:",
        "velocity_score": 8.9,
        "engagement_multiplier": "2.6x",
        "pacing_style": "Benchmark hook + subsystem pipeline walkthrough + key tradeoffs",
        "example_post_id": "blueprint-arch-03"
    },
    {
        "archetype": "Architecture",
        "hook_text": "You probably do not need Kafka, Redis, and a Kubernetes cluster. A single NVMe drive with SQLite WAL handles 45,000 writes/sec:",
        "velocity_score": 8.7,
        "engagement_multiplier": "2.4x",
        "pacing_style": "Complexity contrast + raw capability benchmark + simplification guide",
        "example_post_id": "blueprint-arch-04"
    },
    {
        "archetype": "Architecture",
        "hook_text": "How to design developer tools that operate in fully air-gapped corporate environments without losing feature parity:",
        "velocity_score": 8.5,
        "engagement_multiplier": "2.3x",
        "pacing_style": "Enterprise requirement hook + 4 zero-trust primitives + offline fallback",
        "example_post_id": "blueprint-arch-05"
    },
    {
        "archetype": "Architecture",
        "hook_text": "Why Python memory bloat is rarely a garbage collection issue, and how ring buffers saved our background ingestion pipeline:",
        "velocity_score": 8.3,
        "engagement_multiplier": "2.2x",
        "pacing_style": "Diagnostic insight + memory profile analysis + ring buffer solution",
        "example_post_id": "blueprint-arch-06"
    },

    # Taxonomy 3: Reverse Engineering & Telemetry
    {
        "archetype": "Reverse Engineering",
        "hook_text": "Stop scraping the DOM. Here is how to passively extract LinkedIn creator telemetry without bot risk:",
        "velocity_score": 9.7,
        "engagement_multiplier": "3.5x",
        "pacing_style": "Expository problem + 3-step passive interception solution + ban safety",
        "example_post_id": "blueprint-re-01"
    },
    {
        "archetype": "Reverse Engineering",
        "hook_text": "Synthetic browser automation triggers Cloudflare and LinkedIn bot heuristics within 48 hours. Here is the sovereign alternative:",
        "velocity_score": 9.4,
        "engagement_multiplier": "3.1x",
        "pacing_style": "Heuristic vulnerability alert + hardware interrupt bridge explanation",
        "example_post_id": "blueprint-re-02"
    },
    {
        "archetype": "Reverse Engineering",
        "hook_text": "What we learned inspecting undocumented private enterprise APIs after capturing 100,000 live payload frames:",
        "velocity_score": 9.2,
        "engagement_multiplier": "2.9x",
        "pacing_style": "Intriguing field study + 4 hidden protocol patterns + sanitization protocol",
        "example_post_id": "blueprint-re-03"
    },
    {
        "archetype": "Reverse Engineering",
        "hook_text": "Why programmatic DOM dispatchEvent fails modern anti-bot gates, and why OS-level clipboard interrupts are 100% ban-proof:",
        "velocity_score": 8.9,
        "engagement_multiplier": "2.6x",
        "pacing_style": "Technical deep dive on event.isTrusted + clean 2-step verification protocol",
        "example_post_id": "blueprint-re-04"
    },
    {
        "archetype": "Reverse Engineering",
        "hook_text": "Decompiling client-side fingerprinting scripts: The 5 canvas and audio context traps every engineer should understand:",
        "velocity_score": 8.7,
        "engagement_multiplier": "2.4x",
        "pacing_style": "Security audit breakdown + canvas trap explanation + ethical passive defense",
        "example_post_id": "blueprint-re-05"
    },
    {
        "archetype": "Reverse Engineering",
        "hook_text": "Building an asynchronous telemetry shard that captures live network streams with 0.00ms main thread blocking:",
        "velocity_score": 8.5,
        "engagement_multiplier": "2.3x",
        "pacing_style": "Concurrency challenge + thread boundary decoupling + SQLite WAL flusher",
        "example_post_id": "blueprint-re-06"
    },

    # Taxonomy 4: Failure Analysis & War Stories
    {
        "archetype": "Failure Analysis",
        "hook_text": "Our first ingestion worker crashed at 10,000 events. Here is what broke and how we fixed it:",
        "velocity_score": 9.4,
        "engagement_multiplier": "3.1x",
        "pacing_style": "Vulnerable milestone + systemic root-cause breakdown + recovery recipe",
        "example_post_id": "blueprint-failure-01"
    },
    {
        "archetype": "Failure Analysis",
        "hook_text": "At 3:14 AM, our database locked up completely under 200 concurrent writes. Here is the postmortem:",
        "velocity_score": 9.1,
        "engagement_multiplier": "2.8x",
        "pacing_style": "High-stakes timeline + root cause analysis + concurrency locks fix",
        "example_post_id": "blueprint-failure-02"
    },
    {
        "archetype": "Failure Analysis",
        "hook_text": "We spent 3 weeks building a distributed consensus layer before having 50 active users. What we learned the hard way:",
        "velocity_score": 8.9,
        "engagement_multiplier": "2.6x",
        "pacing_style": "Founder confession + wasted effort calculus + lean refactoring rule",
        "example_post_id": "blueprint-failure-03"
    },
    {
        "archetype": "Failure Analysis",
        "hook_text": "A silent schema mismatch corrupted 400 user databases during an automatic update. How we redesigned our migration ledger:",
        "velocity_score": 8.7,
        "engagement_multiplier": "2.4x",
        "pacing_style": "Nightmare scenario + PRAGMA user_version solution + immutable ledger rule",
        "example_post_id": "blueprint-failure-04"
    },
    {
        "archetype": "Failure Analysis",
        "hook_text": "A single unclosed database cursor leaked 4GB of RAM in 6 hours on Windows desktop clients. The debugging walkthrough:",
        "velocity_score": 8.5,
        "engagement_multiplier": "2.3x",
        "pacing_style": "Mystery symptom + heap snapshot trace + context manager enforcement",
        "example_post_id": "blueprint-failure-05"
    },
    {
        "archetype": "Failure Analysis",
        "hook_text": "When a third-party CDN experienced 2000ms jitter, our synchronous UI thread froze. How we instituted circuit breakers:",
        "velocity_score": 8.3,
        "engagement_multiplier": "2.1x",
        "pacing_style": "Cascading failure cascade + circuit breaker state machine + local fallbacks",
        "example_post_id": "blueprint-failure-06"
    },

    # Taxonomy 5: Benchmarks & Teardowns
    {
        "archetype": "Benchmarks",
        "hook_text": "We benchmarked SQLite WAL vs Postgres connection pool on localhost. The numbers surprised us:",
        "velocity_score": 9.3,
        "engagement_multiplier": "3.0x",
        "pacing_style": "Numerical comparison table + test parameters + actionable takeaway",
        "example_post_id": "blueprint-bench-01"
    },
    {
        "archetype": "Benchmarks",
        "hook_text": "Measuring local IPC latency across 4 approaches: Unix domain sockets, HTTP loopback, named pipes, and shared memory:",
        "velocity_score": 9.1,
        "engagement_multiplier": "2.8x",
        "pacing_style": "Structured methodology + p50/p99 latency charts + recommendation guide",
        "example_post_id": "blueprint-bench-02"
    },
    {
        "archetype": "Benchmarks",
        "hook_text": "Adding this single composite index reduced our SQLite analytics scan time from 420ms to 1.1ms:",
        "velocity_score": 8.8,
        "engagement_multiplier": "2.5x",
        "pacing_style": "EXPLAIN QUERY PLAN diff + index structure explanation + verification query",
        "example_post_id": "blueprint-bench-03"
    },
    {
        "archetype": "Benchmarks",
        "hook_text": "Desktop app launch speed teardown: Electron (2.4s) vs Tauri (380ms) vs Local Python FastAPI + WebView (120ms):",
        "velocity_score": 8.6,
        "engagement_multiplier": "2.4x",
        "pacing_style": "Hardware setup specs + startup phase waterfall chart + resource usage",
        "example_post_id": "blueprint-bench-04"
    },
    {
        "archetype": "Benchmarks",
        "hook_text": "How SQLite WAL checkpoint sizing affects SSD write endurance when handling 500,000 background events per day:",
        "velocity_score": 8.4,
        "engagement_multiplier": "2.2x",
        "pacing_style": "Hardware wear calculations + pragma wal_autocheckpoint tuning + recommendations",
        "example_post_id": "blueprint-bench-05"
    },
    {
        "archetype": "Benchmarks",
        "hook_text": "We pushed our in-memory ring buffer to its absolute limit on a standard developer laptop. Here is where it broke:",
        "velocity_score": 8.2,
        "engagement_multiplier": "2.0x",
        "pacing_style": "Stress test parameters + breaking point metrics + backpressure mechanism",
        "example_post_id": "blueprint-bench-06"
    },

    # Taxonomy 6: Asymmetric Economics & Leverage
    {
        "archetype": "Economics",
        "hook_text": "Why $0/month infrastructure beats a $500/month cloud cluster for desktop developer tools:",
        "velocity_score": 9.5,
        "engagement_multiplier": "3.3x",
        "pacing_style": "Paradox declaration + economic breakdown + sovereignty dividends",
        "example_post_id": "blueprint-econ-01"
    },
    {
        "archetype": "Economics",
        "hook_text": "How microservices quietly convert your software engineering payroll into an Amazon AWS monthly invoice:",
        "velocity_score": 9.0,
        "engagement_multiplier": "2.7x",
        "pacing_style": "Unit economics comparison + architectural simplification + margin impact",
        "example_post_id": "blueprint-econ-02"
    },
    {
        "archetype": "Economics",
        "hook_text": "How a single engineer can operate an enterprise-grade SaaS with zero full-time ops personnel:",
        "velocity_score": 8.8,
        "engagement_multiplier": "2.5x",
        "pacing_style": "Automated tooling stack + maintenance-free patterns + weekly time budget",
        "example_post_id": "blueprint-econ-03"
    },
    {
        "archetype": "Economics",
        "hook_text": "Why the future of professional software is moving back from browser tabs to sovereign desktop runtimes:",
        "velocity_score": 8.6,
        "engagement_multiplier": "2.4x",
        "pacing_style": "Macro shift observation + privacy/performance comparison + roadmap",
        "example_post_id": "blueprint-econ-04"
    },
    {
        "archetype": "Economics",
        "hook_text": "Giving away your core engine for free while monetizing local enterprise intelligence: The economic formula:",
        "velocity_score": 8.4,
        "engagement_multiplier": "2.2x",
        "pacing_style": "Business model breakdown + distribution math + sustainable developer economics",
        "example_post_id": "blueprint-econ-05"
    },
    {
        "archetype": "Economics",
        "hook_text": "Rules for building software that still compiles, runs, and serves customers 5 years from now with zero patches:",
        "velocity_score": 8.2,
        "engagement_multiplier": "2.0x",
        "pacing_style": "5 golden constraints + dependency minimization + durability philosophy",
        "example_post_id": "blueprint-econ-06"
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
        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM viral_templates")
            count = cursor.fetchone()[0]
            if count == 0:
                self.seed_offline_templates(conn)
        except Exception:
            pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def seed_offline_templates(self, conn: Optional[sqlite3.Connection] = None) -> int:
        """Inserts built-in fallback viral templates idempotently into the local SQLite store."""
        should_close = False
        if conn is None:
            conn = get_db()
            should_close = True
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT hook_text FROM viral_templates")
            existing_hooks = {row[0] for row in cursor.fetchall()}
            inserted = 0
            for t in FALLBACK_TEMPLATES:
                if t["hook_text"] not in existing_hooks:
                    cursor.execute("""
                    INSERT INTO viral_templates (
                        archetype, hook_text, velocity_score, engagement_multiplier,
                        pacing_style, example_post_id, origin, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'shipped', CURRENT_TIMESTAMP)
                    """, (
                        t["archetype"],
                        t["hook_text"],
                        t["velocity_score"],
                        t["engagement_multiplier"],
                        t["pacing_style"],
                        t["example_post_id"]
                    ))
                    existing_hooks.add(t["hook_text"])
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
        target_url = (cdn_url or self.cdn_url).strip()
        parsed = urllib.parse.urlparse(target_url)
        if parsed.scheme not in ALLOWED_CDN_SCHEMES:
            return {
                "status": "error",
                "message": f"Disallowed URL scheme '{parsed.scheme}'. Only HTTPS is permitted."
            }
        if not is_allowed_cdn_host(parsed.hostname):
            return {
                "status": "error",
                "message": (
                    f"Disallowed intelligence host '{parsed.hostname}'. "
                    f"Permitted: {', '.join(ALLOWED_CDN_HOSTS)}."
                )
            }

        etag = None if force else self.get_cached_etag()

        headers = {
            "User-Agent": "PrudentStudio/2.5 (Windows; x64)",
            "Accept": "application/json"
        }
        if etag:
            headers["If-None-Match"] = etag

        try:
            # Refuses rather than connecting when this category is off. See egress.py.
            _egress.require(target_url, "library")
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
                if not isinstance(payload, dict):
                    return {
                        "status": "error",
                        "message": "Invalid CDN payload: expected JSON object."
                    }

                raw_categories = payload.get("categories") or payload.get("templates") or []
                if not isinstance(raw_categories, list):
                    raw_categories = []

                new_etag = res.headers.get("ETag") or res.headers.get("etag")

                # Validate the payload fully before touching the database so a
                # release with zero usable templates cannot wipe the local cache.
                cleaned_rows = []
                for h in raw_categories[:MAX_SYNC_TEMPLATES_BATCH]:
                    if not isinstance(h, dict):
                        continue
                    hook_text = str(h.get("hook_text") or h.get("hook") or "").strip()[:MAX_HOOK_TEXT_LENGTH]
                    if not hook_text:
                        continue
                    try:
                        # `or` treats a genuine 0.0 as missing and substitutes
                        # 8.0, so the worst performing hook in a bundle
                        # outranked real 7.x entries. Absence is tested for,
                        # not inferred from falsiness.
                        raw_velocity = h.get("velocity_score")
                        if raw_velocity is None:
                            raw_velocity = h.get("velocity")
                        velocity = float(8.0 if raw_velocity is None else raw_velocity)
                    except (ValueError, TypeError):
                        velocity = 8.0
                    cleaned_rows.append((
                        str(h.get("archetype", "General"))[:MAX_ARCHETYPE_LENGTH],
                        hook_text,
                        velocity,
                        str(h.get("engagement_multiplier", "1.0x"))[:MAX_MULTIPLIER_LENGTH],
                        str(h.get("pacing_style") or h.get("pacing", "Standard"))[:MAX_PACING_LENGTH],
                        str(h.get("example_post_id", "synced-remote"))[:MAX_EXAMPLE_ID_LENGTH]
                    ))

                if not cleaned_rows:
                    # Not a client error: the request succeeded and the local
                    # cache is intact, so this reports as a successful no-op.
                    # The ETag is deliberately not saved, so a later corrected
                    # release is not masked by a 304 for this bad one.
                    return {
                        "status": "no_valid_templates",
                        "http_code": 200,
                        "hooks_count": 0,
                        "templates_available": self.get_total_count(),
                        "message": "CDN payload contained no valid templates. Local intelligence cache preserved."
                    }

                conn = None
                try:
                    conn = get_db()
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM viral_templates")
                        # 'synced', not 'shipped'. These arrived from a bundle
                        # feed, so calling them shipped would be a guess about
                        # where a row came from, which is the thing the column
                        # exists to stop.
                        cursor.executemany("""
                        INSERT INTO viral_templates (
                            archetype, hook_text, velocity_score, engagement_multiplier,
                            pacing_style, example_post_id, origin, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, 'synced', CURRENT_TIMESTAMP)
                        """, cleaned_rows)
                finally:
                    if conn:
                        try:
                            conn.close()
                        except Exception:
                            pass

                # Save the ETag only after the transaction committed, so a
                # failed write leaves the cache eligible for a clean re-sync.
                if new_etag:
                    self.save_etag(new_etag)

                return {
                    "status": "updated",
                    "http_code": 200,
                    "hooks_count": len(cleaned_rows),
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

    def get_templates(self, archetype: Optional[str] = None, query: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieves ranked viral hook archetypes ordered by velocity score descending.
        Supports filtering by archetype (exact or substring) and free-text query.
        Clamps limit between 1 and MAX_TEMPLATES_LIMIT (500).
        """
        self._ensure_offline_seeded()
        clamped_limit = max(1, min(int(limit) if isinstance(limit, (int, float)) else 100, MAX_TEMPLATES_LIMIT))

        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            conditions = []
            params = []

            if archetype and str(archetype).strip() and str(archetype).strip().lower() != "all":
                arch_val = str(archetype).strip()[:MAX_ARCHETYPE_LENGTH]
                conditions.append("(archetype LIKE ? OR archetype = ?)")
                params.extend([f"%{arch_val}%", arch_val])

            if query and str(query).strip():
                q_val = f"%{str(query).strip()[:100]}%"
                conditions.append("(hook_text LIKE ? OR archetype LIKE ? OR pacing_style LIKE ?)")
                params.extend([q_val, q_val, q_val])

            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            sql = f"""
            SELECT id, archetype, hook_text, velocity_score, engagement_multiplier,
                   pacing_style, example_post_id, origin, updated_at
            FROM viral_templates
            {where_clause}
            ORDER BY velocity_score DESC
            LIMIT ?
            """
            params.append(clamped_limit)
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_total_count(self) -> int:
        """Returns total count of viral templates in the local SQLite store."""
        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM viral_templates")
            count = cursor.fetchone()[0]
            return int(count)
        except Exception:
            return len(FALLBACK_TEMPLATES)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_status(self) -> Dict[str, Any]:
        """Returns intelligence sync diagnostics and local cache freshness."""
        etag = self.get_cached_etag()
        total_count = 0
        last_updated = None
        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM viral_templates")
            total_count = cursor.fetchone()[0]
            cursor.execute("SELECT MAX(updated_at) FROM viral_templates")
            last_updated = cursor.fetchone()[0]
        except Exception:
            pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

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

    def import_local_bundle(self, bundle: Any) -> Dict[str, Any]:
        """
        Imports an asymmetric intelligence bundle directly into local SQLite,
        supporting 100% offline, air-gapped workstations without external network requests.
        """
        if not isinstance(bundle, dict):
            return {"status": "error", "message": "Empty or invalid intelligence bundle format."}

        templates = bundle.get("templates") or bundle.get("categories") or []
        if not isinstance(templates, list) or not templates:
            return {"status": "error", "message": "Empty or invalid intelligence bundle format."}

        # Nothing is deleted until the replacement is known to be usable.
        #
        # This used to DELETE FROM viral_templates and then skip invalid items
        # one at a time, so a bundle whose every entry failed validation, for
        # example a list of plain strings from an older export, emptied the
        # store, imported nothing, and returned status success with
        # imported_count 0. sync() was hardened against exactly this with a
        # pre-flight pass; this path never was.
        usable = [
            h for h in templates[:MAX_SYNC_TEMPLATES_BATCH]
            if isinstance(h, dict)
            and str(h.get("hook_text") or h.get("hook") or "").strip()
        ]
        if not usable:
            return {
                "status": "error",
                "message": (
                    "No usable templates in this bundle, so the existing library "
                    "was left untouched. Expected objects carrying a hook_text field."
                ),
            }

        conn = None
        inserted = 0
        try:
            conn = get_db()
            with conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM viral_templates")
                for h in usable:
                    hook_text = str(h.get("hook_text") or h.get("hook") or "").strip()[:MAX_HOOK_TEXT_LENGTH]
                    if not hook_text:
                        continue
                    try:
                        # `or` treats a genuine 0.0 as missing and substitutes
                        # 8.0, so the worst performing hook in a bundle
                        # outranked real 7.x entries. Absence is tested for,
                        # not inferred from falsiness.
                        raw_velocity = h.get("velocity_score")
                        if raw_velocity is None:
                            raw_velocity = h.get("velocity")
                        velocity = float(8.0 if raw_velocity is None else raw_velocity)
                    except (ValueError, TypeError):
                        velocity = 8.0

                    cursor.execute("""
                    INSERT INTO viral_templates (
                        archetype, hook_text, velocity_score, engagement_multiplier,
                        pacing_style, example_post_id, origin, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'imported', CURRENT_TIMESTAMP)
                    """, (
                        str(h.get("archetype", "General"))[:MAX_ARCHETYPE_LENGTH],
                        hook_text,
                        velocity,
                        str(h.get("engagement_multiplier", "1.0x"))[:MAX_MULTIPLIER_LENGTH],
                        str(h.get("pacing_style") or h.get("pacing", "Standard"))[:MAX_PACING_LENGTH],
                        str(h.get("example_post_id", "imported-bundle"))[:MAX_EXAMPLE_ID_LENGTH]
                    ))
                    inserted += 1

            return {
                "status": "success",
                "imported_count": inserted,
                "version": bundle.get("version", "2026.09.1")
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to import bundle: {str(e)}"}
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


# Global singleton instance
intelligence_sync_engine = IntelligenceSyncEngine()
