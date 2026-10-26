"""
Hook forms: the fill-in forms the Composer's hook rail applies, kept on this machine.
====================================================================================
What a new creator starts with is twelve neutral starter forms that claim
nothing until the brackets are filled; the original author's engineering
pack of 36 first-person forms is added only when the creator asks for it
(cycle 2, D-8). The rail reads them through /api/v1/intelligence/templates,
and Ctrl+K searches them in process (routers/search.py).

They lived in intelligence_sync.py beside an unsigned CDN sync that nothing
called and that replaced the whole viral_templates table on every answer.
Cycle 4, track 7 (ideas report decision 10) deleted that module: the forms
moved here unchanged, and the company's library now arrives signed, into a
table of its own (library_bundle.py), never over the creator's forms.

Strict Invariants:
- Zero em-dashes in any code, docstring or comment.
- Zero egress: nothing here opens a connection.
- Nothing invented: a starter form carries no rating, because nobody measured it.
"""

import sqlite3
from typing import Any, Dict, List, Optional

try:
    from .database import get_db
except ImportError:
    from database import get_db

MAX_TEMPLATES_LIMIT = 500
MAX_ARCHETYPE_LENGTH = 100

# The "engineering creator" pack: the original author's own hook library,
# written for a software engineering audience. Opt-in. Many of these are
# first-person claims ("I spent $2,400...", "cut our tail latency from 850ms
# to 4ms") that are only true of the person who wrote them, and every new
# creator used to start on them, one Alt+1 away from their opening line, with
# an editor's rating of 9.8 beside each.
ENGINEERING_PACK = [
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


def _starter(archetype: str, number: int, hook_text: str, pacing_style: str) -> Dict[str, Any]:
    return {
        "archetype": archetype,
        "hook_text": hook_text,
        # No rating: nobody measured these, and a number beside a form reads
        # as a forecast of how it will do.
        "velocity_score": None,
        "engagement_multiplier": None,
        "pacing_style": pacing_style,
        "example_post_id": f"starter-{archetype.lower().replace(' ', '-')}-{number:02d}",
    }


# What a new creator starts with: fill-in forms in plain shapes that suit any
# subject. Each one claims nothing until the creator fills in the brackets.
STARTER_TEMPLATES = [
    _starter("Lesson", 1, "[Number] years of [your work] taught me one thing about [topic]:",
             "One-line setup, then the lesson, then one example from your own work"),
    _starter("Lesson", 2, "What I wish I had known before [a milestone]:",
             "Name the moment, list three things, end with the one that mattered most"),
    _starter("How-to", 1, "How to [get a result] without [a common cost], in [number] steps:",
             "Promise in the first line, numbered steps, one sentence each"),
    _starter("How-to", 2, "A simple way to [do a task] that takes [time]:",
             "The method in one line, then why it works, then a first step to try today"),
    _starter("List", 1, "[Number] [things] I use every week for [a goal]:",
             "Short numbered list, one line on why for each"),
    _starter("List", 2, "[Number] mistakes I see in [topic], and what to do instead:",
             "Mistake, then the fix, repeated; close with the one you made yourself"),
    _starter("Contrarian", 1, "Most advice about [topic] says [the common view]. Here is where I disagree:",
             "State the common view fairly, then your view, then the evidence you have"),
    _starter("Contrarian", 2, "[A popular practice] is not the problem. [The real cause] is.",
             "Two short lines, then a story that shows the real cause"),
    _starter("Story", 1, "Last [time period], [something happened]. It changed how I think about [topic].",
             "What happened, what you expected, what you learned"),
    _starter("Story", 2, "A [customer, colleague or friend] asked me [a question]. My answer surprised them:",
             "The question, your answer, why you answer it that way"),
    _starter("Question", 1, "What is one thing about [topic] you changed your mind on this year?",
             "Ask, give your own answer first, invite theirs in the comments"),
    _starter("Question", 2, "If you could keep only one [tool, habit or rule] for [a goal], which would it be?",
             "Ask, name yours and why, keep it short"),
]

# What a new library is seeded with. The engineering pack is added only when
# the creator asks for it (set_engineering_pack).
FALLBACK_TEMPLATES = STARTER_TEMPLATES

# How a row from the engineering pack is recognised: its example id.
ENGINEERING_PACK_PREFIX = "blueprint-"


def seed_offline_templates(conn: Optional[sqlite3.Connection] = None,
                           templates: Optional[List[Dict[str, Any]]] = None) -> int:
    """
    Inserts built-in forms idempotently: the neutral starters unless
    `templates` names another set, such as the engineering pack.
    """
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT hook_text FROM viral_templates")
        existing_hooks = {row[0] for row in cursor.fetchall()}
        inserted = 0
        for t in (FALLBACK_TEMPLATES if templates is None else templates):
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


def ensure_seeded() -> None:
    """Seeds the starter forms when the library is empty, as a new install's is."""
    conn = None
    try:
        conn = get_db()
        if conn.execute("SELECT COUNT(*) FROM viral_templates").fetchone()[0] == 0:
            seed_offline_templates(conn)
    except Exception:
        pass
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def set_engineering_pack(enabled: bool) -> Dict[str, Any]:
    """
    Adds or removes the engineering creator pack. Removing takes only the
    pack's own rows as shipped; a starter or anything the creator imported
    stays.
    """
    if enabled:
        return {"status": "success", "enabled": True,
                "added": seed_offline_templates(templates=ENGINEERING_PACK)}
    conn = get_db()
    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM viral_templates WHERE example_post_id LIKE ? "
                "AND (origin = 'shipped' OR origin IS NULL) AND hook_text IN (%s)"
                % ",".join("?" for _ in ENGINEERING_PACK),
                (ENGINEERING_PACK_PREFIX + "%", *[t["hook_text"] for t in ENGINEERING_PACK]),
            )
            removed = cursor.rowcount
    finally:
        conn.close()
    return {"status": "success", "enabled": False, "removed": removed}


def get_templates(archetype: Optional[str] = None, query: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """
    The forms, rated ones first by the rating typed into them (a starter has
    none, and sorts last). Filtered by archetype and by words, at most
    MAX_TEMPLATES_LIMIT.
    """
    ensure_seeded()
    clamped_limit = max(1, min(int(limit) if isinstance(limit, (int, float)) else 100, MAX_TEMPLATES_LIMIT))
    conn = None
    try:
        conn = get_db()
        conditions = []
        params: List[Any] = []
        if archetype and str(archetype).strip() and str(archetype).strip().lower() != "all":
            arch_val = str(archetype).strip()[:MAX_ARCHETYPE_LENGTH]
            conditions.append("(archetype LIKE ? OR archetype = ?)")
            params.extend([f"%{arch_val}%", arch_val])
        if query and str(query).strip():
            q_val = f"%{str(query).strip()[:100]}%"
            conditions.append("(hook_text LIKE ? OR archetype LIKE ? OR pacing_style LIKE ?)")
            params.extend([q_val, q_val, q_val])
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(clamped_limit)
        rows = conn.execute(f"""
            SELECT id, archetype, hook_text, velocity_score, engagement_multiplier,
                   pacing_style, example_post_id, origin, updated_at
            FROM viral_templates
            {where_clause}
            ORDER BY velocity_score DESC
            LIMIT ?
        """, tuple(params)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def get_total_count() -> int:
    """How many forms the library holds."""
    conn = None
    try:
        conn = get_db()
        return int(conn.execute("SELECT COUNT(*) FROM viral_templates").fetchone()[0])
    except Exception:
        return len(FALLBACK_TEMPLATES)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
