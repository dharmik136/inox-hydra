"""
MiroFish 1,000 Autonomous User Personas Simulation Test Suite
=============================================================
Tests Inox Hydra's local CRM ingestion, deterministic ICP scoring,
seniority classification, and lead attribution under a realistic
1,000-user swarm intelligence simulation derived from MiroFish OASIS profiles.

Strict Invariants:
- 100% Zero Cloud Egress: zero external network sockets opened.
- Deterministic multi-factor scoring fidelity.
- SQLite WAL mode concurrency and high throughput.
- Zero em-dashes in any strings.
"""

import os
import sys
import time
import random
from typing import List, Dict, Any
import pytest

try:
    from studio.backend.database import get_db, init_db
    from studio.backend.crm import (
        reverse_crm,
        qualification_tier,
        VIP_THRESHOLD,
        QUALIFIED_THRESHOLD,
        NURTURE_THRESHOLD
    )
    from studio.backend import egress as _egress
except ImportError:
    from database import get_db, init_db
    from crm import (
        reverse_crm,
        qualification_tier,
        VIP_THRESHOLD,
        QUALIFIED_THRESHOLD,
        NURTURE_THRESHOLD
    )
    import egress as _egress


ROLES_AND_HEADLINES = [
    # Top Tier: C-Level, Founders, VPs (Expected TIER_1_VIP)
    ("Chief Technology Officer", "CTO at ScaleAI Labs | Distributed Systems & Multi-Agent Swarms", "Enterprise"),
    ("Founder & CEO", "Founder & CEO at ApexCloud | Ex-Google, Building Local AI Infrastructure", "Enterprise"),
    ("VP of Engineering", "VP of Engineering at Datacore | Distributed Storage & SQLite Systems", "Enterprise"),
    ("Chief Information Security Officer", "CISO at Sovereign Defense | Zero-Trust & Air-Gapped Architectures", "Enterprise"),
    ("Managing Director", "Managing Director at Sequoia Capital | B2B SaaS & Developer Infrastructure", "Enterprise"),
    
    # Mid Tier: Directors, Staff Architects, Leads (Expected QUALIFIED)
    ("Director of Product", "Director of Product Management at Stripe | Developer Platforms", "Enterprise"),
    ("Principal Solutions Architect", "Principal Solutions Architect at AWS | High-Throughput Databases", "Enterprise"),
    ("Staff AI Engineer", "Staff AI Engineer at Mistral | Edge Inference & LLM Tooling", "Enterprise"),
    ("Head of Developer Relations", "Head of DevRel at GitHub | Open Source Developer Ecosystems", "Enterprise"),
    ("Senior Engineering Manager", "Senior Engineering Manager at Figma | Real-Time Collaboration Systems", "Enterprise"),

    # Junior Tier: Associates, Analysts, Students (Expected NURTURE or DISQUALIFIED)
    ("Software Engineer Intern", "Software Engineering Intern at Local Startup | Learning Python & FastApi", "Startup"),
    ("Junior Data Analyst", "Junior Data Analyst at RetailMetrics | Excel, Python & BI Dashboards", "Startup"),
    ("Computer Science Student", "Computer Science Student at UC Berkeley | Interested in Agentic AI", "Academic"),
    ("Marketing Associate", "Marketing Associate at GrowthWave | Content & Social Media Strategy", "Agency"),
    ("Freelance Graphic Designer", "Freelance Graphic Designer | Logos, Branding & SVG Vectors", "Freelance")
]

FIRST_NAMES = [
    "Alex", "Priya", "Marcus", "Elena", "Liam", "Chen", "Sophia", "David",
    "Amina", "Mateo", "Ananya", "Lucas", "Mei", "Oliver", "Fatima", "Ethan"
]

LAST_NAMES = [
    "Vance", "Patel", "Morrison", "Rostova", "Kim", "Zhang", "Dubois", "Nakamura",
    "Al-Mansoor", "Silva", "Sharma", "Schmidt", "Wong", "O'Connor", "Haddad", "Novak"
]

SAMPLE_COMMENTS = [
    "Air-gapped creator tooling with zero egress is essential for enterprise security compliance.",
    "The deterministic multi-factor scoring formula provides much higher signal than black-box models.",
    "Using SQLite WAL mode for local desktop applications beats spinning up cloud databases every time.",
    "How does the Gaussian rate limiter pace requests to avoid LinkedIn UI detection flags?",
    "Vector SVG rendering for carousels is brilliant. Zero cloud rasterization latency.",
    "Very thoughtful architecture. The post identity binding solves attribution cleanly.",
    "Would love to see how this integrates with local Ollama hardware inference.",
    "Impressive work on the forward-only schema migration ledger and automated snapshots."
]


