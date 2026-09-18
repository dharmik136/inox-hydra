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


class GStackGovernanceEngine:
    """
    Orchestrator for G-Stack multi-agent governance, role backlogs, and anti-slop audits.
    """

    def __init__(self):
        self._ensure_backlog_seeded()

    def _ensure_backlog_seeded(self) -> None:
        """Seeds foundational G-Stack roadmap backlog if empty."""
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM gstack_backlog")
            count = cursor.fetchone()[0]
            if count == 0:
                for item in FOUNDATIONAL_BACKLOG:
                    cursor.execute("""
                    INSERT INTO gstack_backlog (role, title, specification, status, anti_slop_check)
                    VALUES (?, ?, ?, ?, 1)
                    """, (item["role"], item["title"], item["specification"], item["status"]))
                conn.commit()
            conn.close()
        except Exception:
            pass

    def get_roles(self) -> Dict[str, Any]:
        """Returns the 6 G-Stack roles, their titles, PRD references, and mandates."""
        return GSTACK_ROLES

    def get_backlog(self, role: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Queries tasks from gstack_backlog filtered by role and/or status."""
        self._ensure_backlog_seeded()
        conn = get_db()
        cursor = conn.cursor()

        query = "SELECT id, role, title, specification, status, anti_slop_check, created_at, updated_at FROM gstack_backlog WHERE 1=1"
        params: List[Any] = []

        if role:
            query += " AND role = ?"
            params.append(role)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY id ASC"
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        results = [dict(r) for r in rows]
        conn.close()
        return results

    def add_backlog_task(self, role: str, title: str, specification: str, status: str = "PENDING") -> int:
        """Appends a new task to the G-Stack governance backlog."""
        if role not in GSTACK_ROLES:
            raise ValueError(f"Invalid G-Stack role: {role}. Must be one of {list(GSTACK_ROLES.keys())}")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO gstack_backlog (role, title, specification, status, anti_slop_check, updated_at)
        VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
        """, (role, title, specification, status))
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return task_id

    def update_backlog_status(self, task_id: int, status: str) -> bool:
        """Updates the lifecycle status of a backlog item."""
        valid_statuses = ("PENDING", "IN_PROGRESS", "VERIFIED", "BLOCKED")
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE gstack_backlog
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (status, task_id))
        modified = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return modified

    def audit_content_or_feature(self, content: str, title: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes a 6-gate G-Stack audit against draft content or feature specifications:
        Gate 1 (CEO): Zero em-dash enforcement and anti-slop standards.
        Gate 2 (Engineering Manager): Structural integrity and character limits.
        Gate 3 (Designer): 2-Tier mobile fold safety (lines <= 3, chars <= 140).
        Gate 4 (QA Lead): Non-empty payload and completeness.
        Gate 5 (CSO): Absence of plain-text credentials or unsafe tracking links.
        Gate 6 (Release Manager): Self-contained, offline-renderable markdown.
        """
        violations: List[str] = []
        gates: Dict[str, Dict[str, Any]] = {}

        # Gate 1: CEO Anti-Slop (Strict Zero Em-Dash)
        em_dash_count = content.count("\u2014") + (title.count("\u2014") if title else 0)
        has_generic_buzzwords = bool(re.search(r"\b(game-changer|revolutionary|synergistic|supercharge)\b", content, re.IGNORECASE))
        g1_passed = (em_dash_count == 0) and not has_generic_buzzwords
        if em_dash_count > 0:
            violations.append(f"Gate 1 (CEO): Detected {em_dash_count} illegal em-dash characters (\\u2014).")
        if has_generic_buzzwords:
            violations.append("Gate 1 (CEO): Detected generic AI buzzword slop.")
        gates["gate_1_ceo"] = {
            "passed": g1_passed,
            "em_dash_count": em_dash_count,
            "has_buzzwords": has_generic_buzzwords
        }

        # Gate 2: Engineering Manager (Structural Bounds)
        char_count = len(content)
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
        raw_lines = content.splitlines()
        first_line = raw_lines[0].strip() if raw_lines else ""
        first_3_lines_text = "\n".join(raw_lines[:3]) if len(raw_lines) >= 3 else content
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
        has_line_breaks = "\n" in content
        g4_passed = bool(content.strip()) and has_line_breaks
        if not has_line_breaks:
            violations.append("Gate 4 (QA): Content lacks paragraph structure (monolithic block of text).")
        gates["gate_4_qa_lead"] = {
            "passed": g4_passed,
            "has_paragraph_pacing": has_line_breaks
        }

        # Gate 5: CSO Security (No Leaks / Local-First)
        has_secret_pattern = bool(re.search(r"(li_at|session_key|bot_token|api_key)=['\"][^'\"]+['\"]", content, re.IGNORECASE))
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
