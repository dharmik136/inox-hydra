import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

# Add studio/backend to path (test lives in tests/, modules import as top-level)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from database import init_db, seed_initial_data, get_db
from formatters import (
    to_sans_bold,
    to_sans_italic,
    to_serif_bold,
    to_serif_italic,
    to_blackboard_bold,
    to_underline,
    to_circled_numbers,
    to_monospace,
    to_strikethrough,
    clean_text_formatting,
    analyze_hook,
    calculate_dwell_metrics
)
from carousel_generator import generate_carousel_pdf
from repurposer import generate_10x_hooks, audit_linkedin_algorithm_safety, repurpose_content
from leads import list_leads, add_lead, batch_add_leads, update_lead_status, generate_dm_script, export_leads_csv
from linkedin_client import linkedin_client
from app import get_kpis, get_analytics_overview, get_smart_slots, export_leads_csv_route

def test_database_and_seed():
    init_db()
    seed_initial_data()
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM analytics_daily")
    analytics_count = c.fetchone()[0]
    assert analytics_count >= 60, f"Expected >= 60 analytics rows, got {analytics_count}"

    c.execute("SELECT COUNT(*) FROM posts")
    posts_count = c.fetchone()[0]
    assert posts_count >= 3, f"Expected >= 3 posts, got {posts_count}"

    c.execute("SELECT COUNT(*) FROM audience_demographics")
    demo_count = c.fetchone()[0]
    assert demo_count >= 14, f"Expected >= 14 demographic rows, got {demo_count}"

    c.execute("SELECT COUNT(*) FROM queue_slots")
    slots_count = c.fetchone()[0]
    assert slots_count >= 8, f"Expected >= 8 queue slots, got {slots_count}"

    c.execute("SELECT COUNT(*) FROM leads")
    leads_count = c.fetchone()[0]
    assert leads_count >= 4, f"Expected >= 4 leads, got {leads_count}"

    conn.close()
    print("✅ test_database_and_seed passed!")


def test_formatters_and_rehooker():
    bold_res = to_sans_bold("Hello World 123")
    assert "𝗛𝗲𝗹𝗹𝗼" in bold_res

    # Test Extended Unicode Formatters
    serif_bold = to_serif_bold("Hello World 123")
    assert "𝐇𝐞𝐥𝐥𝐨" in serif_bold

    serif_italic = to_serif_italic("Hello World")
    assert "𝐻𝑒𝑙𝑙𝑜" in serif_italic

    blackboard = to_blackboard_bold("ABC 123")
    assert "\u2102" in blackboard  # Special cap C

    underline = to_underline("Hello")
    assert "\u0332" in underline

    circled = to_circled_numbers("1 2 3")
    assert "❶ ❷ ❸" in circled

    # Test Dwell Time Metrics Calculation
    dwell_short = calculate_dwell_metrics("Quick hook sentence.")
    assert dwell_short["dwell_status"] == "LOW_VELOCITY"

    sample_post = "First paragraph analyzing high-retention creator dynamics and local-first software.\n\nSecond paragraph explaining why SQLite WAL mode achieves microsecond latency.\n\nThird paragraph detailing how modern anti-bot heuristics detect headless browsers."
    dwell_optimal = calculate_dwell_metrics(sample_post)
    assert dwell_optimal["dwell_status"] in ("OPTIMAL_HOOK", "DEEP_DWELL")
    assert dwell_optimal["word_count"] > 20
    assert float(dwell_optimal["estimated_reading_sec"]) > 5.0

    hooks = generate_10x_hooks("enterprise observability and systems architecture")
    assert len(hooks) == 10, f"Expected 10 hooks, got {len(hooks)}"
    assert hooks[0]["mobile_safe"] is True

    audit = audit_linkedin_algorithm_safety("Check out our new tool at https://example.com/tool #a #b #c #d #e #f #g")
    assert audit["has_outbound_links"] is True
    assert audit["safety_score"] < 70, f"Expected score penalty, got {audit['safety_score']}"

    repurposed = repurpose_content("Decoupling database from business logic is critical for scalable enterprise platforms.")
    assert len(repurposed) == 5

    print("✅ test_formatters_and_rehooker passed!")


