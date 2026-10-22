"""
CRM and Audience Graph API Router
=================================
Inbound lead management, ICP scoring, contact status events, anti-slop DMs,
and interaction history. Zero cloud egress.
"""

import uuid
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

try:
    from ..database import get_db
    from ..leads import (
        list_leads,
        page_leads,
        add_lead,
        batch_add_leads,
        update_lead_status,
        update_lead_notes,
        delete_lead,
        generate_dm_script,
        export_leads_csv,
    )
    from ..crm import ICPScoringEngine, ReverseCRMManager, reverse_crm, qualification_tier
    from .. import onboarding, retention, ingest_contract
except (ImportError, ValueError):
    from database import get_db
    from leads import (
        list_leads,
        page_leads,
        add_lead,
        batch_add_leads,
        update_lead_status,
        update_lead_notes,
        delete_lead,
        generate_dm_script,
        export_leads_csv,
    )
    from crm import ICPScoringEngine, ReverseCRMManager, reverse_crm, qualification_tier
    import onboarding
    import retention
    import ingest_contract

router = APIRouter()


class LeadStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


class LeadNotesUpdate(BaseModel):
    notes: str


class IngestInteractionRequest(BaseModel):
    """One engagement on one post, in the shape ingest_contract documents."""
    full_name: Optional[str] = "Unknown"
    linkedin_urn: Optional[str] = None
    profile_url: Optional[str] = None
    headline: Optional[str] = ""
    company: Optional[str] = None
    interaction_type: Optional[str] = "COMMENT"
    comment_text: Optional[str] = None
    post_urn: Optional[str] = None
    # The studio's own post key, which is TEXT. This was declared
    # Optional[int] for a TEXT column, so a client sending a correct
    # "post-<hex12>" got a 422 and its capture was lost outright. post_id
    # stays as the deprecated alias an extension that has not been reloaded
    # sends, and is read as TEXT too.
    post_key: Optional[str] = None
    post_id: Optional[str] = None
    post_topic: Optional[str] = None
    capture_context: Optional[str] = None
    post_author: Optional[str] = None
    extension_version: Optional[str] = None
    contract_version: Optional[int] = None


class GenerateDMRequest(BaseModel):
    lead_name: str
    comment_text: str
    post_topic: Optional[str] = None
    custom_insight: Optional[str] = None


class LeadRemoval(BaseModel):
    lead_ids: List[str]


_ENRICHMENT_RETIRED = (
    "Lead enrichment is retired. It guessed a company's technology and problems "
    "from the person's job title and presented the guess as research. The "
    "dossier shows what the studio actually knows about this person."
)


@router.get("/api/leads")
def get_leads(status: Optional[str] = None, search: Optional[str] = None, limit: Optional[int] = None,
              cursor: Optional[str] = None, q: Optional[str] = None):
    """
    Every lead, or with limit, one page of them: the Leads screen asks for
    200 at a time and filters on the server (q, status), with next_cursor
    for the next page and how many match and exist in all.
    """
    if limit is None:
        return {"status": "success", "leads": list_leads(status, search)}
    return {"status": "success", **page_leads(status, q, limit, cursor)}


@router.get("/api/leads/export/csv", tags=["Inbound CRM"])
def export_leads_csv_route(status: Optional[str] = None, search: Optional[str] = None):
    csv_data = export_leads_csv(status, search)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=linkedin_studio_crm_leads.csv"}
    )


@router.put("/api/leads/{lead_id}/status")
def update_lead(lead_id: str, payload: LeadStatusUpdate):
    result = update_lead_status(lead_id, payload.status, payload.notes)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.patch("/api/leads/{lead_id}")
def edit_lead_notes(lead_id: str, payload: LeadNotesUpdate):
    """The creator's notes on a lead, from the dossier, without touching the stage."""
    result = update_lead_notes(lead_id, payload.notes)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")
    return result


