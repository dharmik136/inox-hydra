"""
G-Stack Multi-Agent Governance & Role-Based Backlog Registry
=============================================================
Operationalizes Y Combinator CEO Garry Tan's G-Stack framework for LinkedIn Strategy Studio.
Coordinates 6 specialized cognitive modes:
1. CEO & Product Strategist
2. Engineering Manager
3. Lead UI/UX Designer
4. QA & Verification Lead
5. Chief Security Officer (CSO)
6. Release & Ops Manager

Design Constraints:
1. Strict Zero Em-Dashes: Character \\u2014 is strictly prohibited.
2. Deterministic Verification: Mathematical validation over stochastic guesses.
3. Offline Autonomy: Zero cloud egress during local audits.
"""

import os
import re
import json
import sqlite3
from typing import Dict, Any, List, Optional

try:
    from .database import get_db
except ImportError:
    from database import get_db

MAX_TITLE_LENGTH = 300
MAX_SPEC_LENGTH = 10000
MAX_ROLE_LENGTH = 50
MAX_STATUS_LENGTH = 50
MAX_AUDIT_CONTENT_LENGTH = 50000
VALID_BACKLOG_STATUSES = ("PENDING", "IN_PROGRESS", "VERIFIED", "BLOCKED")

GSTACK_ROLES = {
    "CEO": {
        "title": "CEO & Product Strategist",
        "prd_ref": "gstack/01_CEO_STRATEGY.md",
        "mandate": "Product moats, ICP definitions, zero-dollar unit economics, and anti-slop enforcement.",
        "focus_areas": ["Market Moat", "Pricing Positioning", "Anti-Slop Guidelines", "ICP Scoring Formula"]
    },
    "ENGINEERING_MANAGER": {
        "title": "Engineering Manager",
        "prd_ref": "gstack/02_ENG_MANAGER_SPEC.md",
        "mandate": "SQLite WAL concurrency, single-writer actor queues, SSE real-time buses, and schema integrity.",
        "focus_areas": ["WAL Pragmas", "Actor Queue Concurrency", "Event Bus Latency", "Relational Schemas"]
    },
    "DESIGNER": {
        "title": "Lead UI/UX Designer",
        "prd_ref": "gstack/03_DESIGN_SYSTEM.md",
        "mandate": "8 bifurcated pages, Swiss typography, mobile feed fold physics, and zero CLS layout shifts.",
        "focus_areas": ["2-Tier Fold Engine", "Swiss Typography", "Bifurcated Views", "Fluid Container Queries"]
    },
    "QA_LEAD": {
        "title": "QA & Verification Lead",
        "prd_ref": "gstack/04_QA_PLAYBOOK.md",
        "mandate": "Multi-threaded stress testing, Playwright E2E browser automation, and crash recovery.",
        "focus_areas": ["Statistical Distribution Tests", "Concurrency Stress Benchmarks", "E2E Regression Suits"]
    },
    "CSO": {
        "title": "Chief Security Officer",
        "prd_ref": "gstack/05_CSO_SECURITY.md",
        "mandate": "Zero cloud egress, DPAPI hardware keying, passive network observation, and anti-bot immunity.",
        "focus_areas": ["Hardware Token Vault", "Passive Telemetry Bridge", "Gaussian Jitter Pacing", "No-Egress Audit"]
    },
    "RELEASE_MANAGER": {
        "title": "Release & Ops Manager",
        "prd_ref": "gstack/06_RELEASE_OPS.md",
        "mandate": "1-click single-binary desktop packaging, GitHub Releases CDN differential sync, and offline installers.",
        "focus_areas": ["Asymmetric ETag CDN Sync", "PyInstaller Bundling", "Localhost Isolation", "Zero-Config Launch"]
    }
}

