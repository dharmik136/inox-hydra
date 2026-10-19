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
        add_lead,
        batch_add_leads,
        update_lead_status,
        delete_lead,
        generate_dm_script,
        export_leads_csv,
    )
    from ..crm import ICPScoringEngine, ReverseCRMManager, reverse_crm, qualification_tier
    from .. import onboarding
except (ImportError, ValueError):
    from database import get_db
    from leads import (
        list_leads,
        add_lead,
        batch_add_leads,
        update_lead_status,
        delete_lead,
        generate_dm_script,
        export_leads_csv,
    )
    from crm import ICPScoringEngine, ReverseCRMManager, reverse_crm, qualification_tier
    import onboarding

router = APIRouter()


class LeadCreate(BaseModel):
    name: str
    headline: Optional[str] = ""
    company: Optional[str] = ""
    profile_url: Optional[str] = ""
    engagement_type: Optional[str] = "Commented"
    post_id: Optional[str] = ""
    status: Optional[str] = "New Lead"
    notes: Optional[str] = ""


class LeadStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


class IngestInteractionRequest(BaseModel):
    full_name: Optional[str] = "Unknown"
    linkedin_urn: Optional[str] = None
    profile_url: Optional[str] = None
    headline: Optional[str] = ""
    company: Optional[str] = None
    interaction_type: Optional[str] = "COMMENT"
    comment_text: Optional[str] = None
    post_urn: Optional[str] = None
    post_id: Optional[int] = None
    post_topic: Optional[str] = None
    capture_context: Optional[str] = None
    post_author: Optional[str] = None


class GenerateDMRequest(BaseModel):
    lead_name: str
    comment_text: str
    post_topic: Optional[str] = None
    custom_insight: Optional[str] = None


class ScorePreviewRequest(BaseModel):
    headline: Optional[str] = ""
    company: Optional[str] = None
    comment_text: Optional[str] = None
    interaction_type: Optional[str] = "COMMENT"


class ArchiveInactiveRequest(BaseModel):
    inactive_days: int = 90


class LeadRemoval(BaseModel):
    lead_ids: List[str]


_ENRICHMENT_RETIRED = (
    "Lead enrichment is retired. It guessed a company's technology and problems "
    "from the person's job title and presented the guess as research. The "
    "dossier shows what the studio actually knows about this person."
)


@router.get("/api/leads")
def get_leads(status: Optional[str] = None, search: Optional[str] = None):
    return {"status": "success", "leads": list_leads(status, search)}


@router.get("/api/v1/crm/leads/export-csv", tags=["Enterprise Reverse CRM"])
@router.get("/api/leads/export/csv", tags=["Inbound CRM"])
def export_leads_csv_route(status: Optional[str] = None, search: Optional[str] = None):
    csv_data = export_leads_csv(status, search)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=linkedin_studio_crm_leads.csv"}
    )


@router.post("/api/leads")
def create_lead(lead: LeadCreate):
    data = lead.model_dump() if hasattr(lead, "model_dump") else lead.dict()
    return add_lead(data)


@router.post("/api/leads/batch")
def create_leads_batch(payload: Dict[str, Any]):
    leads_list = payload.get("leads", [])
    result = batch_add_leads(leads_list)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.put("/api/leads/{lead_id}/status")
def update_lead(lead_id: str, payload: LeadStatusUpdate):
    result = update_lead_status(lead_id, payload.status, payload.notes)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"Lead '{lead_id}' not found")
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])
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
    refused = onboarding.engagement_gate(req.linkedin_urn or req.profile_url, req.post_urn, req.post_author)
    if refused:
        return {"status": "skipped", "reason": refused}
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

    result = reverse_crm.ingest_interaction(
        full_name=req.full_name,
        linkedin_urn=urn,
        headline=req.headline,
        company=req.company,
        interaction_type=norm_type,
        comment_text=req.comment_text,
        post_urn=req.post_urn,
        post_id=req.post_id,
        post_topic=req.post_topic,
        capture_context=req.capture_context,
    )
    result["id"] = result.get("lead_id")
    result["qualification_tier"] = result.get("tier")
    return {"status": "success", "interaction": result, "lead": result}


@router.get("/api/v1/crm/leads/high-value", tags=["Enterprise Reverse CRM"])
def get_high_value_leads(min_score: float = 60.0, limit: int = 50):
    leads = reverse_crm.list_high_value_leads(min_icp_score=min_score, limit=limit)
    return {"status": "success", "count": len(leads), "leads": leads}


@router.get("/api/v1/crm/telemetry", tags=["Enterprise Reverse CRM"])
def get_crm_telemetry():
    return reverse_crm.get_crm_telemetry()


@router.post("/api/v1/crm/leads/generate-dm", tags=["Enterprise Reverse CRM"])
def generate_lead_dm(req: GenerateDMRequest):
    dm = ICPScoringEngine.generate_contextual_dm(
        lead_name=req.lead_name,
        comment_text=req.comment_text,
        post_topic=req.post_topic,
        custom_insight=req.custom_insight,
    )
    return {"status": "success", "suggested_dm": dm}


@router.post("/api/v1/crm/dm/variants", tags=["Enterprise Reverse CRM"])
def generate_anti_slop_dm_variants(req: GenerateDMRequest):
    variants = ICPScoringEngine.generate_anti_slop_dm_variants(
        lead_name=req.lead_name,
        comment_text=req.comment_text,
        post_topic=req.post_topic,
        custom_insight=req.custom_insight,
    )
    return {"status": "success", "variants": variants}


@router.post("/api/v1/crm/score-preview", tags=["Enterprise Reverse CRM"])
def preview_icp_score(req: ScorePreviewRequest):
    breakdown = ICPScoringEngine.calculate_icp_breakdown(
        headline=req.headline,
        company=req.company,
        comment_text=req.comment_text,
        interaction_type=req.interaction_type or "COMMENT",
    )
    return {
        "status": "success",
        **breakdown,
    }


@router.delete("/api/v1/crm/leads/{lead_id}/purge", tags=["Enterprise Reverse CRM"])
def purge_crm_lead(lead_id: str):
    res = reverse_crm.purge_lead(lead_id)
    if not res["lead_deleted"]:
        raise HTTPException(status_code=404, detail="Lead not found")
    return res


@router.post("/api/v1/crm/leads/archive-inactive", tags=["Enterprise Reverse CRM"])
def archive_inactive_crm_leads(req: Optional[ArchiveInactiveRequest] = None):
    days = req.inactive_days if req else 90
    result = reverse_crm.archive_inactive_leads(days)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/api/v1/crm/leads/{lead_id}/timeline", tags=["Enterprise Reverse CRM"])
def get_lead_interaction_timeline(lead_id: str):
    res = reverse_crm.get_lead_timeline(lead_id)
    if res["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Lead not found")
    res["interactions"] = onboarding.annotate_interactions(res["interactions"])
    # Whether the lead was scored at all, and its tier under the one rule. A
    # captured lead is scored at capture, and a student's 0 is a score; only a
    # lead added by hand, with nothing captured, has none. The dossier read
    # every 0 as "Not scored".
    res["lead"]["scored"] = bool(res["interactions"]) or float(res["lead"].get("icp_score") or 0) > 0
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
