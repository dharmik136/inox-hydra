"""
A lead in search reads as it does on Leads.
==========================================

Cycle 2, batch R5, D-16 (the presentation half; ranking is batch R3's
full-text search). The palette labelled a lead "DM SENT" where the pipeline
says "Outreach Sent", and its line repeated the company, "Logiq Logiq".
"""

from qc2_r5_live import seed_creator, server, studio  # noqa: F401


def test_a_lead_result_names_its_stage_and_company_once(studio):
    client = studio["client"]
    # Anika Shah, "Head of Platform at Cargoline", of the company Cargoline.
    seed_creator(client)
    leads = client.get("/api/leads").json()["leads"]
    lead_id = next(lead["id"] for lead in leads if "Anika" in (lead.get("name") or lead.get("full_name") or ""))
    assert client.put(f"/api/leads/{lead_id}/status", json={"status": "Outreach Sent"}).status_code == 200

    hits = client.get("/api/v1/search", params={"q": "Anika"}).json()["groups"]["leads"]
    assert hits, "the lead was not found"
    hit = hits[0]
    assert hit["meta"] == "OUTREACH SENT", hit
    assert "Cargoline Cargoline" not in hit["snippet"], hit
