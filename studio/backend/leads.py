"""
Leads & Relationship CRM Service Layer
======================================
Manages high-value post engagers (commenters, reactors) across the conversion pipeline.
Stored in local SQLite table 'leads' with 0 cloud data leakage.

Lifecycle States:
- New Lead: Prospect recently commented/reacted on post.
- Outreach Sent: 1-on-1 direct message script sent.
- Connected: 1st-degree connection established on LinkedIn.
- Meeting Booked: Collaboration, consulting, or client discussion scheduled.
"""

import uuid
import re
from typing import List, Dict, Optional, Any
from datetime import datetime

try:
    from .database import get_db
except ImportError:
    from database import get_db


# -- Validation constants --------------------------------------------------
MAX_NAME_LENGTH = 200
MAX_HEADLINE_LENGTH = 500
MAX_COMPANY_LENGTH = 300
MAX_NOTES_LENGTH = 2000
MAX_BATCH_SIZE = 500
VALID_LEAD_STATUSES = {"New Lead", "Outreach Sent", "Connected", "Meeting Booked"}


def list_leads(status: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    
    query = "SELECT * FROM leads WHERE 1=1"
    params = []
    
    if status and status != "All":
        query += " AND status = ?"
        params.append(status)
        
    if search and search.strip():
        term = f"%{search.strip()}%"
        query += " AND (name LIKE ? OR company LIKE ? OR headline LIKE ? OR notes LIKE ?)"
        params.extend([term, term, term, term])
        
    query += " ORDER BY created_at DESC"
    
    c.execute(query, tuple(params))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def add_lead(lead_data: Dict) -> Dict:
    name = (lead_data.get("name") or "").strip()[:MAX_NAME_LENGTH]
    if not name:
        return {"status": "error", "message": "Name is required"}

    headline = (lead_data.get("headline") or "").strip()[:MAX_HEADLINE_LENGTH]
    company = (lead_data.get("company") or "").strip()[:MAX_COMPANY_LENGTH]
    notes = (lead_data.get("notes") or "").strip()[:MAX_NOTES_LENGTH]

    lead_id = lead_data.get("id") or f"lead_{uuid.uuid4().hex[:8]}"
    conn = get_db()
    c = conn.cursor()

    # Deduplicate if lead with same profile_url or exact name exists
    profile_url = (lead_data.get("profile_url") or "").strip()
    if profile_url:
        c.execute("SELECT id FROM leads WHERE profile_url = ?", (profile_url,))
        existing = c.fetchone()
        if existing:
            # Update notes or engagement if new comment
            c.execute("UPDATE leads SET engagement_type = ?, notes = ? WHERE id = ?", (
                lead_data.get("engagement_type", "Commented"),
                notes,
                existing["id"]
            ))
            conn.commit()
            conn.close()
            return {"status": "success", "id": existing["id"], "action": "updated"}
            
    c.execute("""
    INSERT INTO leads (id, name, headline, company, profile_url, engagement_type, post_id, status, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        lead_id,
        name,
        headline,
        company,
        profile_url,
        lead_data.get("engagement_type", "Commented"),
        lead_data.get("post_id", ""),
        lead_data.get("status", "New Lead"),
        notes
    ))
    conn.commit()
    conn.close()
    return {"status": "success", "id": lead_id, "action": "created"}


def batch_add_leads(leads_list: List[Dict]) -> Dict:
    """
    Ingests multiple leads captured passively or actively from LinkedIn.
    Safely ignores duplicates without raising errors.
    Capped at MAX_BATCH_SIZE (500) per request to prevent DB lock starvation.
    """
    if len(leads_list) > MAX_BATCH_SIZE:
        return {
            "status": "error",
            "message": f"Batch size {len(leads_list)} exceeds maximum of {MAX_BATCH_SIZE} leads per request"
        }
    conn = get_db()
    c = conn.cursor()
    added_count = 0
    updated_count = 0
    
    for l in leads_list:
        name = (l.get("name") or "").strip()
        if not name or len(name) < 2:
            continue
            
        profile_url = (l.get("profile_url") or "").strip()
        l_id = l.get("id") or f"lead_{uuid.uuid4().hex[:8]}"
        notes = l.get("notes") or "Captured live from LinkedIn engagement"
        headline = l.get("headline") or ""
        company = l.get("company") or ""
        
        # Extract company from headline if not provided
        if not company and headline:
            if " at " in headline:
                company = headline.split(" at ")[1].split("|")[0].split(",")[0].strip()
            elif " @ " in headline:
                company = headline.split(" @ ")[1].split("|")[0].split(",")[0].strip()
                
        # Check existing by profile_url or exact name
        existing_id = None
        if profile_url:
            c.execute("SELECT id FROM leads WHERE profile_url = ?", (profile_url,))
            row = c.fetchone()
            if row:
                existing_id = row["id"]
        if not existing_id:
            c.execute("SELECT id FROM leads WHERE name = ? AND headline = ?", (name, headline))
            row = c.fetchone()
            if row:
                existing_id = row["id"]
                
        if existing_id:
            c.execute("UPDATE leads SET engagement_type = ?, notes = ? WHERE id = ?", (
                l.get("engagement_type", "Commented"),
                notes,
                existing_id
            ))
            updated_count += 1
        else:
            c.execute("""
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
            added_count += 1
            
    conn.commit()
    conn.close()
    return {"status": "success", "added": added_count, "updated": updated_count}


def update_lead_status(lead_id: str, new_status: str, notes: Optional[str] = None) -> Dict:
    if new_status not in VALID_LEAD_STATUSES:
        return {
            "status": "error",
            "message": f"Invalid status '{new_status}'. Must be one of: {', '.join(sorted(VALID_LEAD_STATUSES))}"
        }
    conn = get_db()
    c = conn.cursor()
    if notes is not None:
        sanitized_notes = notes.strip()[:MAX_NOTES_LENGTH]
        c.execute("UPDATE leads SET status = ?, notes = ? WHERE id = ?", (new_status, sanitized_notes, lead_id))
    else:
        c.execute("UPDATE leads SET status = ? WHERE id = ?", (new_status, lead_id))
    updated = c.rowcount
    conn.commit()
    conn.close()
    if updated == 0:
        return {"status": "not_found", "id": lead_id}
    return {"status": "success", "id": lead_id, "new_status": new_status}


def delete_lead(lead_id: str) -> Dict:
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    if deleted == 0:
        return {"status": "not_found", "id": lead_id}
    return {"status": "success", "id": lead_id}


def generate_dm_script(lead_id: str, style: str = "value_add", post_topic: Optional[str] = None) -> Dict:
    """
    Generates a personalized, high-converting 1-on-1 direct message script
    tailored to the prospect's real company, headline, and engagement context.
    
    Styles:
    - value_add: Thoughtful technical / peer question based on their perspective.
    - resource_share: Offer a concrete architectural breakdown or PDF blueprint.
    - quick_chat: Casual 15-minute sync / virtual coffee to exchange engineering notes.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    lead = c.fetchone()
    conn.close()

    if not lead:
        return {"error": "Lead not found"}

    first_name = lead["name"].split()[0] if lead["name"] else "there"
    company = lead["company"] or "your team"
    headline = lead["headline"] or ""
    action_saw = "commented on" if lead["engagement_type"] == "Commented" else "reacted to"
    action_thanks = "commenting on" if lead["engagement_type"] == "Commented" else "reacting to"
    topic = post_topic or "enterprise systems and architecture"
    
    # Check if we have specific comment notes to reference
    notes = lead["notes"] or ""
    comment_ref = ""
    if "Commented:" in notes:
        # Extract quoted comment
        match = re.search(r'Commented:\s*"(.*?)"', notes)
        if match:
            extracted = match.group(1).strip()
            if len(extracted) > 10:
                comment_ref = f' Your point about "{extracted[:60]}..." really stood out.'

    if style == "resource_share":
        script = (
            f"Hi {first_name},\n\n"
            f"Thanks for {action_thanks} my recent post on {topic}!{comment_ref}\n\n"
            f"I recently put together a practical architecture blueprint and checklist detailing how engineering teams at organizations like {company} decouple critical systems without downtime.\n\n"
            f"Would you find it helpful if I sent the diagram over? Happy to drop the link right here."
        )
    elif style == "quick_chat":
        action_eng = "in the comments on" if lead["engagement_type"] == "Commented" else "engaging with"
        script = (
            f"Hi {first_name},\n\n"
            f"Great seeing you {action_eng} my post regarding {topic}!{comment_ref}\n\n"
            f"I have been following {company}'s trajectory and love connecting with fellow leaders navigating technical scale.\n\n"
            f"If you are ever open to a low-key 15-minute virtual coffee to swap notes on engineering architecture, I would love to connect."
        )
    else:  # value_add (default)
        script = (
            f"Hi {first_name},\n\n"
            f"Saw that you {action_saw} my recent post on {topic}. "
            f"Really appreciated your perspective!{comment_ref}\n\n"
            f"Curious how you and {company} are currently navigating foundational observability and decoupling logic as you scale?\n\n"
            f"Would love to exchange notes if you're open to connecting."
        )

    # Strict zero em-dash verification
    script = script.replace("\u2014", ", ").replace("--", ", ")

    return {
        "status": "success",
        "lead_name": lead["name"],
        "lead_company": company,
        "style": style,
        "profile_url": lead["profile_url"],
        "dm_script": script
    }


def export_leads_csv(status: Optional[str] = None, search: Optional[str] = None) -> str:
    """
    Exports leads as RFC-4180 compliant CSV string for CRM sync or manual outreach.
    """
    import csv
    import io
    leads = list_leads(status, search)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Name", "Headline", "Company", "Seniority Level",
        "ICP Score", "Qualification Tier", "Status", "Profile URL",
        "Engagement Type", "Notes", "Created At"
    ])
    for l in leads:
        score = float(l.get("icp_score") or 0.0)
        if score >= 80.0:
            tier = "TIER_1_VIP"
        elif score >= 60.0:
            tier = "QUALIFIED"
        elif score >= 30.0:
            tier = "NURTURE"
        else:
            tier = "DISQUALIFIED"

        writer.writerow([
            l.get("id", ""),
            l.get("full_name") or l.get("name", ""),
            l.get("headline", ""),
            l.get("company", ""),
            l.get("seniority_level", "Unknown"),
            f"{score:.1f}",
            tier,
            l.get("lead_status") or l.get("status", "NEW"),
            l.get("profile_url", ""),
            l.get("engagement_type", ""),
            l.get("notes", ""),
            l.get("created_at", "")
        ])
    return output.getvalue()