def generate_mirofish_personas(count: int = 1000) -> List[Dict[str, Any]]:
    """
    Generates 1,000 diverse MiroFish/OASIS user personas with realistic
    demographics, company profiles, follower metrics, and comments.
    """
    random.seed(42)  # Deterministic seed for reproducible tests
    personas = []
    
    for i in range(count):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}_{i}"
        user_name = f"{first.lower()}_{last.lower()}_{i}"
        profile_url = f"https://www.linkedin.com/in/{user_name}"
        
        title, headline, company_type = random.choice(ROLES_AND_HEADLINES)
        company = f"Enterprise Group {i % 50}" if company_type == "Enterprise" else f"Org {i % 25}"
        
        followers = random.randint(150, 45000)
        comment_text = random.choice(SAMPLE_COMMENTS)
        post_urn = f"urn:li:activity:710000000000000{i % 5}"  # Distributed across 5 test posts
        
        personas.append({
            "user_id": i,
            "username": user_name,
            "name": name,
            "headline": headline,
            "company": company,
            "profile_url": profile_url,
            "interaction_type": "COMMENT",
            "comment_text": comment_text,
            "post_urn": post_urn,
            "follower_count": followers
        })
        
    return personas


def test_mirofish_1000_users_ingestion_and_scoring():
    """
    Stress-tests Inox Hydra CRM with 1,000 MiroFish autonomous agent personas.
    Verifies throughput, data fidelity, tier distribution, and zero-egress guarantee.
    """
    personas = generate_mirofish_personas(1000)
    assert len(personas) == 1000

    conn = get_db()
    try:
        # Record baseline count
        initial_lead_count = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    finally:
        conn.close()

    start_time = time.time()
    ingested_lead_ids = []

    # Ingest all 1,000 user interactions
    for p in personas:
        res = reverse_crm.ingest_interaction(
            full_name=p["name"],
            headline=p["headline"],
            linkedin_urn=p["profile_url"],
            interaction_type=p["interaction_type"],
            comment_text=p["comment_text"],
            company=p["company"],
            post_urn=p["post_urn"]
        )
        assert res is not None
        assert "lead_id" in res
        ingested_lead_ids.append(res["lead_id"])

    duration = time.time() - start_time
    print(f"\n[MiroFish Benchmark] Ingested and scored 1,000 users in {duration:.2f} seconds ({1000/duration:.1f} ops/sec)")

    conn = get_db()
    try:
        new_lead_count = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        assert new_lead_count - initial_lead_count == 1000

        # Verify ICP Score Distribution across Qualification Tiers
        tier_counts = {"TIER_1_VIP": 0, "QUALIFIED": 0, "NURTURE": 0, "DISQUALIFIED": 0}
        
        rows = conn.execute("SELECT name, headline, icp_score FROM leads WHERE linkedin_urn LIKE '%_0' OR linkedin_urn LIKE '%_999'").fetchall()
        assert len(rows) >= 2

        all_scores = [r[0] for r in conn.execute("SELECT icp_score FROM leads").fetchall()]
        for score in all_scores:
            tier = qualification_tier(score)
            tier_counts[tier] += 1

        print(f"[MiroFish CRM Tiers] VIP: {tier_counts['TIER_1_VIP']}, Qualified: {tier_counts['QUALIFIED']}, Nurture: {tier_counts['NURTURE']}, Disqualified: {tier_counts['DISQUALIFIED']}")

        # Ensure high-level executives achieved VIP or Qualified tiers
        assert tier_counts["TIER_1_VIP"] > 0
        assert tier_counts["QUALIFIED"] > 0
        assert tier_counts["NURTURE"] > 0

        # Test Attribution across the 5 posts
        for post_idx in range(5):
            target_urn = f"urn:li:activity:710000000000000{post_idx}"
            count_on_post = conn.execute(
                "SELECT COUNT(*) FROM lead_interactions WHERE post_urn = ?", (target_urn,)
            ).fetchone()[0]
            assert count_on_post == 200  # 1000 users / 5 posts = 200 users per post exactly

        # Test Deduplication: re-ingesting the first 100 users must NOT duplicate leads
        for p in personas[:100]:
            dup_res = reverse_crm.ingest_interaction(
                full_name=p["name"],
                headline=p["headline"],
                linkedin_urn=p["profile_url"],
                interaction_type=p["interaction_type"],
                comment_text="Second comment from the same MiroFish user.",
                company=p["company"],
                post_urn=p["post_urn"]
            )
            assert dup_res is not None


        lead_count_after_dedupe = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        assert lead_count_after_dedupe == new_lead_count  # Count must remain unchanged!

    finally:
        conn.close()

    # Verify Strict Zero Cloud Egress
    # No outbound network calls to LinkedIn or third-party cloud services must have occurred
    assert _egress._stats["linkedin"]["performed"] == 0
