"""
Enterprise Multi-Tenant Creator Profile Management.
===================================================

Provides profile isolation and account switching for creators and agencies
managing multiple LinkedIn profiles from a single local Inox Hydra instance.

Invariants:
- Zero literal em-dashes across all code, docstrings, and comments.
- 'default' account cannot be deleted.
- Data across drafts, posts, leads, and lead_interactions are scoped by account_id.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from .database import get_db
except ImportError:
    from database import get_db


MAX_ACCOUNT_NAME_LENGTH = 120
MAX_HEADLINE_LENGTH = 300
MAX_VANITY_LENGTH = 100


def _compute_initials(name: str) -> str:
    """Computes a clean 2-character initials string from a person's or brand's name."""
    clean = re.sub(r"[^\w\s]", "", (name or "").strip())
    parts = clean.split()
    if not parts:
        return "CR"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def get_active_account_id(conn=None) -> str:
    """
    Returns the currently active account_id from local settings.
    Falls back to 'default' if not configured or if the recorded account does not exist.
    """
    close_after = False
    if conn is None:
        conn = get_db()
        close_after = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'active_account_id'")
        row = cursor.fetchone()
        if not row or not row["value"]:
            return "default"

        active_id = str(row["value"]).strip()
        cursor.execute("SELECT id FROM creator_accounts WHERE id = ?", (active_id,))
        if cursor.fetchone():
            return active_id
        return "default"
    finally:
        if close_after:
            conn.close()


def set_active_account_id(account_id: str, conn=None) -> str:
    """Sets the active account_id in local settings."""
    close_after = False
    if conn is None:
        conn = get_db()
        close_after = True

    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_account_id', ?)",
            (account_id,),
        )
        conn.commit()
        return account_id
    finally:
        if close_after:
            conn.close()


def list_accounts(conn=None) -> Dict[str, Any]:
    """
    Lists all creator profile accounts, their summary metrics, and the active profile.
    """
    close_after = False
    if conn is None:
        conn = get_db()
        close_after = True

    try:
        cursor = conn.cursor()
        active_id = get_active_account_id(conn=conn)

        # Ensure default account exists
        cursor.execute("SELECT COUNT(*) FROM creator_accounts WHERE id = 'default'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT OR IGNORE INTO creator_accounts (id, name, vanity, headline, avatar_initials, is_default)
                VALUES ('default', 'Default Profile', '', 'Creator', 'DP', 1)
            """)
            conn.commit()

        cursor.execute("""
            SELECT id, name, vanity, headline, avatar_initials, is_default, created_at, updated_at
            FROM creator_accounts
            ORDER BY is_default DESC, created_at ASC
        """)
        rows = cursor.fetchall()
        accounts: List[Dict[str, Any]] = []

        for r in rows:
            acc_id = r["id"]

            # Quick metric aggregates per account
            cursor.execute("SELECT COUNT(*) FROM posts WHERE account_id = ?", (acc_id,))
            posts_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM drafts WHERE account_id = ?", (acc_id,))
            drafts_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM leads WHERE account_id = ?", (acc_id,))
            leads_count = cursor.fetchone()[0]

            accounts.append({
                "id": acc_id,
                "name": r["name"],
                "vanity": r["vanity"] or "",
                "headline": r["headline"] or "",
                "avatar_initials": r["avatar_initials"] or _compute_initials(r["name"]),
                "is_default": bool(r["is_default"]),
                "is_active": acc_id == active_id,
                "created_at": r["created_at"],
                "posts_count": posts_count,
                "drafts_count": drafts_count,
                "leads_count": leads_count,
            })

        return {
            "status": "success",
            "accounts": accounts,
            "active_account_id": active_id,
        }
    finally:
        if close_after:
            conn.close()