@router.delete("/api/leads/{lead_id}")
def remove_lead(lead_id: str):
    result = delete_lead(lead_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")
    return result


@router.get("/api/leads/{lead_id}/dm-script")
def get_lead_dm(lead_id: str, style: Optional[str] = "value_add", topic: Optional[str] = None,
                offer: Optional[str] = None):
    return generate_dm_script(lead_id, style=style, post_topic=topic, offer=offer)


@router.post("/api/leads/{lead_id}/enrich", tags=["Leads & CRM"])
def enrich_lead_endpoint(lead_id: str):
    raise HTTPException(status_code=410, detail=_ENRICHMENT_RETIRED)


@router.get("/api/leads/{lead_id}/enrichment", tags=["Leads & CRM"])
def get_lead_enrichment_endpoint(lead_id: str):
    raise HTTPException(status_code=410, detail=_ENRICHMENT_RETIRED)


@router.post("/api/v1/crm/interactions/ingest", tags=["Enterprise Reverse CRM"])
def ingest_crm_interaction(req: IngestInteractionRequest):
    """
    One engagement on one of the creator's posts. Answers one of the three
    outcomes in ingest_contract: accepted, nothing_new, or 409 refused.

    Every decline used to be 200 {"status": "skipped"}, including "confirm
    your profile in Setup first", so a creator scrolled their own post, saw
    nothing happen, and had no way to learn why.
    """
    ingest_contract.note_client(req.extension_version, req.contract_version)
    refused = onboarding.engagement_gate(req.linkedin_urn or req.profile_url, req.post_urn, req.post_author)
    verdict = ingest_contract.classify(refused)
    if verdict:
        reason, outcome = verdict
        if outcome == ingest_contract.REFUSED:
            ingest_contract.refuse(reason, refused)
        return ingest_contract.nothing_new(reason, refused)
    urn = req.linkedin_urn or req.profile_url or f"local:unresolved:{uuid.uuid4().hex[:12]}"
    raw_type = (req.interaction_type or "COMMENT").upper()
    if "COMMENT" in raw_type:
        norm_type = "COMMENT"
    elif "LIKE" in raw_type:
        norm_type = "LIKE"
    elif "REPOST" in raw_type:
        norm_type = "REPOST"
    else:
        norm_type = "COMMENT"

    # One writer for a burst. Thirty engagers of one post arrive at once and
    # used to race for the database lock through SQLite's polling busy
    # handler, so each waited for the whole queue: 6,047 ms of wall time
    # against 1,318 ms for the same thirty one at a time. Taking a turn costs
    # one hand-off and removes the contention.
    #
    # post_id is deliberately not passed on. lead_interactions.post_id is an
    # INTEGER foreign key into drafts(id) and can never match a posts.id, so
    # writing the studio's own key there stored a value nothing can join;
    # post_urn is what every attribution surface reads.
    result = ingest_contract.through_the_writer(
        "Capturing an engagement",
        reverse_crm.ingest_interaction,
        full_name=req.full_name,
        linkedin_urn=urn,
        headline=req.headline,
        company=req.company,
        interaction_type=norm_type,
        comment_text=req.comment_text,
        post_urn=req.post_urn,
        post_id=None,
        post_topic=req.post_topic,
        capture_context=req.capture_context,
    )
    result["id"] = result.get("lead_id")
    result["qualification_tier"] = result.get("tier")
    return ingest_contract.accepted(interaction=result, lead=result,
                                    post_key=ingest_contract.post_key_of(req.model_dump()))


@router.post("/api/v1/crm/leads/generate-dm", tags=["Enterprise Reverse CRM"])
def generate_lead_dm(req: GenerateDMRequest):
    dm = ICPScoringEngine.generate_contextual_dm(
        lead_name=req.lead_name,
        comment_text=req.comment_text,
        post_topic=req.post_topic,
        custom_insight=req.custom_insight,
    )
    return {"status": "success", "suggested_dm": dm}


@router.delete("/api/v1/crm/leads/{lead_id}/purge", tags=["Enterprise Reverse CRM"])
def purge_crm_lead(lead_id: str):
    res = reverse_crm.purge_lead(lead_id)
    if not res["lead_deleted"]:
        raise HTTPException(status_code=404, detail="Lead not found")
    return res


@router.get("/api/v1/crm/leads/{lead_id}/timeline", tags=["Enterprise Reverse CRM"])
def get_lead_interaction_timeline(lead_id: str):
    res = reverse_crm.get_lead_timeline(lead_id)
    if res["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Lead not found")
    res["interactions"] = onboarding.annotate_interactions(res["interactions"])
    # Reactions older than 24 months that retention folded into counts: how
    # many, and on whose posts; which posts is no longer kept.
    res["folded_reactions"] = retention.folded_for_lead(lead_id)
    # Whether the lead was scored at all, and its tier under the one rule. A
    # captured lead is scored at capture, and a student's 0 is a score; only a
    # lead added by hand, with nothing captured, has none. The dossier read
    # every 0 as "Not scored".
    res["lead"]["scored"] = (bool(res["interactions"]) or bool(res["folded_reactions"])
                             or float(res["lead"].get("icp_score") or 0) > 0)
    res["lead"]["qualification_tier"] = qualification_tier(res["lead"].get("icp_score"))
    conn = get_db()
    try:
        res["stage_history"] = [dict(r) for r in conn.execute(
            "SELECT from_status, to_status, changed_at FROM lead_stage_events WHERE lead_id = ? ORDER BY changed_at",
            (lead_id,))]
    finally:
        conn.close()
    return res


@router.get("/api/v1/leads/review", tags=["Leads & CRM"])
def get_lead_review():
    return onboarding.lead_review()


@router.post("/api/v1/leads/review/remove", tags=["Leads & CRM"])
def post_lead_review_remove(payload: LeadRemoval):
    try:
        return onboarding.remove_leads_not_on_your_posts(payload.lead_ids)
    except onboarding.RefusedCapture as error:
        raise HTTPException(status_code=409, detail=str(error))
