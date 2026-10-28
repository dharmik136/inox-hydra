"""
CRM and Audience Graph API Router
=================================
Inbound lead management, ICP scoring, contact status events, anti-slop DMs,
and interaction history. Zero cloud egress.
"""

import re
import uuid
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ValidationError

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
    from ..crm import ICPScoringEngine, ReverseCRMManager, reverse_crm, qualification_tier, MAX_CRM_COMMENT_LENGTH
    from .. import onboarding, retention, ingest_contract, changes
    from ..migrations import INTERACTION_PLACEHOLDERS, interaction_comment_key
    from ..text_cut import clip
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
    from crm import ICPScoringEngine, ReverseCRMManager, reverse_crm, qualification_tier, MAX_CRM_COMMENT_LENGTH
    import onboarding
    import retention
    import ingest_contract
    import changes
    from migrations import INTERACTION_PLACEHOLDERS, interaction_comment_key
    from text_cut import clip

router = APIRouter()


class LeadStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None
    # The post the change came from: the dossier was opened from Replies or a
    # post's detail. Checked against what the person engaged with.
    post_urn: Optional[str] = None


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
    # One read's people, each in the shape above, answered item by item
    # (cycle 4, track 1, phase 2). The worker's key for each and its stamp.
    items: Optional[List[Dict[str, Any]]] = None
    idempotency_key: Optional[str] = None
    stamp: Optional[Dict[str, Any]] = None


# One read carries at most this many people: the other list routes' cap.
MAX_READ_ITEMS = 300


def _norm_type(raw: Optional[str]) -> str:
    said = (raw or "COMMENT").upper()
    if "COMMENT" in said:
        return "COMMENT"
    if "LIKE" in said:
        return "LIKE"
    if "REPOST" in said:
        return "REPOST"
    return "COMMENT"


def _engagement_grain(creator: str, req: "IngestInteractionRequest") -> str:
    """
    The key of one engagement by the studio's own grain: lead_interactions
    keeps one row per person, post, kind and comment, the person known by the
    /in/ identifier of their profile (crm._find_lead) and the comment by its
    normalised words (migrations.interaction_comment_key), with the capture's
    placeholders cleared as crm.ingest_interaction clears them.
    """
    person = req.linkedin_urn or req.profile_url or ""
    match = re.search(r"linkedin\.com/in/([^/?#]+)", person, re.IGNORECASE)
    person_key = match.group(1).lower() if match else person
    comment = clip(req.comment_text, MAX_CRM_COMMENT_LENGTH) if req.comment_text else req.comment_text
    if comment and comment.strip().lower() in INTERACTION_PLACEHOLDERS:
        comment = None
    return ingest_contract.grain_key("engagement", creator, req.post_urn or "", person_key,
                                     _norm_type(req.interaction_type), interaction_comment_key(comment))


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


def _engaged_post(lead_id: str, post_urn: str) -> Optional[str]:
    """
    The post as this person's engagement names it, when they engaged with the
    post asked for under any of LinkedIn's spellings of it; None otherwise.
    """
    wanted = onboarding._activity_id(post_urn)
    if not wanted:
        return None
    conn = get_db()
    try:
        for row in conn.execute("SELECT DISTINCT post_urn FROM lead_interactions WHERE lead_id = ? "
                                "AND post_urn IS NOT NULL", (lead_id,)):
            if onboarding._activity_id(row[0]) == wanted:
                return row[0]
    finally:
        conn.close()
    return None


@router.put("/api/leads/{lead_id}/status")
def update_lead(lead_id: str, payload: LeadStatusUpdate):
    post_urn = None
    if payload.post_urn:
        # A change is recorded as coming from a post only when the person
        # engaged with that post; otherwise it is refused, not recorded
        # without it, so the screen can say so.
        post_urn = _engaged_post(lead_id, payload.post_urn)
        if post_urn is None:
            raise HTTPException(status_code=422, detail="This person has not engaged with that post, so the change "
                                                        "cannot be recorded as coming from it.")
    result = update_lead_status(lead_id, payload.status, payload.notes, post_urn=post_urn)
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


