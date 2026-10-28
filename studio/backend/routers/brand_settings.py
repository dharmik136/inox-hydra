"""
Brand and Settings: what the two screens split from Brand Studio read first.
=============================================================================

Brand opens on the profile as LinkedIn last showed it, each part with the
date it was read; Settings opens on an overview of what runs here and what
leaves (sections report, batch 5). Both read what other modules hold and
write nothing.

Strict Invariants:
- Zero em-dashes.
- Every value carries when it was read, or says it was not.
"""

from typing import Any, Dict

from fastapi import APIRouter

try:
    from ..database import get_db
    from .. import desktop, egress, licensing, retention, updates
except (ImportError, ValueError):
    from database import get_db
    import desktop
    import egress
    import licensing
    import retention
    import updates

router = APIRouter(tags=["Brand and Settings"])


@router.get("/api/v1/brand/profile")
def get_brand_profile() -> Dict[str, Any]:
    """
    Your profile as LinkedIn last showed it: the fields read together, with
    their one read date, and each role, school and skill with its own; and
    your follower and connection counts on the days they were read, never a
    seeded day. Nothing before you confirm which profile is yours.
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT vanity, display_name, headline, about, location, current_company, follower_count, "
            "connection_count, profile_observed_at, contact_observed_at, confirmed_at FROM creator_identity "
            "WHERE id = 1 AND confirmed_at IS NOT NULL").fetchone()
        if not row:
            return {"status": "success", "confirmed": False, "profile": None, "positions": [], "education": [],
                    "skills": [], "audience": []}
        positions = [dict(r) for r in conn.execute(
            "SELECT title, company, date_range, location, description, observed_at AS read_at "
            "FROM creator_positions ORDER BY ordinal")]
        education = [dict(r) for r in conn.execute(
            "SELECT school, degree, date_range, observed_at AS read_at FROM creator_education ORDER BY ordinal")]
        skills = [dict(r) for r in conn.execute(
            "SELECT skill, observed_at AS read_at FROM creator_skills ORDER BY skill")]
        audience = [dict(r) for r in conn.execute(
            "SELECT date, followers, connections FROM analytics_daily WHERE source = 'observed' "
            "AND (followers IS NOT NULL OR connections IS NOT NULL) ORDER BY date")]
    finally:
        conn.close()
    profile = {
        "vanity": row["vanity"], "name": row["display_name"], "headline": row["headline"], "about": row["about"],
        "location": row["location"], "company": row["current_company"], "followers": row["follower_count"],
        "connections": row["connection_count"],
        # One read of your own profile page writes these fields together.
        "read_at": row["profile_observed_at"], "confirmed_at": row["confirmed_at"],
    }
    return {"status": "success", "confirmed": True, "profile": profile, "positions": positions,
            "education": education, "skills": skills, "audience": audience}


@router.get("/api/v1/settings/overview")
def get_settings_overview() -> Dict[str, Any]:
    """
    The values Settings opens on, each from the module that owns it: the last
    backup and whether it was verified, what the next cleanup would remove,
    what has left this machine since the studio started, the licence's tier
    and end, the update check, and whether the studio starts with your
    computer.
    """
    backups = retention.backup_state(retention.rules())
    ledger = egress.describe()
    licence = licensing.current()
    held = licence.get("licence") or {}
    check = updates.describe()
    start = desktop.describe()
    return {
        "status": "success",
        "backup": {"enabled": backups.get("enabled"), "last": backups.get("last"), "next_due": backups.get("next_due"),
                   "stale": backups.get("stale"), "never": backups.get("never")},
        "cleanup": retention.next_cleanup(),
        "egress": {"total_performed": ledger["total_performed"], "total_refused": ledger["total_refused"],
                   "master_off": ledger["master_off"], "since": "the studio started"},
        "licence": {"status": licence.get("status"), "tier_label": licence.get("tier_label"),
                    "expires_at": held.get("expires_at"), "updates_until": held.get("updates_until")},
        "updates": {"enabled": check.get("enabled"), "last_checked": check.get("last_checked"),
                    "last_seen_version": check.get("last_seen_version"), "current_version": check.get("current_version")},
        "autostart": {"supported": bool(start.get("supported")), "enabled": bool(start.get("autostart_enabled")),
                      "available": bool(start.get("autostart_available")), "platform": start.get("platform")},
    }