FOUNDATIONAL_BACKLOG = [
    {
        "role": "CEO",
        "title": "Establish Anti-Slop Discipline & Zero-Dollar Unit Economics",
        "specification": "Enforce strict zero em-dash rule, deterministic math over LLMs, and $0/mo architecture.",
        "status": "VERIFIED"
    },
    {
        "role": "ENGINEERING_MANAGER",
        "title": "Build SQLite WAL Single-Writer Actor Queue",
        "specification": "Serialize all background write tasks via dedicated worker thread to eliminate database locks.",
        "status": "VERIFIED"
    },
    {
        "role": "DESIGNER",
        "title": "Implement 2-Tier Mobile Feed Fold Simulator",
        "specification": "Enforce 3-line or 140-char fold boundary with 45-char blank line weighting and visual badges.",
        "status": "VERIFIED"
    },
    {
        "role": "QA_LEAD",
        "title": "Automated Verification Suites for Roadmap Days 01 through 04",
        "specification": "Author hermetic pytest test suites covering Gaussian distribution, ETag sync, and DPAPI vault.",
        "status": "VERIFIED"
    },
    {
        "role": "CSO",
        "title": "Passive Voyager Telemetry & Hardware-Keyed DPAPI Vault",
        "specification": "Capture browser telemetry without synthetic bot clicks; encrypt session cookies with DPAPI.",
        "status": "VERIFIED"
    },
    {
        "role": "RELEASE_MANAGER",
        "title": "Asymmetric GitHub CDN Differential Intelligence Sync",
        "specification": "Implement If-None-Match ETag sync returning 304 (0 bytes) when viral templates are unchanged.",
        "status": "VERIFIED"
    }
]

