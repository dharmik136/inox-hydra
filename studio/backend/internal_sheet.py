"""
Internal Sheet & Visual Screen Concept Identifier Engine
=========================================================
Zero-egress local issue, concept, and annotation ledger for Inox Hydra.
Allows on-screen visual selection of DOM elements, captures contextual
diagnostics (tag, selector, tab, snippet, bounding box), and persists
records directly into SQLite.

Provides RFC-4180 CSV sheet export compatible with Google Sheets and Excel,
along with direct 1-click promotion to the G-Stack multi-agent backlog.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
- Zero cloud egress: 100% local persistence in SQLite.
"""

import csv
import io
import json
import sqlite3
from typing import Any, Dict, List, Optional

try:
    from .database import get_db
    from .gstack_governance import gstack_engine
except ImportError:
    from database import get_db
    from gstack_governance import gstack_engine

MAX_LIST_LIMIT = 2000

VALID_CATEGORIES = {
    "bug",
    "concept",
    "ux_glitch",
    "copy_slop",
    "data_mismatch",
    "feature_request",
}

VALID_SEVERITIES = {
    "low",
    "medium",
    "high",
    "critical",
}

VALID_ROLES = {
    "CEO",
    "ENGINEERING_MANAGER",
    "DESIGNER",
    "QA_LEAD",
    "CSO",
    "RELEASE_MANAGER",
}

VALID_STATUSES = {
    "OPEN",
    "IN_PROGRESS",
    "RESOLVED",
    "WONT_FIX",
}