def _gate(req: "IngestInteractionRequest") -> Optional[Dict[str, Any]]:
    """The engagement gate's answer for one person, or None when they may be filed."""
    refused = onboarding.engagement_gate(req.linkedin_urn or req.profile_url, req.post_urn, req.post_author)
    verdict = ingest_contract.classify(refused)
    if not verdict:
        return None
    reason, outcome = verdict
    if outcome == ingest_contract.REFUSED:
        ingest_contract.note_refusal(reason)
        return ingest_contract.refusal_body(reason, refused)
    return ingest_contract.nothing_new(reason, refused)


def _write_engagement(req: "IngestInteractionRequest") -> Dict[str, Any]:
    """
    One engagement, written, on the single writer's turn.

    The gate let this person through because the post is the creator's, so
    the post is made known before anyone is filed under it: its publication
    and its posts row, by the one rule (post_identity.ensure_post, through
    onboarding.note_own_post). A post first found through its engagers used to
    have neither, and its engagers route answered 404. A failure there is
    logged and the capture still kept, because the next read of the post or
    the next upgrade gives it its post, and the person is the creator's
    either way.

    post_id is deliberately not passed on: lead_interactions.post_id is an
    INTEGER foreign key into drafts(id) and can never match a posts.id, so
    writing the studio's own key there stored a value nothing can join;
    post_urn is what every attribution surface reads.
    """
    if req.post_urn:
        try:
            onboarding.note_own_post(req.post_urn)
        except Exception as error:  # noqa: BLE001
            ingest_contract.logger.warning("The post of a captured engagement was not recorded: %s", error)
    urn = req.linkedin_urn or req.profile_url or f"local:unresolved:{uuid.uuid4().hex[:12]}"
    return reverse_crm.ingest_interaction(
        full_name=req.full_name,
        linkedin_urn=urn,
        headline=req.headline,
        company=req.company,
        interaction_type=_norm_type(req.interaction_type),
        comment_text=req.comment_text,
        post_urn=req.post_urn,
        post_id=None,
        post_topic=req.post_topic,
        capture_context=req.capture_context,
    )


@router.post("/api/v1/crm/interactions/ingest", tags=["Enterprise Reverse CRM"])
def ingest_crm_interaction(req: IngestInteractionRequest):
    """
    One engagement on one of the creator's posts, or one read's people as
    items[]. Answers one of the three outcomes in ingest_contract: accepted,
    nothing_new, or 409 refused; a read answers each person on their own,
    under 200.

    Every decline used to be 200 {"status": "skipped"}, including "confirm
    your profile in Setup first", so a creator scrolled their own post, saw
    nothing happen, and had no way to learn why.

    A replay of an engagement the studio took in the last ten minutes is
    answered nothing_new / already_seen before the writer: ten tabs on one
    post used to write each person ten times (ingest_contract.RECENT).
    """
    ingest_contract.note_client(req.extension_version, req.contract_version)
    if req.items is not None:
        return _ingest_read(req)
    creator = onboarding.confirmed_vanity()
    answer = _gate(req)
    if answer is not None:
        if answer["outcome"] == ingest_contract.REFUSED:
            raise ingest_contract.RefusedIngest(answer["reason"], answer["message"])
        return answer
    key = _engagement_grain(creator, req)
    if ingest_contract.RECENT.seen(key):
        return ingest_contract.already_seen(post_key=ingest_contract.post_key_of(req.model_dump()))
    # One writer for a burst. Thirty engagers of one post arrive at once and
    # used to race for the database lock through SQLite's polling busy
    # handler, so each waited for the whole queue: 6,047 ms of wall time
    # against 1,318 ms for the same thirty one at a time. Taking a turn costs
    # one hand-off and removes the contention.
    result = ingest_contract.through_the_writer("Capturing an engagement", _write_engagement, req)
    ingest_contract.RECENT.remember(key)
    norm_type = _norm_type(req.interaction_type)
    changes.publish("people", interaction={"LIKE": "reaction", "REPOST": "repost"}.get(norm_type, "comment"), post=req.post_urn, lead=result.get("lead_id"))
    result["id"] = result.get("lead_id")
    result["qualification_tier"] = result.get("tier")
    return ingest_contract.accepted(interaction=result, lead=result,
                                    post_key=ingest_contract.post_key_of(req.model_dump()))


