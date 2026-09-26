"""
What the studio may tell a creator about a stranger.
===================================================

The CRM holds real people, captured by an extension watching pages the creator
opened. Everything this product generates about them goes out under the
creator's name, to someone who can read it and disagree, so the standard for a
sentence here is higher than for anything the studio shows only to its owner.

Two routes draft outreach, and they are not equivalent.

`/api/leads/{id}/dm-script` interpolates fields the studio actually holds: the
lead's first name, their company as recorded, whether they commented or reacted,
and their comment quoted from the notes when one is there. Every claim in the
output traces to a column. That is a template, and templates are fine when the
creator reads the words before sending them.

`/api/leads/{id}/enrich` is a different thing wearing similar clothes.
LeadResearchAgent matches the headline against a keyword taxonomy, picks one of
five role buckets, and returns a paragraph written in advance for that bucket
with the company name interpolated into it. For a headline containing "VP of
Engineering" it asserts that the company "operates at enterprise scale" and runs
"Kubernetes, Go/Java microservices, Kafka event streams" - the same list for a
five person startup and for a bank, because the company was never consulted. The
field is named estimated_tech_stack, which is honest, and sits beside
company_intelligence, which is not.

So the interface surfaces the first and not the second, and this file holds that
line by property rather than by prohibition. Surfacing enrichment is allowed. It
is allowed on the condition that the screen says the dossier is inferred from a
job title, because a creator who believes the studio researched the company will
repeat it to the person it is about.

The last test pins the premise. If the research agent ever does real lookups,
these tests fail and the labelling requirement should be revisited rather than
worked around.
"""

import inspect
import os
import re
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")

sys.path.insert(0, BACKEND)

API_CLIENT = os.path.join(UI_SRC, "lib", "api.ts")
LEADS_SURFACE = os.path.join(UI_SRC, "components", "LeadsSurface.tsx")

# Anything that would open a socket to another host.
OUTBOUND = re.compile(
    r"\brequests\.(get|post|put|patch|delete)\b"
    r"|\bhttpx\."
    r"|\baiohttp\."
    r"|\burlopen\("
    r"|\bsocket\.(create_connection|socket)\b"
)


def _read(path):
    if not os.path.exists(path):
        pytest.skip(f"{os.path.basename(path)} is not present in this checkout")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _rendered(path):
    """
    Source with comments stripped.

    Three guards in this repository have failed on the comment explaining the
    thing they forbid. A comment is not what the reader sees, so it is not what
    a claim check should read.
    """
    source = _read(path)
    source = re.sub(r"\{/\*.*?\*/\}", "", source, flags=re.DOTALL)
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    source = re.sub(r"^\s*//[^\n]*$", "", source, flags=re.MULTILINE)
    return source


def _lead(**overrides):
    row = {
        "id": "claims-probe",
        "name": "Priya Raman",
        "headline": "VP of Engineering",
        "company": "Northwind Freight",
        "engagement_type": "Reacted",
        "notes": "",
        "profile_url": "",
    }
    row.update(overrides)
    return row


@pytest.fixture
def seeded():
    """
    A lead in the real table, because generate_dm_script reads the database
    rather than taking a dict.
    """
    from database import get_db

    def seed(**overrides):
        row = _lead(**overrides)
        conn = get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO leads "
                "(id, name, headline, company, engagement_type, notes, status) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    row["id"], row["name"], row["headline"], row["company"],
                    row["engagement_type"], row["notes"], "new",
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return row["id"]

    yield seed

    conn = get_db()
    try:
        conn.execute("DELETE FROM leads WHERE id = 'claims-probe'")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The draft every lead can get
# ---------------------------------------------------------------------------

def test_a_reaction_is_not_thanked_for_a_perspective(seeded):
    """
    The defect surfacing this route made visible.

    The value_add opener read "Really appreciated your perspective!" for every
    lead, including the ones who had clicked a reaction and said nothing. That
    attributes an opinion to a real person, in a message about to be sent to
    them, and they are the one reader guaranteed to know it is false.
    """
    import leads

    lead_id = seeded(engagement_type="Reacted")
    for style in ("value_add", "resource_share", "quick_chat"):
        script = leads.generate_dm_script(lead_id, style=style)["dm_script"]
        assert "perspective" not in script.lower(), (
            f"the {style} draft credits a perspective to someone who only "
            f"reacted:\n{script}"
        )


def test_a_comment_still_is(seeded):
    """
    The other half, so the fix above is a condition rather than a deletion.

    Removing the sentence outright would have been the cheap fix and would have
    made the draft worse for the leads it was true of.
    """
    import leads

    lead_id = seeded(engagement_type="Commented")
    script = leads.generate_dm_script(lead_id, style="value_add")["dm_script"]
    assert "perspective" in script.lower(), (
        "the opener no longer acknowledges a comment the lead actually left"
    )