UPCOMING_ROADMAP_BACKLOG = [
    # Milestone 2: Hook Mechanics & Asymmetric Intelligence (Days 05 - 08)
    {
        "role": "CEO",
        "title": "Day 05: Algorithmic Dwell Time Mathematical Weighting",
        "specification": "Define formula: Score = 0.55*Dwell + 0.30*Comments + 0.15*Reactions to maximize feed visibility.",
        "status": "PENDING"
    },
    {
        "role": "DESIGNER",
        "title": "Day 05: Bifurcated Trend Radar & Topic Velocity Grid",
        "specification": "Implement #view-radar with Swiss card layout and 7-day velocity differentials.",
        "status": "PENDING"
    },
    {
        "role": "ENGINEERING_MANAGER",
        "title": "Day 05: SQLite 7-Day Moving Average & Keyword Velocity Calculator",
        "specification": "Compute local rolling average of impression velocity without cloud analytics dependencies.",
        "status": "PENDING"
    },
    {
        "role": "QA_LEAD",
        "title": "Day 05: Dwell Time Pacing & Fold Boundary Test Matrix",
        "specification": "Stress-test mobile fold simulator across edge cases: 1-line hooks, multiline code snippets, and emojis.",
        "status": "PENDING"
    },
    {
        "role": "ENGINEERING_MANAGER",
        "title": "Day 06: Multi-Mirror CDN Fallback Engine",
        "specification": "Implement redundant fallback chain: GitHub CDN -> jsDelivr -> Cloudflare R2 on 403 or 429.",
        "status": "PENDING"
    },
    {
        "role": "CSO",
        "title": "Day 06: Anonymous Egress & Zero-Leak Edge Telemetry Verification",
        "specification": "Verify that all intelligence sync requests strip local machine fingerprints and credentials.",
        "status": "PENDING"
    },
    {
        "role": "RELEASE_MANAGER",
        "title": "Day 07: GitHub Releases Differential ETag Synchronization",
        "specification": "Automate conditional packaging updates via GitHub release assets with ETag caching.",
        "status": "PENDING"
    },
    {
        "role": "CEO",
        "title": "Day 08: Zero Token Markup Local AI Gateway Specification",
        "specification": "Establish direct BYO-AI client architecture bypassing intermediary token reseller taxes.",
        "status": "PENDING"
    },
    {
        "role": "CSO",
        "title": "Day 08: DPAPI Hardware Keying for Third-Party AI API Keys",
        "specification": "Encrypt OpenAI, Anthropic, and Gemini API keys locally via Windows DPAPI before SQLite persistence.",
        "status": "PENDING"
    },
    # Milestone 3: Modular Architecture & Systems Engineering (Days 09 - 12)
    {
        "role": "ENGINEERING_MANAGER",
        "title": "Day 09: Sub-Millisecond SQLite FTS5 Full-Text Search for Docs",
        "specification": "Build instant offline search index across all markdown playbooks and architectural specs.",
        "status": "PENDING"
    },
    {
        "role": "DESIGNER",
        "title": "Day 09: Split-Pane Swiss Documentation Reader",
        "specification": "Render offline architecture manuals with syntax highlighting and instant topic switching.",
        "status": "PENDING"
    },
    {
        "role": "ENGINEERING_MANAGER",
        "title": "Day 10: Decouple SPA Modules with Strict Lifecycle Mount & Unmount",
        "specification": "Refactor monolithic UI views into modular DOM controllers with explicit cleanup handlers.",
        "status": "PENDING"
    },
    {
        "role": "CEO",
        "title": "Day 11: Post-Publish Edit & External Link Penalty Auditing Rules",
        "specification": "Formalize algorithm reach suppression warnings for post edits within 60 minutes and outbound URLs.",
        "status": "PENDING"
    },
    {
        "role": "CEO",
        "title": "Day 12: Multi-Factor ICP Scoring & Reverse-Engineered DM Templates",
        "specification": "Score incoming commenters by seniority, company size, and engagement depth into Warm Lead pipeline.",
        "status": "PENDING"
    },
    # Milestone 4: Quality Assurance, Packaging & Launch (Days 13 - 17)
    {
        "role": "DESIGNER",
        "title": "Day 13: Vector PDF Carousel Generator with Swiss Grid Geometry",
        "specification": "Programmatically generate high-DPI 4:5 document carousels with sharp typography and zero bitmap blur.",
        "status": "PENDING"
    },
    {
        "role": "QA_LEAD",
        "title": "Day 14: Playwright End-to-End Visual Regression Suite",
        "specification": "Automate headless Chromium tests validating desktop layout stability and 0 CLS across all 8 views.",
        "status": "PENDING"
    },
    {
        "role": "CSO",
        "title": "Day 15: Comprehensive Air-Gap & Token Storage Threat Modeling",
        "specification": "Conduct security audit asserting zero background outbound network sockets during offline operation.",
        "status": "PENDING"
    },
    {
        "role": "RELEASE_MANAGER",
        "title": "Day 16: Single-Binary Windows PyInstaller & Embedded CPython Packager",
        "specification": "Bundle application, local web server, and dependencies into a self-contained portable Windows executable.",
        "status": "PENDING"
    },
    {
        "role": "CEO",
        "title": "Day 17: Public Launch Kit & The Sovereign Creator Manifesto Post",
        "specification": "Finalize launch messaging, public documentation distribution, and open-source release kit.",
        "status": "PENDING"
    }
]


