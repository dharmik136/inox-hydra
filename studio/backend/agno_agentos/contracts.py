"""
Agno AgentOS Pydantic Contracts (P1/P7 Structure-as-Law)
=========================================================
Strict typed schemas defining all Agent inputs, outputs, and validation rules.
No untyped dicts or ambiguous payloads cross agent boundaries.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator


# ==========================================
# 1. AI IMAGE STUDIO CONTRACTS
# ==========================================

class ImagePromptInput(BaseModel):
    """Input parameters provided by creator for generative image synthesis."""
    concept: str = Field(..., min_length=3, description="Creator's raw visual idea or concept")
    aspect_ratio: str = Field(default="1:1", description="Target aspect ratio (1:1, 4:5, 16:9)")
    visual_style: str = Field(default="photorealistic", description="Visual aesthetic style key")
    color_palette: str = Field(default="navy_cyan", description="Color mood and tone")
    lighting: str = Field(default="studio", description="Lighting environment")
    render_quote_overlay: bool = Field(default=True, description="Whether to composite elegant typography for quotes")
    custom_quote_text: Optional[str] = Field(default=None, description="Custom quote text to composite")
    custom_quote_author: Optional[str] = Field(default=None, description="Custom quote author to composite")


class SynthesizedImagePrompt(BaseModel):
    """Structured master prompt output produced by ImagePromptSynthesizerAgent."""
    master_prompt: str = Field(..., description="Engineered prompt with camera, composition, and style details")
    negative_prompt: str = Field(default="", description="Negative constraints to suppress artifacts")
    aspect_ratio: str = Field(default="1:1", description="Validated aspect ratio")
    width: int = Field(default=1080, description="Pixel width")
    height: int = Field(default=1080, description="Pixel height")
    technical_parameters: Dict[str, Any] = Field(default_factory=dict, description="Generation metadata")
    aesthetic_notes: str = Field(default="", description="Design rationale for the composition")
    quote_text: Optional[str] = Field(default=None, description="Extracted quote text if applicable")
    quote_author: Optional[str] = Field(default=None, description="Extracted quote author if applicable")


# ==========================================
# 2. LINKEDIN CONTENT COPILOT CONTRACTS
# ==========================================

class CopilotDraftInput(BaseModel):
    """Input payload for LinkedIn post drafting and hook optimization."""
    raw_content: str = Field(..., min_length=10, description="Draft text or brain-dump")
    target_audience: str = Field(default="Engineering & Product Leaders", description="Target audience persona")
    post_format: str = Field(default="framework_breakdown", description="Post narrative structure")
    attached_media_type: Optional[str] = Field(default=None, description="Type of attached media: image, carousel, video, or none")


class CopilotDraftResponse(BaseModel):
    """Structured copilot response with formatted copy, hook variants, and dwell telemetry."""
    optimized_content: str = Field(..., description="Cleaned, formatted post with line breaks and mathematical bold")
    hook_variants: List[str] = Field(default_factory=list, description="5-10 scroll-stopping hook alternatives")
    dwell_time_seconds: int = Field(default=45, description="Estimated reading dwell time in seconds")
    fold_safe: bool = Field(default=True, description="Whether the primary hook fits under the 180-char fold")
    pre_fold_chars: int = Field(default=140, description="Exact character count of opening hook")
    media_callout: Optional[str] = Field(default=None, description="Contextual swipe or watch callout for attached media")


# ==========================================
# 3. INBOUND CRM LEAD ENRICHMENT CONTRACTS
# ==========================================

class LeadResearchInput(BaseModel):
    """Raw prospect profile captured from LinkedIn interaction."""
    lead_id: str = Field(..., description="Unique lead identifier")
    name: str = Field(..., description="Full prospect name")
    headline: Optional[str] = Field(default="", description="LinkedIn headline/job title")
    company: Optional[str] = Field(default="Enterprise Organization", description="Current company")
    profile_url: Optional[str] = Field(default="", description="LinkedIn URL")
    engagement_type: str = Field(default="Commented", description="Commented, Liked, or Reposted")
    post_id: Optional[str] = Field(default="", description="ID of post engaged with")
    notes: Optional[str] = Field(default="", description="Manual notes or context")


class LeadResearchDossier(BaseModel):
    """Deep enterprise research dossier for a prospect."""
    lead_id: str = Field(..., description="Lead ID")
    role_category: str = Field(..., description="Categorized seniority level")
    company_intelligence: str = Field(..., description="Enterprise operational scale summary")
    estimated_tech_stack: str = Field(..., description="Inferred software architecture & data stack")
    key_topics: List[str] = Field(default_factory=list, description="Core technical focus areas")
    friction_points: str = Field(..., description="Likely organizational & technical pain points")


class IcebreakerAngles(BaseModel):
    """Contextual warm DM starter angles."""
    lead_id: str = Field(..., description="Lead ID")
    angle_technical: str = Field(..., description="Architecture or technical question angle")
    angle_resource: str = Field(..., description="Blueprint or playbook share angle")
    angle_conversational: str = Field(..., description="Low-friction quick conversation starter")


# ==========================================
# 4. VIRAL SWIPE FILE HARVESTER CONTRACTS
# ==========================================

class SwipePostAnalysisInput(BaseModel):
    """Input payload of a viral post to be reverse-engineered."""
    post_id: str = Field(..., description="Swipe post ID")
    author_name: str = Field(..., description="Original creator name")
    content: str = Field(..., min_length=20, description="Full text of viral post")
    topic: Optional[str] = Field(default="Engineering Leadership", description="Subject area")


class SwipePostPattern(BaseModel):
    """Extracted architectural blueprint and reusable template from a viral post."""
    post_id: str = Field(..., description="Post ID")
    hook_archetype: str = Field(..., description="e.g. Curiosity Gap, Contrarian Axiom, Metric Drop")
    tension_point: str = Field(..., description="The core conflict or counter-intuitive insight")
    structural_blueprint: str = Field(..., description="Narrative rhythm breakdown")
    reusable_template: str = Field(..., description="Fill-in-the-blanks template for creator posts")
    key_takeaways: List[str] = Field(default_factory=list, description="Key strategic lessons")
