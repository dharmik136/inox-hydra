"""
CRM Lead Enrichment Agents (Agno AgentOS Inbound Intelligence)
==============================================================
Evaluates prospect roles, infers enterprise architecture friction, and synthesizes
three high-signal DM conversation starters. Enforces P6 zero em-dashes and P7 schemas.
"""

import os
import re
from typing import Dict, Any, List, Optional
import requests

from ..contracts import LeadResearchInput, LeadResearchDossier, IcebreakerAngles
from ..scar_tissue import scrub_em_dashes
from ..model_gateway import get_current_ai_config, AIProviderConfig


class LeadResearchAgent:
    """
    Agent for deep company intelligence and role taxonomy categorization.
    Strictly zero cloud egress, fully deterministic local analysis.
    """

    ROLE_TAXONOMY: Dict[str, List[str]] = {
        "engineering_leadership": [
            "vp of engineering", "head of engineering", "cto", "director of engineering",
            "engineering director", "vp engineering", "technical director"
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
            "developer advocate", "devrel", "developer relations", "technical writer",
            "developer evangelist", "community manager", "content strategist"
        ]
    }

    def research(self, lead_input: LeadResearchInput) -> LeadResearchDossier:
        """Categorizes lead and infers architecture and friction points."""
        headline = lead_input.headline.lower()
        company = lead_input.company or "Enterprise Tech"

        # Categorize role
        role_category = "general_tech"
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
                f"{company} aligns engineering outputs with business customer journeys and retention metrics."
            )
            tech_stack = "Segment, Mixpanel, BigQuery, React, Node.js, GraphQL, AWS"
            key_topics = ["Feature Adoption", "User Retention", "Data-Driven Prioritization", "Cross-Functional Flow"]
            friction_points = (
                "Translating architectural technical constraints into clear business timelines and managing cross-team dependencies."
            )
        elif role_category == "devrel_content":
            company_intel = (
                f"{company} drives developer adoption and technical community authority through clear architectural education."
            )
            tech_stack = "Docusaurus, GitHub Actions, Hugo, Algolia, Markdown, Postman, TypeScript"
            key_topics = ["Developer Experience", "Technical Education", "Open Source Community", "API Documentation"]
            friction_points = (
                "Maintaining technical documentation freshness alongside rapid production API releases and code changes."
            )
        else:
            company_intel = f"{company} scales high-leverage business operations with modern software systems."
            tech_stack = "Cloud Native Infrastructure, Modern Data Stack, Distributed Microservices"
            key_topics = ["Organizational Leverage", "Market Execution", "System Resilience"]
            friction_points = "Balancing architectural scalability with organizational agility and cost containment."

        return LeadResearchDossier(
            lead_id=lead_input.lead_id,
            role_category=role_category,
            company_intelligence=scrub_em_dashes(company_intel),
            estimated_tech_stack=tech_stack,
            key_topics=key_topics,
            friction_points=scrub_em_dashes(friction_points)
        )


class IcebreakerAgent:
    """Agent for crafting high-converting warm DM icebreakers."""

    def __init__(self, ai_config: Optional[AIProviderConfig] = None, gemini_api_key: Optional[str] = None):
        if ai_config:
            self.ai_config = ai_config
        elif gemini_api_key:
            self.ai_config = AIProviderConfig(
                provider="gemini",
                api_key=gemini_api_key,
                model="gemini-2.5-flash",
                base_url="https://generativelanguage.googleapis.com/v1beta",
                verified_at="manual",
                status="connected"
            )
        else:
            self.ai_config = get_current_ai_config()
        self.gemini_api_key = self.ai_config.api_key if self.ai_config.provider == "gemini" else None

    def generate_angles(self, lead_input: LeadResearchInput, dossier: LeadResearchDossier) -> IcebreakerAngles:
        """Synthesizes three tailored outreach angles."""
        first_name = lead_input.name.split()[0] if lead_input.name else "there"
        company = lead_input.company or "your team"
        primary_topic = dossier.key_topics[0] if dossier.key_topics else "distributed architecture"
        second_topic = dossier.key_topics[1] if len(dossier.key_topics) > 1 else "data systems"

        # Deterministic angles
        tech_angle = (
            f"Hey {first_name}, noticed your engagement on my recent breakdown. "
            f"Curious how {company} is handling {primary_topic} without letting operational sprawl slow down releases. "
            f"Are you leaning on event-driven boundaries or centralized schemas?"
        )
        resource_angle = (
            f"Hi {first_name}, thanks for checking out the post. "
            f"Recently put together an architecture blueprint on solving {dossier.friction_points.split(',')[0].lower()} "
            f"specifically for teams working with {dossier.estimated_tech_stack.split(',')[0]}. "
            f"Happy to drop the PDF link over if it is relevant to what you are building at {company}."
        )
        chat_angle = (
            f"Hey {first_name}, great connecting. Always respect engineering leaders tackling {second_topic} at scale. "
            f"Open to a quick 10-minute async chat sometime this week to compare notes on what is working for {company}?"
        )

        return IcebreakerAngles(
            lead_id=lead_input.lead_id,
            angle_technical=scrub_em_dashes(tech_angle),
            angle_resource=scrub_em_dashes(resource_angle),
            angle_conversational=scrub_em_dashes(chat_angle)
        )
