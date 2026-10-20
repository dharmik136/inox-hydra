"""
A first message says only what is true of the creator and the lead.
===================================================================

The drafts were written in the original author's voice. A bakery marketer
pressing "Offer a blueprint" got "I recently put together a practical
architecture blueprint and checklist ... Would you find it helpful if I sent
the diagram over?", the peer question asked about "foundational observability
and decoupling logic", the call suggestion "swap notes on engineering
architecture", and the reply ended "Are you testing similar workflows in your
stack?". A creator who copies one sends a stranger a false claim under their
own name.

A draft may use the lead's record (name, company, how they engaged, their
comment) and what the creator types. Anything else is invented, and where
there is not enough to write from, the draft says what is missing.
"""

import os
import re
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

# The original author's background. None of it is true of an arbitrary creator.
NOT_THE_CREATORS = (
    "architecture", "architectural", "blueprint", "diagram", "observability", "decoupl",
    "stack", "trajectory", "engineering", "technical", "workflows", "scale", "your team",
)
OFFERS = ("send it over", "sent the diagram", "checklist", "happy to share", "drop the link")


@pytest.fixture
def client(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_dm_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    from fastapi.testclient import TestClient
    import app as app_module

    init_db()
    client = TestClient(app_module.app)
    profile = client.get("/api/settings/profile").json()["profile"]
    profile.update(name="Priya Test", headline="Marketing lead at Bloom Bakery", company="Bloom Bakery")
    assert client.post("/api/settings/profile", json=profile).status_code == 200
    return client


@pytest.fixture
def leads(client):
    from crm import reverse_crm

    asha = reverse_crm.ingest_interaction(
        full_name="Asha Rao", linkedin_urn="https://www.linkedin.com/in/asha-rao-dm",
        headline="Founder at Crumb Co", company="Crumb Co", interaction_type="COMMENT",
        comment_text="We lost a fifth of our flour to this last winter.",
    )["lead_id"]
    zoe = reverse_crm.ingest_interaction(
        full_name="Zoe Park", linkedin_urn="https://www.linkedin.com/in/zoe-park-dm",
        headline="", interaction_type="LIKE",
    )["lead_id"]
    return {"asha": asha, "zoe": zoe}


def _claims(text):
    lowered = text.lower()
    return [word for word in NOT_THE_CREATORS if word in lowered]


@pytest.mark.parametrize("who", ["asha", "zoe"])
@pytest.mark.parametrize("style", ["value_add", "quick_chat"])
@pytest.mark.parametrize("topic", [None, "flour waste"])
def test_an_opener_claims_nothing_about_the_creator_it_does_not_know(client, leads, who, style, topic):
    query = f"style={style}" + (f"&topic={topic}" if topic else "")
    body = client.get(f"/api/leads/{leads[who]}/dm-script?{query}").json()
    script = body["dm_script"]
    assert script.startswith("Hi "), body
    assert not _claims(script), f"{style} for {who} says {_claims(script)} about the creator:\n{script}"
    assert not any(offer in script.lower() for offer in OFFERS), f"{style} offers something nobody named:\n{script}"


def test_an_offer_needs_the_creator_to_say_what_it_is(client, leads):
    body = client.get(f"/api/leads/{leads['asha']}/dm-script?style=resource_share").json()
    assert body.get("error"), f"an offer was drafted with nothing to offer: {body}"
    assert not body.get("dm_script")
    assert "what you would" in body["error"].lower()

    offer = "the flour order sheet I use every week"
    body = client.get(
        f"/api/leads/{leads['asha']}/dm-script", params={"style": "resource_share", "offer": offer, "topic": "flour waste"}
    ).json()
    script = body["dm_script"]
    assert offer in script, script
    assert not _claims(script), script


def test_the_reply_and_its_variants_claim_nothing_about_the_creator(client):
    # The variants route was removed in cycle 2 (D1); the generator remains.
    from crm import ICPScoringEngine

    for comment in ("How long do you proof it?", "Loved the flour waste numbers"):
        body = {"lead_name": "Asha Rao", "comment_text": comment, "post_topic": "flour waste"}
        reply = client.post("/api/v1/crm/leads/generate-dm", json=body).json()["suggested_dm"]
        assert reply and not _claims(reply), f"the reply says {_claims(reply)}:\n{reply}"
        assert "breakdown" not in reply.lower(), f"the reply names a post format nobody gave:\n{reply}"
        for variant in ICPScoringEngine.generate_anti_slop_dm_variants(**body):
            assert not _claims(variant["dm_text"]), f"{variant['angle']}: {variant['dm_text']}"


def test_a_question_reply_does_not_promise_a_perspective_it_does_not_give(client):
    body = {"lead_name": "Asha Rao", "comment_text": "How long do you proof it?", "post_topic": "sourdough"}
    reply = client.post("/api/v1/crm/leads/generate-dm", json=body).json()["suggested_dm"]
    assert "share a quick perspective" not in reply, reply

    body["custom_insight"] = "I proof overnight in the fridge."
    reply = client.post("/api/v1/crm/leads/generate-dm", json=body).json()["suggested_dm"]
    assert "I proof overnight in the fridge." in reply


def test_the_interface_no_longer_offers_a_blueprint():
    with open(os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts"), encoding="utf-8") as handle:
        client_source = handle.read()
    with open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "LeadsSurface.tsx"), encoding="utf-8") as handle:
        surface = handle.read()
    # What the reader sees, so comments explaining the change do not count.
    shown = re.sub(r"/\*.*?\*/|^\s*//[^\n]*$", "", client_source + surface, flags=re.DOTALL | re.MULTILINE)
    assert not re.search(r"blueprint", shown, re.IGNORECASE)
