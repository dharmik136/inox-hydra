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
    from . import devtools
except ImportError:
    from database import get_db
    from gstack_governance import gstack_engine
    import devtools

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
        tab_id: Optional[str] = None,
        section_hint: Optional[str] = None,
        ancestor_ids: Optional[List[str]] = None,
        capture: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Creates a new internal sheet issue / concept record.

        The caller supplies the human part. Everything else that makes the
        record reproducible a week later is derived here rather than trusted
        from the browser: the screen and section are resolved through the
        registry, the capture bundle is bounded and scrubbed, and the build and
        schema are read from this process.

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

        # Resolved rather than accepted. The browser reports where it was, this
        # decides what that means, so a renamed tab cannot quietly invent a
        # screen that the registry has never heard of.
        screen_key, section_key = devtools.resolve_location(
            tab_id=tab_id,
            section_hint=section_hint,
            ancestor_ids=ancestor_ids,
        )
        clean_capture = devtools.normalize_capture(capture)
        env_snapshot = devtools.environment_snapshot()
        repro_hash = devtools.repro_fingerprint(
            screen_key, section_key, category_clean, clean_capture["console"]
        )

        # The backlog task is created AFTER the issue row exists.
        #
        # It used to be created first, in its own transaction, before this
        # function had even opened a connection. A locked database during the
        # insert below therefore left a PENDING task whose gstack_task_id
        # pointed at no issue, and every retry added another one. The task is
        # the derived record; it should not outlive the thing it derives from.
        gstack_task_id = None

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
                    screen_key, section_key, console_capture, network_capture,
                    breadcrumbs, env_snapshot, a11y_findings, repro_hash,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
                    screen_key,
                    section_key,
                    json.dumps(clean_capture["console"]),
                    json.dumps(clean_capture["network"]),
                    json.dumps(clean_capture["breadcrumbs"]),
                    json.dumps(env_snapshot),
                    json.dumps(clean_capture["a11y"]),
                    repro_hash,
                ),
            )
            issue_id = cursor.lastrowid
            conn.commit()
        finally:
            conn.close()

        if promote_to_backlog:
            # promote_to_gstack builds the same specification and writes the
            # resulting id back onto the row, so there is one code path that
            # creates a backlog task rather than two that can disagree.
            self.promote_to_gstack(issue_id)

        return self.get_issue(issue_id)

    def _backlog_specification(
        self,
        screen_key: str,
        section_key: str,
        target_selector: str,
        snippet: Optional[str],
        description: str,
        capture: Dict[str, Any],
        env_snapshot: Dict[str, Any],
        issue_id: Optional[int] = None,
    ) -> str:
        """
        The text a maintainer actually reads when they pick the task up.

        Location comes first because it is the only part that stays true, then
        the problem, then the machine evidence. Console and breadcrumb lines are
        capped so a chatty page cannot bury the description under its own noise.
        """
        heading = f"[Visual Annotation{f' #{issue_id}' if issue_id else ''}]"
        lines = [
            f"{heading} Screen: {screen_key} | Section: {section_key}",
            f"Selector at capture: {target_selector}",
            f"Build: {env_snapshot.get('app_version')} | Schema: {env_snapshot.get('schema_version')}",
            "",
            f"Problem: {description}",
        ]
        if snippet:
            lines.append(f"Element text: {snippet}")

        breadcrumbs = capture.get("breadcrumbs") or []
        if breadcrumbs:
            lines.append("")
            lines.append("Steps before capture:")
            for crumb in breadcrumbs[-8:]:
                lines.append(f"  {crumb.get('kind', 'event')}: {crumb.get('label', '')}")

        console = [c for c in (capture.get("console") or []) if (c.get("level") or "").lower() in ("error", "warn")]
        if console:
            lines.append("")
            lines.append("Console:")
            for entry in console[-5:]:
                lines.append(f"  [{entry.get('level')}] {entry.get('message', '')}")

        failures = [n for n in (capture.get("network") or []) if str(n.get("status") or "").startswith(("4", "5"))]
        if failures:
            lines.append("")
            lines.append("Failed requests:")
            for entry in failures[-5:]:
                lines.append(f"  {entry.get('status')} {entry.get('method', '')} {entry.get('url', '')}")

        a11y = capture.get("a11y") or []
        if a11y:
            lines.append("")
            lines.append("Accessibility findings on the element:")
            for entry in a11y[-6:]:
                lines.append(f"  {entry.get('rule')}: {entry.get('detail', '')}")

        return "\n".join(lines)

    def find_duplicates(self, repro_hash: str, exclude_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Other records describing the same failure in the same place.

        Two people annotating one broken card should end up looking at one
        ticket, not filing a second one nobody notices is the same.
        """
        if not repro_hash:
            return []
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if exclude_id is None:
                cursor.execute(
                    "SELECT * FROM internal_sheet_issues WHERE repro_hash = ? ORDER BY id DESC LIMIT 20",
                    (repro_hash,),
                )
            else:
                cursor.execute(
                    "SELECT * FROM internal_sheet_issues WHERE repro_hash = ? AND id != ? ORDER BY id DESC LIMIT 20",
                    (repro_hash, exclude_id),
                )
            return [self._row_to_dict(r) for r in cursor.fetchall()]
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

        spec = self._backlog_specification(
            screen_key=issue.get("screen_key") or issue.get("tab_name") or "unknown",
            section_key=issue.get("section_key") or "unknown",
            target_selector=issue.get("target_selector") or "",
            snippet=issue.get("element_text_snippet"),
            description=issue.get("description") or "",
            capture={
                "console": issue.get("console_capture") or [],
                "network": issue.get("network_capture") or [],
                "breadcrumbs": issue.get("breadcrumbs") or [],
                "a11y": issue.get("a11y_findings") or [],
            },
            env_snapshot=issue.get("env_snapshot") or {},
            issue_id=issue_id,
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

        # Header row. Screen and section lead, because a spreadsheet sorted by
        # selector groups nothing useful, and one sorted by screen groups the
        # work by the person who owns it.
        writer.writerow([
            "Issue ID",
            "Status",
            "Severity",
            "Category",
            "Screen",
            "Section",
            "Title",
            "Problem Description",
            "Repro Hash",
            "Build",
            "Schema",
            "Console Errors",
            "Failed Requests",
            "Target Selector",
            "Element Tag",
            "Element Text Snippet",
            "Assigned Role",
            "G-Stack Task ID",
            "Created At",
            "Resolved At",
        ])

        for item in issues:
            env = item.get("env_snapshot") or {}
            console = item.get("console_capture") or []
            network = item.get("network_capture") or []
            error_count = sum(
                1 for c in console if isinstance(c, dict) and (c.get("level") or "").lower() == "error"
            )
            failure_count = sum(
                1 for n in network if isinstance(n, dict) and str(n.get("status") or "").startswith(("4", "5"))
            )
            writer.writerow([
                item.get("id"),
                item.get("status"),
                item.get("severity"),
                item.get("category"),
                item.get("screen_key") or "",
                item.get("section_key") or "",
                item.get("title"),
                item.get("description"),
                item.get("repro_hash") or "",
                env.get("app_version", "") if isinstance(env, dict) else "",
                env.get("schema_version", "") if isinstance(env, dict) else "",
                error_count,
                failure_count,
                item.get("target_selector"),
                item.get("element_tag"),
                item.get("element_text_snippet"),
                item.get("suggested_role"),
                item.get("gstack_task_id") or "",
                item.get("created_at"),
                item.get("resolved_at") or "",
            ])

        return output.getvalue()

    # Fields carried across an export. Local identifiers are deliberately not in
    # this list: an id and a G-Stack task number mean nothing on the machine
    # importing them, and carrying them would collide with real rows there.
    _PORTABLE_FIELDS = (
        "target_selector",
        "element_tag",
        "element_id",
        "element_classes",
        "element_text_snippet",
        "tab_name",
        "page_route",
        "category",
        "severity",
        "title",
        "description",
        "suggested_role",
        "status",
        "bounding_box",
        "viewport_resolution",
        "dom_path",
        "screen_key",
        "section_key",
        "console_capture",
        "network_capture",
        "breadcrumbs",
        "env_snapshot",
        "a11y_findings",
        "repro_hash",
        "created_at",
    )

    def export_json(self) -> Dict[str, Any]:
        """
        A lossless, re-importable dump. CSV is for reading in a spreadsheet and
        throws away the capture bundles; this is for moving a maintainer's
        annotations onto another machine without losing the evidence.
        """
        issues = self.list_issues(limit=MAX_LIST_LIMIT)
        return {
            "format": "inox-internal-sheet",
            "format_version": 1,
            "exported_from": devtools.environment_snapshot(),
            "count": len(issues),
            "issues": [
                {field: issue.get(field) for field in self._PORTABLE_FIELDS}
                for issue in issues
            ],
        }

    def import_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merges an exported sheet into this database.

        Rows already present under the same repro hash and title are skipped
        rather than duplicated, so importing the same file twice is a no-op.
        Anything malformed is counted and reported instead of aborting the run,
        because one bad row should not cost the other two hundred.
        """
        if not isinstance(payload, dict) or payload.get("format") != "inox-internal-sheet":
            raise ValueError("not an internal sheet export")

        incoming = payload.get("issues")
        if not isinstance(incoming, list):
            raise ValueError("export contains no issues list")

        imported = 0
        skipped = 0
        rejected = 0

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            for raw in incoming:
                if not isinstance(raw, dict):
                    rejected += 1
                    continue
                title = (raw.get("title") or "").strip()
                selector = (raw.get("target_selector") or "").strip()
                if not title or not selector:
                    rejected += 1
                    continue

                repro = raw.get("repro_hash") or ""
                cursor.execute(
                    "SELECT id FROM internal_sheet_issues WHERE repro_hash = ? AND title = ?",
                    (repro, title),
                )
                if cursor.fetchone():
                    skipped += 1
                    continue

                # Only fields the export actually carried. Writing NULL for an
                # absent one would override a NOT NULL column default and get
                # the whole row refused, which would make any export written by
                # an older build unimportable.
                present = []
                values = []
                for field in self._PORTABLE_FIELDS:
                    if raw.get(field) is None:
                        continue
                    value = raw[field]
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value)
                    present.append(field)
                    values.append(value)

                placeholders = ", ".join("?" for _ in present)
                columns = ", ".join(present)
                try:
                    cursor.execute(
                        f"INSERT INTO internal_sheet_issues ({columns}, updated_at) "
                        f"VALUES ({placeholders}, CURRENT_TIMESTAMP)",
                        tuple(values),
                    )
                    imported += 1
                except sqlite3.Error:
                    # A CHECK constraint rejecting an unknown category or
                    # severity lands here. The row is refused, the import lives.
                    rejected += 1

            conn.commit()
        finally:
            conn.close()

        return {"imported": imported, "skipped": skipped, "rejected": rejected}

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

    # Columns holding JSON. Decoded on read so a caller never has to know which
    # fields were serialised on the way in.
    _JSON_COLUMNS = (
        "bounding_box",
        "console_capture",
        "network_capture",
        "breadcrumbs",
        "env_snapshot",
        "a11y_findings",
    )

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        for column in self._JSON_COLUMNS:
            value = d.get(column)
            if value and isinstance(value, str):
                try:
                    d[column] = json.loads(value)
                except Exception:
                    pass
        return d


internal_sheet_manager = InternalSheetManager()