class InternalSheetManager:
    """Manages visual screen concept identification and internal sheet records."""

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path

    def _get_conn(self) -> sqlite3.Connection:
        if self._db_path:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            return conn
        return get_db()

    def create_issue(
        self,
        target_selector: str,
        title: str,
        description: str,
        category: str = "bug",
        severity: str = "medium",
        suggested_role: str = "ENGINEERING_MANAGER",
        element_tag: Optional[str] = None,
        element_id: Optional[str] = None,
        element_classes: Optional[str] = None,
        element_text_snippet: Optional[str] = None,
        tab_name: str = "composer",
        page_route: str = "/",
        bounding_box: Optional[Dict[str, Any]] = None,
        viewport_resolution: Optional[str] = None,
        dom_path: Optional[str] = None,
        promote_to_backlog: bool = False,
    ) -> Dict[str, Any]:
        """
        Creates a new internal sheet issue / concept record.
        Optionally promotes directly to G-Stack multi-agent backlog.
        """
        # Enforce zero em-dash invariant
        target_selector = (target_selector or "").replace("\u2014", " - ")
        title = (title or "").replace("\u2014", " - ")
        description = (description or "").replace("\u2014", " - ")
        if element_text_snippet:
            element_text_snippet = element_text_snippet.replace("\u2014", " - ")

        if not target_selector.strip():
            raise ValueError("target_selector is required")
        if not title.strip():
            raise ValueError("title is required")
        if not description.strip():
            raise ValueError("description is required")

        category_clean = category.lower().strip() if category else "bug"
        if category_clean not in VALID_CATEGORIES:
            category_clean = "bug"

        severity_clean = severity.lower().strip() if severity else "medium"
        if severity_clean not in VALID_SEVERITIES:
            severity_clean = "medium"

        role_clean = suggested_role.upper().strip() if suggested_role else "ENGINEERING_MANAGER"
        if role_clean not in VALID_ROLES:
            role_clean = "ENGINEERING_MANAGER"

        bbox_json = json.dumps(bounding_box) if bounding_box else None

        gstack_task_id = None
        if promote_to_backlog:
            spec = (
                f"[Visual Annotation] Tab: {tab_name} | Selector: {target_selector}\n"
                f"Snippet: {element_text_snippet or 'N/A'}\n"
                f"Problem: {description}"
            )
            gstack_task_id = gstack_engine.add_backlog_task(
                role=role_clean,
                title=f"[{category_clean.upper()}] {title}",
                specification=spec,
                status="PENDING",
            )

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO internal_sheet_issues (
                    target_selector, element_tag, element_id, element_classes,
                    element_text_snippet, tab_name, page_route, category,
                    severity, title, description, suggested_role, status,
                    bounding_box, viewport_resolution, dom_path, gstack_task_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    target_selector,
                    element_tag,
                    element_id,
                    element_classes,
                    element_text_snippet,
                    tab_name,
                    page_route,
                    category_clean,
                    severity_clean,
                    title,
                    description,
                    role_clean,
                    bbox_json,
                    viewport_resolution,
                    dom_path,
                    gstack_task_id,
                ),
            )
            issue_id = cursor.lastrowid
            conn.commit()
            return self.get_issue(issue_id)
        finally:
            conn.close()

    def get_issue(self, issue_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a single issue by ID."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM internal_sheet_issues WHERE id = ?", (issue_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(row)
        finally:
            conn.close()

    def list_issues(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        tab_name: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """Lists issues with optional filtering."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM internal_sheet_issues WHERE 1=1"
            params: List[Any] = []

            if status:
                query += " AND status = ?"
                params.append(status.upper().strip())
            if category:
                query += " AND category = ?"
                params.append(category.lower().strip())
            if severity:
                query += " AND severity = ?"
                params.append(severity.lower().strip())
            if tab_name:
                query += " AND tab_name = ?"
                params.append(tab_name.strip())

            query += " ORDER BY id DESC LIMIT ?"
            try:
                safe_limit = max(1, min(int(limit), MAX_LIST_LIMIT))
            except (TypeError, ValueError):
                safe_limit = 200
            params.append(safe_limit)

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def update_issue_status(self, issue_id: int, status: str) -> bool:
        """Updates status of an issue (e.g. OPEN -> RESOLVED)."""
        status_clean = status.upper().strip()
        if status_clean not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if status_clean == "RESOLVED":
                cursor.execute(
                    """
                    UPDATE internal_sheet_issues
                    SET status = ?, resolved_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (status_clean, issue_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE internal_sheet_issues
                    SET status = ?, resolved_at = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (status_clean, issue_id),
                )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_issue(self, issue_id: int) -> bool:
        """Deletes an issue record."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM internal_sheet_issues WHERE id = ?", (issue_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def promote_to_gstack(self, issue_id: int) -> Optional[int]:
        """Promotes an existing issue to the G-Stack backlog if not already promoted."""
        issue = self.get_issue(issue_id)
        if not issue:
            return None
        if issue.get("gstack_task_id"):
            return issue["gstack_task_id"]

        spec = (
            f"[Visual Annotation #{issue_id}] Tab: {issue.get('tab_name')} | Selector: {issue.get('target_selector')}\n"
            f"Snippet: {issue.get('element_text_snippet') or 'N/A'}\n"
            f"Problem: {issue.get('description')}"
        )
        task_id = gstack_engine.add_backlog_task(
            role=issue.get("suggested_role", "ENGINEERING_MANAGER"),
            title=f"[{issue.get('category', 'BUG').upper()}] {issue.get('title')}",
            specification=spec,
            status="PENDING",
        )

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE internal_sheet_issues SET gstack_task_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (task_id, issue_id),
            )
            conn.commit()
            return task_id
        finally:
            conn.close()

    def export_csv(self) -> str:
        """
        Exports all internal sheet records as an RFC-4180 CSV string
        ready for direct import into Google Sheets or Microsoft Excel.
        """
        issues = self.list_issues(limit=2000)
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)

        # Header row
        writer.writerow([
            "Issue ID",
            "Status",
            "Severity",
            "Category",
            "Title",
            "Target Selector",
            "Element Tag",
            "Tab",
            "Problem Description",
            "Element Text Snippet",
            "Assigned Role",
            "G-Stack Task ID",
            "Created At",
            "Resolved At",
        ])

        for item in issues:
            writer.writerow([
                item.get("id"),
                item.get("status"),
                item.get("severity"),
                item.get("category"),
                item.get("title"),
                item.get("target_selector"),
                item.get("element_tag"),
                item.get("tab_name"),
                item.get("description"),
                item.get("element_text_snippet"),
                item.get("suggested_role"),
                item.get("gstack_task_id") or "",
                item.get("created_at"),
                item.get("resolved_at") or "",
            ])

        return output.getvalue()

    def get_summary_metrics(self) -> Dict[str, Any]:
        """Returns summary counts of open, resolved, and critical items."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT status, severity, COUNT(*) as cnt FROM internal_sheet_issues GROUP BY status, severity")
            rows = cursor.fetchall()
            total = 0
            open_count = 0
            resolved_count = 0
            critical_count = 0
            for r in rows:
                c = int(r["cnt"])
                total += c
                if r["status"] == "OPEN":
                    open_count += c
                    if r["severity"] == "critical":
                        critical_count += c
                elif r["status"] == "RESOLVED":
                    resolved_count += c

            return {
                "total": total,
                "open": open_count,
                "resolved": resolved_count,
                "critical": critical_count,
            }
        finally:
            conn.close()

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        if d.get("bounding_box") and isinstance(d["bounding_box"], str):
            try:
                d["bounding_box"] = json.loads(d["bounding_box"])
            except Exception:
                pass
        return d


internal_sheet_manager = InternalSheetManager()
