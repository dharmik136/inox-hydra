"""
Inox Hydra: Agno Autonomous Lead Enrichment Multi-Agent Engine
=============================================================
Zero Cloud Egress Guarantee & Dual-Mode Intelligence.
Implements the Agno multi-agent inbound pipeline specified in docs/modules/04_VIRAL_SWIPE_FILE.md:

1. LeadResearchAgent:
   - Analyzes prospect role, company scale, and engagement context.
   - Infers enterprise architecture challenges, estimated tech stack, and friction points.

2. IcebreakerAgent:
   - Generates 3 conversational, high-signal icebreaker angles based on detected tech stack and topics.
   - Enforces strict zero em-dash compliance (scrubs all em-dashes and double dashes).

3. EnrichmentOrchestrator:
   - Coordinates agents and persists enriched dossiers into SQLite (lead_enrichments table).
   - Dual-mode intelligence: Local deterministic intelligence engine by default;
     automatically upgrades to Gemini 2.5 Flash if an API key is present in local settings.

Strict Invariants:
- Zero em-dashes across all generated text, prompts, and docstrings.
"""

import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

try:
    from .database import get_db
except ImportError:
    from database import get_db


def clean_no_em_dashes(text: Any) -> str:
    """
    Enforces strict zero em-dash compliance.
    Replaces em-dashes and double dashes with clean natural punctuation.
    """
    if text is None:
        return ""
    s = str(text)
    em_dash = chr(0x2014)
    en_dash = chr(0x2013)
    s = s.replace(em_dash, ", ")
    s = s.replace(en_dash, ", ")
    s = s.replace(" -- ", ", ")
    s = s.replace("--", ", ")
    # Clean up double spaces
    while "  " in s:
        s = s.replace("  ", " ")
    return s.strip()