def test_carousel_pdf():
    slides = [
        {"title": "The Decoupled Architecture", "body": "Why modern enterprise platforms cannot rely on monolithic schemas."},
        {"title": "01. Pure State Machine", "body": "Treat state transitions as immutable events rather than in-place updates."},
        {"title": "02. Verification Over Trust", "body": "Every diff must be programmatically verified before execution."},
        {"title": "Actionable Summary", "body": "Save this carousel to revisit foundational system architecture."}
    ]
    pdf = generate_carousel_pdf(slides)
    assert len(pdf) > 50000, "PDF bytes unexpectedly small"
    assert pdf.startswith(b"%PDF"), "Missing PDF magic bytes header"
    print("✅ test_carousel_pdf passed!")


def test_leads_crm():
    leads = list_leads()
    assert len(leads) >= 4, f"Expected >= 4 leads, got {len(leads)}"

    # Test filtering by status
    new_leads = list_leads(status="New Lead")
    assert len(new_leads) >= 1
    assert all(l["status"] == "New Lead" for l in new_leads)

    # Test search
    search_leads = list_leads(search="Aravind")
    assert len(search_leads) >= 1
    assert any("Aravind" in l["name"] for l in search_leads)

    # Test multi-style DM generation & strict zero em-dash check
    styles = ["value_add", "resource_share", "quick_chat"]
    for s in styles:
        dm_res = generate_dm_script(leads[0]["id"], style=s)
        assert dm_res["status"] == "success"
        script = dm_res["dm_script"]
        assert "\u2014" not in script, f"DM script in style '{s}' contains forbidden em-dash!"
        assert "--" not in script, f"DM script in style '{s}' contains forbidden double dash!"
        assert len(script) > 50

    # Test CSV Export
    csv_str = export_leads_csv()
    assert "ID,Name,Headline,Company,Seniority Level,ICP Score,Qualification Tier,Status,Profile URL,Engagement Type,Notes,Created At" in csv_str
    assert "Aravind Subramanian" in csv_str

    # Test API CSV route response
    csv_resp = export_leads_csv_route()
    assert csv_resp.media_type == "text/csv"
    assert "linkedin_studio_crm_leads.csv" in csv_resp.headers["Content-Disposition"]

    # Test deduplicated batch ingestion
    import uuid
    rand_tag = uuid.uuid4().hex[:6]
    batch_res = batch_add_leads([
        {
            "name": "Aravind Subramanian",
            "headline": "VP of Engineering at CloudScale",
            "profile_url": "https://linkedin.com/in/aravind-sub",
            "engagement_type": "Commented",
            "notes": 'Commented: "Decoupling logic is essential."'
        },
        {
            "name": f"Test Prospect {rand_tag}",
            "headline": "Staff SRE @ Quantum Corp",
            "profile_url": f"https://linkedin.com/in/test-prospect-{rand_tag}",
            "engagement_type": "Liked",
            "notes": "Reacted to post on LinkedIn"
        }
    ])
    assert batch_res["status"] == "success"
    assert batch_res["updated"] >= 1  # Aravind was updated with latest comment
    assert batch_res["added"] == 1    # Unique prospect was added

    print("✅ test_leads_crm passed!")


def test_multi_range_kpis_and_slots():
    kpis_7d = get_kpis(range="7d")
    assert kpis_7d["range"] == "7d"
    assert "impressions_delta_pct" in kpis_7d

    kpis_30d = get_kpis(range="30d")
    assert kpis_30d["range"] == "30d"

    overview_14d = get_analytics_overview(range="14d")
    assert overview_14d["count"] == 14

    slots = get_smart_slots()
    assert slots["status"] == "success"
    assert len(slots["slots"]) >= 8

    print("✅ test_multi_range_kpis_and_slots passed!")


def test_ai_engine():
    from repurposer import get_ai_status, command_ai_engine
    status = get_ai_status()
    assert status["provider"] in ["gemini_antigravity", "local_deterministic", "gemini"]
    assert "capabilities" in status

    cmd_res = command_ai_engine("Write a contrarian hook about enterprise data decoupling")
    assert cmd_res["status"] == "success"
    assert "output" in cmd_res
    assert "\u2014" not in cmd_res["output"]  # Strict zero em-dash rule!
    print("✅ test_ai_engine passed (strict zero em-dash verified)!")