def test_the_draft_says_only_what_the_record_holds(seeded):
    """
    Every proper noun in the output traces to a column. This is what separates
    the template from the dossier.
    """
    import leads

    lead_id = seeded(company="Northwind Freight", name="Priya Raman")
    script = leads.generate_dm_script(lead_id, style="value_add", post_topic="local-first tooling")["dm_script"]

    assert "Priya" in script
    assert "Northwind Freight" in script
    assert "local-first tooling" in script, "the topic the creator supplied was dropped"


def test_no_topic_is_invented_for_the_post(seeded):
    """
    Without a topic the draft fell back to "enterprise systems and
    architecture", naming a post the creator may never have written. The studio
    does not know which post the lead engaged with, so it says nothing about
    the subject rather than guessing one.
    """
    import leads

    lead_id = seeded()
    for style in ("value_add", "resource_share", "quick_chat"):
        script = leads.generate_dm_script(lead_id, style=style)["dm_script"]
        assert "enterprise systems" not in script, (
            f"the {style} draft names a post topic nobody supplied:\n{script}"
        )
        assert " on ." not in script and " regarding !" not in script, (
            f"removing the topic left a dangling phrase:\n{script}"
        )


def test_every_lead_can_reach_a_draft():
    """
    The reason this route was worth surfacing.

    The interface had one drafting control, built from a comment, so a lead who
    reacted got a disabled button and a sentence reading NO COMMENT FROM THIS
    LEAD TO DRAFT A REPLY FROM. That described a limit the product did not have.
    """
    client = _rendered(API_CLIENT)
    assert "dm-script" in client, (
        "the interface no longer reaches the one DM route that needs no comment, "
        "so leads who reacted rather than commented have no draft again"
    )

    surface = _rendered(LEADS_SURFACE)
    assert "DM_STYLES" in surface, (
        "the openers are reachable in the client but not offered on the surface"
    )


def test_the_surface_does_not_offer_to_send_the_message():
    """
    The studio cannot send a LinkedIn DM and must not imply otherwise. A draft
    is handed to the creator to send by hand, which is why it is copyable.
    """
    surface = _rendered(LEADS_SURFACE)
    assert "Nothing is sent from here" in surface, (
        "the drafting panel no longer says the sending is the creator's to do"
    )
    assert "clipboard" in surface, (
        "a draft the creator cannot copy is a draft they have to retype"
    )


# ---------------------------------------------------------------------------
# The dossier, and the condition on surfacing it
# ---------------------------------------------------------------------------

def test_enrichment_is_not_presented_as_research():
    """
    A condition, not a ban.

    If the interface ever calls the enrich routes, the screen has to say the
    dossier is inferred from the job title. Written as a property so that
    surfacing it honestly passes and surfacing it silently fails, rather than as
    a tripwire on a spelling, which this repository has already watched go stale
    while its own premise went false.
    """
    client = _rendered(API_CLIENT)
    if not re.search(r"/api/leads/[^\"'`\s]*/enrich", client):
        pytest.skip("the interface does not surface enrichment, which is the current state")

    surface = _rendered(LEADS_SURFACE).lower()
    hedges = ("inferred", "estimate", "guess", "not research", "from their headline", "from the job title")
    assert any(word in surface for word in hedges), (
        "the enrichment dossier is on screen without saying where it comes "
        "from. It is a keyword match on the headline, so a creator reading "
        "company_intelligence as research will repeat an invented fact to the "
        "person it is about. Label it, or take it back off."
    )


def test_the_dossier_is_inference_and_nothing_more():
    """
    The premise the test above rests on.

    If this starts failing because the agent gained a real lookup, the labelling
    requirement is the thing to revisit. Until then the paragraph is chosen by
    keyword and the company is never consulted.
    """
    import agno_agent

    source = inspect.getsource(agno_agent.LeadResearchAgent)
    assert not OUTBOUND.search(source), (
        "LeadResearchAgent now makes an outbound call, so it may be doing real "
        "research. Re-read test_enrichment_is_not_presented_as_research before "
        "changing anything: its requirement may no longer be the right one."
    )
    assert "ROLE_TAXONOMY" in source, (
        "the role taxonomy is gone, so how the dossier is derived has changed "
        "and the claim this file makes about it needs re-checking"
    )


def test_the_same_headline_yields_the_same_dossier_for_any_company():
    """
    The clearest statement of what the dossier is.

    Two unrelated companies, one headline, identical technical findings. Held as
    a test because the field names alone read as though a lookup happened.
    """
    import agno_agent

    agent = agno_agent.LeadResearchAgent()
    small = agent.research(_lead(company="Two Person Consultancy"))
    large = agent.research(_lead(company="Global Investment Bank"))

    assert small["estimated_tech_stack"] == large["estimated_tech_stack"], (
        "the stack now varies by company, which would mean something about the "
        "company is being consulted. Check whether the dossier has become real."
    )
    assert small["friction_points"] == large["friction_points"]
    assert "Two Person Consultancy" in small["company_intelligence"], (
        "the company name is interpolated into a prewritten paragraph, and if "
        "that stopped being true this file's description of the mechanism is stale"
    )