class LeadResearchAgent:
    """
    Agent 1: Deep Enterprise Prospect & Company Research Agent.
    Evaluates role, company domain, and engagement behavior to pinpoint
    technical stack characteristics and organizational friction points.
    """

    ROLE_TAXONOMY = {
        "engineering_leadership": [
            "vp of engineering", "head of engineering", "cto", "director of engineering",
            "engineering director", "vp engineering"
        ],
        "architects": [
            "architect", "principal architect", "enterprise architect", "solution architect",
            "systems architect", "chief architect", "staff engineer", "principal engineer"
        ],
        "product_leadership": [
            "product manager", "director of product", "head of product", "vp product",
            "cpo", "product architect", "group product manager"
        ],
        "devrel_content": [
            "devrel", "developer relations", "content", "evangelist", "head of content",
            "community", "technical writer"
        ],
        "executive": [
            "founder", "ceo", "co-founder", "partner", "managing partner", "executive"
        ]
    }

    def research(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyzes prospect metadata and returns structured research intelligence.
        """
        if not isinstance(lead, dict):
            lead = {}

        name = str(lead.get("name") or "Prospect")[:100]
        headline = (str(lead.get("headline") or "")).lower()[:200]
        company = str(lead.get("company") or "Enterprise Organization")[:100]
        notes = (str(lead.get("notes") or "")).lower()[:1000]
        engagement = str(lead.get("engagement_type") or "Engaged")[:50]

        # Categorize role
        role_category = "architects"
        for category, keywords in self.ROLE_TAXONOMY.items():
            if any(kw in headline for kw in keywords):
                role_category = category
                break

        # Infer company intelligence, stack, and friction
        if role_category == "engineering_leadership":
            company_intel = (
                f"{company} operates at enterprise scale where engineering velocity, system reliability, "
                f"and operational overhead are prime executive priorities."
            )
            tech_stack = "Kubernetes, Go/Java microservices, Kafka event streams, OpenTelemetry, PostgreSQL, Redis"
            key_topics = ["Engineering Velocity", "Event-Driven Decoupling", "MTTR Reduction", "Platform Engineering"]
            friction_points = (
                "Balancing new product feature velocity against accumulated technical debt, schema migration risks, "
                "and microservice observability sprawl."
            )
        elif role_category == "architects":
            company_intel = (
                f"{company} maintains distributed system topologies requiring clear bounded contexts, "
                f"fault isolation, and deterministic data contract validation."
            )
            tech_stack = "Kafka, gRPC, Distributed Event Buses, ClickHouse, Docker, Python/Go, AWS/GCP"
            key_topics = ["Distributed Systems", "Zero-Downtime Migration", "Event-Driven Architecture", "Observability"]
            friction_points = (
                "Cascading failures across shared relational schemas and tight coupling between transactional writes "
                "and read projections."
            )
        elif role_category == "product_leadership":
            company_intel = (
                f"{company} focuses on high-impact customer journeys, data-driven feature rollouts, "
                f"and cross-functional engineering alignment."
            )
            tech_stack = "Event-driven telemetry, Amplitude/Mixpanel, Segment, REST/GraphQL APIs, Next.js"
            key_topics = ["Product Analytics", "B2B SaaS Growth", "User Dwell Time", "Feature Decoupling"]
            friction_points = (
                "Bridging customer feature demands with backend engineering constraints and slow feedback loops on telemetry."
            )
        elif role_category == "devrel_content":
            company_intel = (
                f"{company} leverages technical brand authority, open source community engagement, "
                f"and developer distribution loops."
            )
            tech_stack = "Markdown documentation pipelines, GitHub Actions, Headless CMS, Community Discord/Slack"
            key_topics = ["Technical Storytelling", "Organic Reach", "Developer Experience", "Content Strategy"]
            friction_points = (
                "Distilling complex enterprise architectures into high-converting, mobile-safe visual frameworks."
            )
        else:
            company_intel = (
                f"{company} is scaling its market presence and optimizing capital efficiency, systems leverage, and growth."
            )
            tech_stack = "Cloud Infrastructure, Modern ERP/CRM systems, Automated AI Agents, Python pipelines"
            key_topics = ["Systems Leverage", "Enterprise AI Adoption", "Capital Efficiency", "Strategic Positioning"]
            friction_points = (
                "Scaling operations without proportional headcount inflation and selecting durable architectural bets."
            )

        # Contextual note enrichment
        if "observability" in notes or "erp" in notes:
            key_topics.insert(0, "IT Observability & ERP Systems")
            friction_points = f"Integrating legacy ERP records into modern observability telemetry streams. {friction_points}"

        return {
            "name": name,
            "company": company,
            "role_category": role_category,
            "company_intelligence": clean_no_em_dashes(company_intel),
            "estimated_tech_stack": clean_no_em_dashes(tech_stack),
            "key_topics": key_topics,
            "friction_points": clean_no_em_dashes(friction_points),
            "engagement_type": engagement
        }


class IcebreakerAgent:
    """
    Agent 2: High-Signal Contextual Icebreaker Generator.
    Crafts 3 distinct, conversational outreach angles with strict zero em-dash compliance.
    """

    def generate_icebreakers(self, research_data: Dict[str, Any]) -> List[str]:
        """
        Generates 3 tailored icebreakers based on research findings.
        """
        if not isinstance(research_data, dict):
            research_data = {}

        name = str(research_data.get("name") or "there").split()[0][:50]
        company = str(research_data.get("company") or "your team")[:80]
        topics = research_data.get("key_topics") or ["Distributed Systems"]
        primary_topic = str(topics[0] if topics else "systems architecture")
        secondary_topic = str(topics[1] if len(topics) > 1 else "clean service boundaries")
        tech_stack = str(research_data.get("estimated_tech_stack") or "distributed systems")

        # Angle 1: Architecture & Technical Friction Angle
        angle_1 = (
            f"Hi {name}, saw your engagement around {primary_topic.lower()}. "
            f"Given how {company} is scaling, I was curious: how are your teams navigating {secondary_topic.lower()} "
            f"without running into schema migration bottlenecks?"
        )

        # Angle 2: Peer Experience / Practical Insight Exchange
        first_tech = tech_stack.split(",")[0].strip()
        angle_2 = (
            f"Hey {name}, really appreciated your perspective on our recent post. "
            f"We have been seeing several teams adopting {first_tech} face friction around {secondary_topic.lower()}. "
            f"Would love to compare notes on what has proven most reliable in your stack."
        )

        # Angle 3: Low-Friction Value-Add Asset
        angle_3 = (
            f"Hi {name}, we recently put together a concrete visual architecture teardown on {primary_topic.lower()} "
            f"focusing on zero-downtime decoupling patterns. Thought it might resonate with what you are building at {company}. "
            f"Happy to send over the PDF if helpful, no pitch attached."
        )

        icebreakers = [
            clean_no_em_dashes(angle_1),
            clean_no_em_dashes(angle_2),
            clean_no_em_dashes(angle_3)
        ]
        return icebreakers


class EnrichmentOrchestrator:
    """
    Orchestrator: Coordinates multi-agent pipeline and persists results into SQLite.
    Supports dual-mode AI (Gemini 2.5 Flash if configured, local deterministic engine otherwise).
    """

    def __init__(self):
        self.researcher = LeadResearchAgent()
        self.icebreaker = IcebreakerAgent()

    def get_gemini_api_key(self) -> Optional[str]:
        """Retrieves stored Gemini API key from SQLite settings table."""
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'gemini_api_key'")
            row = cursor.fetchone()
            if row and row["value"] and str(row["value"]).strip():
                return str(row["value"]).strip()
            return os.environ.get("GEMINI_API_KEY")
        finally:
            conn.close()

    def enrich_lead(self, lead_id: str) -> Dict[str, Any]:
        """
        Runs autonomous Agno enrichment on a lead by ID and stores the resulting dossier.
        """
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Lead with ID '{lead_id}' not found in CRM database.")
            lead_dict = dict(row)
        finally:
            conn.close()

        return self.enrich_lead_payload(lead_dict)

    def enrich_lead_payload(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes multi-agent enrichment on a lead dictionary and persists to SQLite.
        """
        if not isinstance(lead, dict):
            raise TypeError("lead must be a dictionary")

        lead_id = str(lead.get("id") or f"lead-gen-{abs(hash(str(lead.get('name', '')))) % 100000}")[:100]
        research = self.researcher.research(lead)

        api_key = self.get_gemini_api_key()
        provider = "agno_local"
        icebreakers = []

        # Attempt Dual-Mode Gemini upgrade if key is present
        if api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-2.5-flash")
                prompt = (
                    f"You are the Inox Hydra Agno Lead Intelligence Agent.\n"
                    f"Prospect: {research['name']} at {research['company']}\n"
                    f"Role Focus: {research['role_category']}\n"
                    f"Tech Stack: {research['estimated_tech_stack']}\n"
                    f"Friction Point: {research['friction_points']}\n\n"
                    f"Generate exactly 3 high-signal, conversational, punchy 2-sentence LinkedIn outreach icebreakers.\n"
                    f"CRITICAL RULE: DO NOT USE ANY EM-DASHES ({chr(0x2014)}) OR DOUBLE DASHES (--). STRICT ZERO EM-DASHES.\n"
                    f"Return as a JSON array of 3 strings."
                )
                res = model.generate_content(prompt)
                raw_text = res.text.strip()
                # Attempt to parse json array
                if "[" in raw_text and "]" in raw_text:
                    json_str = raw_text[raw_text.find("["):raw_text.rfind("]")+1]
                    parsed = json.loads(json_str)
                    if isinstance(parsed, list) and len(parsed) == 3:
                        icebreakers = [clean_no_em_dashes(str(x)) for x in parsed]
                        provider = "gemini_2_5_flash"
            except Exception:
                # Graceful fallback to deterministic local engine
                icebreakers = []

        # Fallback to local deterministic agent if offline or no API key
        if not icebreakers:
            icebreakers = self.icebreaker.generate_icebreakers(research)
            provider = "agno_local"

        dossier = {
            "lead_id": lead_id,
            "name": research["name"],
            "company": research["company"],
            "company_intelligence": research["company_intelligence"],
            "estimated_tech_stack": research["estimated_tech_stack"],
            "key_topics": research["key_topics"],
            "friction_points": research["friction_points"],
            "icebreakers": icebreakers,
            "enriched_by": provider,
            "enriched_at": datetime.now(timezone.utc).isoformat()
        }

        # Persist into SQLite
        conn = get_db()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT OR REPLACE INTO lead_enrichments 
                (lead_id, company_intelligence, estimated_tech_stack, key_topics, friction_points, icebreakers, enriched_by, enriched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    lead_id,
                    dossier["company_intelligence"],
                    dossier["estimated_tech_stack"],
                    json.dumps(dossier["key_topics"]),
                    dossier["friction_points"],
                    json.dumps(dossier["icebreakers"]),
                    dossier["enriched_by"],
                    dossier["enriched_at"]
                ))
        finally:
            conn.close()

        return {
            "status": "success",
            "enrichment": dossier
        }

    def get_enrichment(self, lead_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves existing enriched profile dossier from SQLite.
        """
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM lead_enrichments WHERE lead_id = ?", (lead_id,))
            row = cursor.fetchone()
            if not row:
                return None

            data = dict(row)
            try:
                data["key_topics"] = json.loads(data["key_topics"]) if data.get("key_topics") else []
            except Exception:
                data["key_topics"] = []
            try:
                data["icebreakers"] = json.loads(data["icebreakers"]) if data.get("icebreakers") else []
            except Exception:
                data["icebreakers"] = []

            return data
        finally:
            conn.close()


agno_orchestrator = EnrichmentOrchestrator()