def test_scheduled_post_integrity():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM posts WHERE id = 'post-enterprise-scheduled'")
    post = c.fetchone()
    assert post is not None, "Crucial post 'post-enterprise-scheduled' not found!"
    assert post["status"] in ["scheduled", "published"], f"Expected post status 'scheduled' or 'published', got '{post['status']}'"
    assert "\u2014" not in post["content"], "Post contains forbidden em-dash!"
    assert "12:00:00" in post["scheduled_for"], f"Unexpected schedule time: {post['scheduled_for']}"
    conn.close()
    print("✅ test_scheduled_post_integrity passed (5:30 PM IST post confirmed intact)!")


def test_static_assets_and_docs():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    docs_dir = os.path.join(base_dir, "docs")
    assets_dir = os.path.join(base_dir, "assets")

    expected_docs = [
        "ARCHITECTURE.md",
        "AI_ENGINE.md",
        "EXTENSION_AND_SYNC.md",
        "ENTERPRISE_USAGE.md",
        "API_REFERENCE.md",
        "GETTING_STARTED.md"
    ]
    for d in expected_docs:
        doc_path = os.path.join(docs_dir, d)
        assert os.path.exists(doc_path), f"Required doc missing: {d}"
        assert os.path.getsize(doc_path) > 500, f"Doc unexpectedly small: {d}"

    # Verify master 4K asset in assets/
    master_asset = os.path.join(assets_dir, "motadata_to_enterprise_4k_flawless.jpg")
    assert os.path.exists(master_asset), "Master creative missing from assets/"

    # Verify all 6 section-wise modular docs
    modules_dir = os.path.join(docs_dir, "modules")
    assert os.path.exists(modules_dir), "docs/modules directory missing"
    expected_modules = [
        "01_STUDIO_AND_EDITOR.md",
        "02_SCHEDULE_AND_QUEUE.md",
        "03_INBOUND_CRM.md",
        "04_VIRAL_SWIPE_FILE.md",
        "05_ANALYTICS.md",
        "06_AI_COMMAND.md"
    ]
    for m in expected_modules:
        m_path = os.path.join(modules_dir, m)
        assert os.path.exists(m_path), f"Modular doc missing: {m}"
        assert os.path.getsize(m_path) > 1000, f"Modular doc unexpectedly small: {m}"

    print("✅ test_static_assets_and_docs passed (all master docs, 6 module specs & creatives validated)!")


def test_docs_api_and_modules():
    from app import list_docs_modules, get_doc_module

    docs_res = list_docs_modules()
    assert docs_res["status"] == "success"
    assert docs_res["count"] >= 7
    modules = docs_res["modules"]

    module_ids = [m["id"] for m in modules]
    assert "studio-editor" in module_ids
    assert "schedule-queue" in module_ids
    assert "inbound-crm" in module_ids
    assert "viral-swipe-file" in module_ids
    assert "analytics" in module_ids
    assert "ai-command" in module_ids
    assert "enterprise-usage" in module_ids

    # Test individual module fetch and content validations
    studio_doc = get_doc_module("studio-editor")
    assert "Algorithmic Safety Audit" in studio_doc["content"]
    assert "Pre-Fold Hook" in studio_doc["content"]
    assert "Outbound Link Egress" in studio_doc["content"]

    crm_doc = get_doc_module("inbound-crm")
    assert "Contact Name" in crm_doc["content"]
    assert "value_add" in crm_doc["content"]
    assert "resource_share" in crm_doc["content"]

    swipe_doc = get_doc_module("viral-swipe-file")
    assert "Agno" in swipe_doc["content"] or "agno" in swipe_doc["content"].lower(), "Agno framework not documented in swipe file doc!"

    analytics_doc = get_doc_module("analytics")
    assert "li_at" in analytics_doc["content"]
    assert "Voyager" in analytics_doc["content"]

    ai_doc = get_doc_module("ai-command")
    assert "Gemini 2.5 Flash" in ai_doc["content"]
    assert "Antigravity Local Engine" in ai_doc["content"]

    print("✅ test_docs_api_and_modules passed (API routes & section-wise content thoroughly verified)!")


if __name__ == "__main__":
    print("Running LinkedIn Studio Enterprise Tests...")
    test_database_and_seed()
    test_formatters_and_rehooker()
    test_carousel_pdf()
    test_leads_crm()
    test_multi_range_kpis_and_slots()
    test_ai_engine()
    test_scheduled_post_integrity()
    test_static_assets_and_docs()
    test_docs_api_and_modules()
    print("\n🎉 ALL 9 ENTERPRISE TEST SUITES PASSED SUCCESSFULLY!")