def _ingest_read(req: IngestInteractionRequest) -> Dict[str, Any]:
    """
    One read's people, in one request and one turn of the writer. Each
    person is answered on their own, under their idempotency key: accepted,
    already_seen, the gate's nothing_new, or a refusal with its sentence.
    """
    if len(req.items) > MAX_READ_ITEMS:
        raise ingest_contract.RefusedIngest(
            "too_many_items", f"One read carries at most {MAX_READ_ITEMS} people; this one carried {len(req.items)}.")
    creator = onboarding.confirmed_vanity()
    answers: List[Optional[Dict[str, Any]]] = [None] * len(req.items)
    to_write: List[tuple] = []
    queued = set()
    for index, raw in enumerate(req.items):
        key_said = raw.get("idempotency_key") if isinstance(raw, dict) else None
        try:
            item = IngestInteractionRequest(**{k: v for k, v in (raw if isinstance(raw, dict) else {}).items()
                                               if k not in ("items", "stamp")})
        except ValidationError:
            answers[index] = ingest_contract.refusal_body("bad_item", "This person could not be read.")
            answers[index]["idempotency_key"] = key_said
            continue
        answer = _gate(item)
        if answer is None:
            grain = _engagement_grain(creator, item)
            if ingest_contract.RECENT.seen(grain) or grain in queued:
                answer = ingest_contract.already_seen()
            else:
                queued.add(grain)
                to_write.append((index, item, grain))
        if answer is not None:
            answer["idempotency_key"] = key_said
            answers[index] = answer
    if to_write:
        results = ingest_contract.through_the_writer(
            "Capturing a read", lambda: [_write_engagement(item) for _, item, _ in to_write])
        for (index, item, grain), result in zip(to_write, results):
            ingest_contract.RECENT.remember(grain)
            result["id"] = result.get("lead_id")
            result["qualification_tier"] = result.get("tier")
            answers[index] = ingest_contract.accepted(interaction=result, lead=result)
            answers[index]["idempotency_key"] = item.idempotency_key
        changes.publish("people", interaction="read", post=to_write[0][1].post_urn, lead=None)
    accepted = sum(1 for a in answers if a and a.get("outcome") == ingest_contract.ACCEPTED)
    refused = [a for a in answers if a and a.get("outcome") == ingest_contract.REFUSED]
    outcome = ingest_contract.ACCEPTED if accepted else (
        ingest_contract.REFUSED if refused else ingest_contract.NOTHING_NEW)
    return {"status": "success" if accepted else ("refused" if refused else "skipped"), "outcome": outcome,
            "items": answers, "items_accepted": accepted, "contract_version": ingest_contract.CONTRACT_VERSION}


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
    conn = get_db()
    try:
        stage_history = [dict(r) for r in conn.execute(
            "SELECT from_status, to_status, changed_at, post_urn FROM lead_stage_events WHERE lead_id = ? "
            "ORDER BY changed_at", (lead_id,))]
    finally:
        conn.close()
    # One annotation for one read (tests/test_qc3_t7_leads_dossier.py): the
    # interactions, and the stage changes made from a post, each given its
    # post's opening by the same reading of the creator's posts.
    from_posts = [event for event in stage_history if event["post_urn"]]
    interactions = res["interactions"]
    res["interactions"] = onboarding.annotate_interactions(interactions + from_posts)[:len(interactions)]
    for event in stage_history:
        if not event["post_urn"]:
            event["post_excerpt"] = None
        event.pop("post_origin", None)
    res["stage_history"] = stage_history
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