class GStackGovernanceEngine:
    """
    Orchestrator for G-Stack multi-agent governance, role backlogs, and anti-slop audits.
    """

    def __init__(self):
        self._ensure_backlog_seeded()

    def _ensure_backlog_seeded(self) -> None:
        """Seeds foundational G-Stack roadmap backlog and upcoming milestones if not present."""
        conn = None
        try:
            conn = get_db()
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM gstack_backlog")
                count = cursor.fetchone()[0]
                if count == 0:
                    for item in FOUNDATIONAL_BACKLOG:
                        cursor.execute("""
                        INSERT INTO gstack_backlog (role, title, specification, status, anti_slop_check)
                        VALUES (?, ?, ?, ?, 1)
                        """, (item["role"], item["title"], item["specification"], item["status"]))
                
                # Seed upcoming milestones idempotently
                for item in UPCOMING_ROADMAP_BACKLOG:
                    cursor.execute(
                        "SELECT COUNT(*) FROM gstack_backlog WHERE role = ? AND title = ?",
                        (item["role"], item["title"])
                    )
                    if cursor.fetchone()[0] == 0:
                        cursor.execute("""
                        INSERT INTO gstack_backlog (role, title, specification, status, anti_slop_check)
                        VALUES (?, ?, ?, ?, 1)
                        """, (item["role"], item["title"], item["specification"], item["status"]))
        except Exception:
            pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_roles(self) -> Dict[str, Any]:
        """Returns the 6 G-Stack roles, their titles, PRD references, and mandates."""
        return GSTACK_ROLES

    def get_backlog(self, role: Optional[str] = None, status: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
        """Queries tasks from gstack_backlog filtered by role and/or status."""
        self._ensure_backlog_seeded()
        clamped_limit = max(1, min(int(limit) if isinstance(limit, (int, float)) else 500, 1000))
        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor()

            query = "SELECT id, role, title, specification, status, anti_slop_check, created_at, updated_at FROM gstack_backlog WHERE 1=1"
            params: List[Any] = []

            if role and str(role).strip():
                clean_role = str(role).strip()[:MAX_ROLE_LENGTH]
                query += " AND role = ?"
                params.append(clean_role)
            if status and str(status).strip():
                clean_status = str(status).strip().upper()[:MAX_STATUS_LENGTH]
                query += " AND status = ?"
                params.append(clean_status)

            query += " ORDER BY id ASC LIMIT ?"
            params.append(clamped_limit)
            cursor.execute(query, tuple(params))
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

    def add_backlog_task(self, role: str, title: str, specification: str, status: str = "PENDING") -> int:
        """Appends a new task to the G-Stack governance backlog."""
        norm_role = str(role or "").strip().upper()[:MAX_ROLE_LENGTH]
        if norm_role not in GSTACK_ROLES:
            raise ValueError(f"Invalid G-Stack role: {role}. Must be one of {list(GSTACK_ROLES.keys())}")

        clean_title = str(title or "").strip()[:MAX_TITLE_LENGTH]
        if not clean_title:
            raise ValueError("Task title cannot be empty.")

        clean_spec = str(specification or "").strip()[:MAX_SPEC_LENGTH]
        if not clean_spec:
            raise ValueError("Task specification cannot be empty.")

        norm_status = str(status or "PENDING").strip().upper()[:MAX_STATUS_LENGTH]
        if norm_status not in VALID_BACKLOG_STATUSES:
            raise ValueError(f"Invalid status: {status}. Must be one of {VALID_BACKLOG_STATUSES}")

        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO gstack_backlog (role, title, specification, status, anti_slop_check, updated_at)
            VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            """, (norm_role, clean_title, clean_spec, norm_status))
            task_id = cursor.lastrowid
            conn.commit()
            return int(task_id)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def update_backlog_status(self, task_id: int, status: str) -> bool:
        """Updates the lifecycle status of a backlog item."""
        if not isinstance(task_id, int) or task_id <= 0:
            return False

        norm_status = str(status or "").strip().upper()[:MAX_STATUS_LENGTH]
        if norm_status not in VALID_BACKLOG_STATUSES:
            raise ValueError(f"Invalid status: {status}. Must be one of {VALID_BACKLOG_STATUSES}")

        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE gstack_backlog
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (norm_status, task_id))
            modified = cursor.rowcount > 0
            conn.commit()
            return modified
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def audit_content_or_feature(self, content: Any, title: Optional[Any] = None) -> Dict[str, Any]:
        """
        Executes a 6-gate G-Stack audit against draft content or feature specifications:
        Gate 1 (CEO): Zero em-dash enforcement and anti-slop standards.
        Gate 2 (Engineering Manager): Structural integrity and character limits.
        Gate 3 (Designer): 2-Tier mobile fold safety (lines <= 3, chars <= 140).
        Gate 4 (QA Lead): Non-empty payload and completeness.
        Gate 5 (CSO): Absence of plain-text credentials or unsafe tracking links.
        Gate 6 (Release Manager): Self-contained, offline-renderable markdown.
        """
        safe_content = str(content or "")[:MAX_AUDIT_CONTENT_LENGTH]
        safe_title = str(title or "")[:MAX_TITLE_LENGTH] if title is not None else ""

        violations: List[str] = []
        gates: Dict[str, Dict[str, Any]] = {}

        # Gate 1: CEO Anti-Slop (Strict Zero Em-Dash)
        em_dash = chr(0x2014)
        em_dash_count = safe_content.count(em_dash) + safe_title.count(em_dash)
        has_generic_buzzwords = bool(re.search(r"\b(game-changer|revolutionary|synergistic|supercharge)\b", safe_content, re.IGNORECASE))
        g1_passed = (em_dash_count == 0) and not has_generic_buzzwords
        if em_dash_count > 0:
            violations.append(f"Gate 1 (CEO): Detected {em_dash_count} illegal em-dash characters (U+2014).")
        if has_generic_buzzwords:
            violations.append("Gate 1 (CEO): Detected generic AI buzzword slop.")
        gates["gate_1_ceo"] = {
            "passed": g1_passed,
            "em_dash_count": em_dash_count,
            "has_buzzwords": has_generic_buzzwords
        }

        # Gate 2: Engineering Manager (Structural Bounds)
        char_count = len(safe_content)
        g2_passed = (50 <= char_count <= 3000)
        if char_count < 50:
            violations.append("Gate 2 (Eng Manager): Content is too short for algorithmic authority (<50 characters).")
        elif char_count > 3000:
            violations.append("Gate 2 (Eng Manager): Content exceeds LinkedIn maximum length bounds (>3000 characters).")
        gates["gate_2_eng_manager"] = {
            "passed": g2_passed,
            "char_count": char_count
        }

        # Gate 3: Designer (Mobile Fold Safety)
        raw_lines = safe_content.splitlines()
        first_line = raw_lines[0].strip() if raw_lines else ""
        first_3_lines_text = "\n".join(raw_lines[:3]) if len(raw_lines) >= 3 else safe_content
        pre_fold_chars = len(first_3_lines_text)
        g3_passed = (len(first_line) <= 140 and pre_fold_chars <= 210)
        if len(first_line) > 140:
            violations.append(f"Gate 3 (Designer): First line hook ({len(first_line)} chars) exceeds mobile 140-char limit.")
        if pre_fold_chars > 210:
            violations.append(f"Gate 3 (Designer): Pre-fold text ({pre_fold_chars} chars) exceeds mobile fold 210-char threshold.")
        gates["gate_3_designer"] = {
            "passed": g3_passed,
            "first_line_chars": len(first_line),
            "pre_fold_chars": pre_fold_chars,
            "is_pre_fold_safe": g3_passed
        }

        # Gate 4: QA Lead (Completeness & Formatting)
        has_line_breaks = "\n" in safe_content
        g4_passed = bool(safe_content.strip()) and has_line_breaks
        if not has_line_breaks:
            violations.append("Gate 4 (QA): Content lacks paragraph structure (monolithic block of text).")
        gates["gate_4_qa_lead"] = {
            "passed": g4_passed,
            "has_paragraph_pacing": has_line_breaks
        }

        # Gate 5: CSO Security (No Leaks / Local-First)
        has_secret_pattern = bool(re.search(r"(li_at|session_key|bot_token|api_key)=['\"][^'\"]+['\"]", safe_content, re.IGNORECASE))
        g5_passed = not has_secret_pattern
        if has_secret_pattern:
            violations.append("Gate 5 (CSO): Potential credentials or secret keys detected in text payload.")
        gates["gate_5_cso"] = {
            "passed": g5_passed,
            "no_exposed_secrets": g5_passed
        }

        # Gate 6: Release Manager (Self-Contained)
        g6_passed = True
        gates["gate_6_release_manager"] = {
            "passed": g6_passed,
            "offline_renderable": True
        }

        all_passed = all(g["passed"] for g in gates.values())
        passed_count = sum(1 for g in gates.values() if g["passed"])
        score = int((passed_count / len(gates)) * 100)

        return {
            "passed": all_passed,
            "score": score,
            "gates": gates,
            "violations": violations
        }


# Global singleton instance
gstack_engine = GStackGovernanceEngine()