def get_account(account_id: str, conn=None) -> Optional[Dict[str, Any]]:
    """Retrieves a single creator account record."""
    close_after = False
    if conn is None:
        conn = get_db()
        close_after = True

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, vanity, headline, avatar_initials, is_default, created_at, updated_at
            FROM creator_accounts
            WHERE id = ?
        """, (account_id,))
        row = cursor.fetchone()
        if not row:
            return None

        active_id = get_active_account_id(conn=conn)
        return {
            "id": row["id"],
            "name": row["name"],
            "vanity": row["vanity"] or "",
            "headline": row["headline"] or "",
            "avatar_initials": row["avatar_initials"] or _compute_initials(row["name"]),
            "is_default": bool(row["is_default"]),
            "is_active": row["id"] == active_id,
            "created_at": row["created_at"],
        }
    finally:
        if close_after:
            conn.close()


def create_account(data: Dict[str, Any], conn=None) -> Dict[str, Any]:
    """
    Creates a new creator account profile in the studio.
    """
    name = (data.get("name") or "").strip()[:MAX_ACCOUNT_NAME_LENGTH]
    if not name:
        return {"status": "error", "message": "Account name is required"}

    headline = (data.get("headline") or "").strip()[:MAX_HEADLINE_LENGTH]
    vanity = (data.get("vanity") or "").strip()[:MAX_VANITY_LENGTH]

    # Generate an account identifier
    suggested_id = (data.get("id") or "").strip()
    if suggested_id:
        acc_id = re.sub(r"[^\w\-]", "", suggested_id).lower()
    else:
        slug = re.sub(r"[^\w]+", "-", name.lower()).strip("-")[:24]
        acc_id = f"{slug}-{uuid.uuid4().hex[:6]}" if slug else f"acc-{uuid.uuid4().hex[:8]}"

    initials = _compute_initials(name)
    now_iso = datetime.now(timezone.utc).isoformat()

    close_after = False
    if conn is None:
        conn = get_db()
        close_after = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM creator_accounts WHERE id = ?", (acc_id,))
        if cursor.fetchone():
            return {"status": "error", "message": f"Account ID '{acc_id}' already exists"}

        cursor.execute("""
            INSERT INTO creator_accounts (id, name, vanity, headline, avatar_initials, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        """, (acc_id, name, vanity, headline, initials, now_iso, now_iso))
        conn.commit()

        account = {
            "id": acc_id,
            "name": name,
            "vanity": vanity,
            "headline": headline,
            "avatar_initials": initials,
            "is_default": False,
            "is_active": False,
            "created_at": now_iso,
            "posts_count": 0,
            "drafts_count": 0,
            "leads_count": 0,
        }
        return {"status": "success", "account": account}
    finally:
        if close_after:
            conn.close()


def switch_account(account_id: str, conn=None) -> Dict[str, Any]:
    """
    Switches active profile to the target account_id.
    """
    close_after = False
    if conn is None:
        conn = get_db()
        close_after = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM creator_accounts WHERE id = ?", (account_id,))
        row = cursor.fetchone()
        if not row:
            return {"status": "error", "message": f"Account '{account_id}' does not exist"}

        set_active_account_id(account_id, conn=conn)
        account = get_account(account_id, conn=conn)

        return {
            "status": "success",
            "active_account_id": account_id,
            "account": account,
        }
    finally:
        if close_after:
            conn.close()


def delete_account(account_id: str, conn=None) -> Dict[str, Any]:
    """
    Deletes a creator account profile. Refuses to delete 'default'.
    If the active account is deleted, active account is switched back to 'default'.
    """
    if account_id == "default":
        return {"status": "error", "message": "Cannot delete the default system profile"}

    close_after = False
    if conn is None:
        conn = get_db()
        close_after = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM creator_accounts WHERE id = ?", (account_id,))
        if not cursor.fetchone():
            return {"status": "error", "message": f"Account '{account_id}' not found"}

        active_id = get_active_account_id(conn=conn)
        if active_id == account_id:
            set_active_account_id("default", conn=conn)

        cursor.execute("DELETE FROM creator_accounts WHERE id = ?", (account_id,))
        conn.commit()

        return {
            "status": "success",
            "message": f"Account '{account_id}' deleted successfully",
            "active_account_id": get_active_account_id(conn=conn),
        }
    finally:
        if close_after:
            conn.close()
