import os
import re
import json
import requests
from typing import List, Dict, Optional, Any

try:
    from .database import get_db
    from .formatters import to_sans_bold, clean_text_formatting
    from .agno_agentos.model_gateway import get_current_ai_config, execute_llm_completion, AIProviderConfig
except ImportError:
    try:
        from database import get_db
        from formatters import to_sans_bold, clean_text_formatting
        from agno_agentos.model_gateway import get_current_ai_config, execute_llm_completion, AIProviderConfig
    except ImportError:
        get_current_ai_config = None
        execute_llm_completion = None
        AIProviderConfig = None


# -- Validation & Boundary Constants ----------------------------------------
MAX_COMMAND_LENGTH = 5000
MAX_CONTEXT_LENGTH = 10000
MAX_TOPIC_LENGTH = 1000
MAX_AUDIT_TEXT_LENGTH = 20000
MAX_REPURPOSE_INPUT_LENGTH = 10000
MAX_PROMPT_LENGTH = 15000


def get_gemini_api_key() -> Optional[str]:
    """
    Retrieves the Gemini API key from environment variables or the local SQLite settings table.
    Guarantees SQLite connection is closed even on query failure.
    """
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key and len(key.strip()) > 10:
        return key.strip()

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'gemini_api_key'")
        row = cursor.fetchone()
        if row and row["value"] and len(row["value"].strip()) > 10:
            return row["value"].strip()
    except Exception:
        pass
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    return None


def call_gemini_api(prompt: str, system_instruction: str = "") -> Optional[str]:
    """
    Direct, lightweight HTTP call to Google Gemini 2.5 Flash with zero heavy dependencies.
    Falls back gracefully if no key is configured or on network timeout.
    """
    prompt_safe = (prompt or "")[:MAX_PROMPT_LENGTH]
    if not prompt_safe.strip():
        return None

    api_key = get_gemini_api_key()
    if not api_key:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt_safe}]
            }
        ]
    }

    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }

    payload["generationConfig"] = {
        "temperature": 0.7,
        "maxOutputTokens": 2048
    }

    try:
        headers = {"Content-Type": "application/json"}
        resp = requests.post(url, json=payload, headers=headers, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
        else:
            print(f"[Gemini Bridge] Response code {resp.status_code}: {resp.text[:160]}")
    except Exception as e:
        print(f"[Gemini Bridge] Connection issue: {e}")

    return None


def get_ai_status() -> Dict[str, Any]:
    """
    Returns current Bring-Your-Own-AI (BYO-AI) Engine configuration and active mode.
    """
    if get_current_ai_config:
        cfg = get_current_ai_config()
        has_key = cfg.is_configured
        provider_name = cfg.provider
        model_name = cfg.model
        active_mode = f"{provider_name.upper()} ({model_name})" if has_key else "Antigravity Local Engine (Deterministic Zero-Egress)"
    else:
        api_key = get_gemini_api_key()
        has_key = bool(api_key)
        provider_name = "gemini" if has_key else "local_deterministic"
        model_name = "gemini-2.5-flash" if has_key else "antigravity-local"
        active_mode = "Gemini 2.5 Flash (Cloud Native)" if has_key else "Antigravity Local Engine (Deterministic Zero-Egress)"

    return {
        "provider": provider_name,
        "has_api_key": has_key,
        "model": model_name,
        "active_mode": active_mode,
        "byo_ai_enabled": True,
        "antigravity_pair_programming": True,
        "capabilities": [
            "10x_viral_hooks",
            "smart_repurpose",
            "algorithmic_audit",
            "antigravity_agent_command",
            "personalized_crm_dm"
        ]
    }


def command_ai_engine(command: Optional[str], context: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes a high-level command against the configured AI Engine (Gemini, OpenAI, Claude, Groq, Ollama,
    or Antigravity Local Engine fallback).
    Strictly enforces zero em-dashes and mathematical bolding standards.
    """
    raw_cmd = command if isinstance(command, str) else str(command or "")
    command_clean = raw_cmd.strip()[:MAX_COMMAND_LENGTH]
    if not command_clean:
        command_clean = "Draft a high-signal, punchy systems post"

    context_clean = None
    if context:
        raw_ctx = context if isinstance(context, str) else str(context)
        context_clean = raw_ctx.strip()[:MAX_CONTEXT_LENGTH]
        if not context_clean:
            context_clean = None

    system_prompt = (
        "You are the elite AI Copilot for a high-performing Content Strategist and Enterprise Systems Practitioner on LinkedIn.\n"
        "Your writing style is punchy, high-signal, authentic, and authoritative.\n"
        "CRITICAL FORMATTING RULES:\n"
        "1. NEVER use em-dashes (\u2014) or en-dashes (–). Use commas, periods, or clean line breaks instead.\n"
        "2. NO corporate clichés or generic buzzwords (avoid: 'In today's fast-paced world', 'game-changer', 'delve', 'testament').\n"
        "3. Format for mobile dwell time: short paragraphs (1-2 sentences max), generous spacing.\n"
        "4. Hook rule: The first line must stop the scroll instantly.\n"
        "5. Conclude with an authentic, thoughtful question or takeaway."
    )

    full_prompt = f"Command: {command_clean}\n\n"
    if context_clean:
        full_prompt += f"Context/Draft:\n{context_clean}\n\n"
    full_prompt += "Generate the optimized response. Remember: NEVER use em-dashes."

    ai_out = None
    engine_name = "Antigravity Local Engine"

    # Route through configured BYO-AI provider
    if get_current_ai_config and execute_llm_completion:
        cfg = get_current_ai_config()
        if cfg.is_configured:
            try:
                ai_out = execute_llm_completion(cfg, full_prompt, system_prompt=system_prompt, max_tokens=1500)
                if ai_out:
                    engine_name = f"{cfg.provider.capitalize()} ({cfg.model})"
            except Exception as e:
                print(f"[BYO-AI] Completion failed on {cfg.provider}: {e}")

    # Fallback to direct Gemini if available
    if not ai_out:
        gemini_out = call_gemini_api(full_prompt, system_instruction=system_prompt)
        if gemini_out:
            ai_out = gemini_out
            engine_name = "Gemini 2.5 Flash"

    if ai_out:
        cleaned = clean_text_formatting(ai_out.strip())
        return {
            "status": "success",
            "engine": engine_name,
            "output": cleaned
        }

    # Deterministic Antigravity Local Fallback
    source_text = context_clean or command_clean
    lines = [l.strip() for l in source_text.splitlines() if l.strip()]
    topic = lines[0] if lines else "enterprise systems and content strategy"
    topic_clean = re.sub(r'^(write|create|draft|stepping into|how to|why)\s*', '', topic, flags=re.IGNORECASE).strip()

    fallback_post = (
        f"{to_sans_bold('Zero manual intervention.')}\n\n"
        f"That is the single metric that matters when building systems around {topic_clean}.\n\n"
        f"Here is why:\n\n"
        f"Most teams focus on typing faster.\n"
        f"Top practitioners focus on deterministic architecture.\n\n"
        f"Three principles that compound over time:\n\n"
        f"1. Decouple business logic from transient storage.\n"
        f"2. Make every state transition auditable.\n"
        f"3. Eliminate manual handoffs between teams.\n\n"
        f"Simple principles. Difficult discipline.\n\n"
        f"What is your team's standard?"
    )

    return {
        "status": "success",
        "engine": "Antigravity Local Engine",
        "output": clean_text_formatting(fallback_post)
    }


def generate_10x_hooks(topic_or_draft: Optional[str]) -> List[Dict[str, Any]]:
    """
    Generates 10 proven, high-converting LinkedIn hook archetypes for any topic or existing draft.
    Uses Gemini 2.5 Flash if configured; falls back to instantaneous deterministic templates.
    """
    raw_topic = topic_or_draft if isinstance(topic_or_draft, str) else str(topic_or_draft or "")
    clean_topic = raw_topic.strip()[:MAX_TOPIC_LENGTH]
    lines = [l.strip() for l in clean_topic.splitlines() if l.strip()]
    first_line = lines[0] if lines else clean_topic
    subject = re.sub(r'^(stepping into|how to|why|stop doing|the truth about|the secret to|lessons from)\s*', '', first_line, flags=re.IGNORECASE).strip()
    if not subject:
        subject = "enterprise systems and observability"
    subject_clean = subject.rstrip(".:,;")

    # Attempt AI generation if provider configured
    resp = None
    if get_current_ai_config and execute_llm_completion:
        cfg = get_current_ai_config()
        if cfg.is_configured:
            prompt = (
                f"Generate exactly 10 distinct, high-converting LinkedIn hooks for the topic: '{subject_clean}'.\n"
                "Archetypes required: Pattern Interrupt, Concrete Metric, Hard Lesson, Counter-Intuitive, "
                "Tactical Playbook, Cost of Inaction, Quiet Title, Unpopular Truth, Before vs After, Razor of Leverage.\n"
                "Rules:\n"
                "- NEVER use em-dashes (\u2014). Use clean punctuation.\n"
                "- First line must be under 120 characters so it does not truncate before the 'see more' button on mobile.\n"
                "- Return strictly a valid JSON array of objects with keys: 'archetype', 'hook'. Do not enclose in markdown code blocks."
            )
            try:
                resp = execute_llm_completion(cfg, prompt, system_prompt="You output ONLY raw JSON.", max_tokens=1000)
            except Exception as e:
                print(f"[BYO-AI Hooks] Failed on {cfg.provider}: {e}")

    # Fallback to direct Gemini if available
    if not resp:
        api_key = get_gemini_api_key()
        if api_key:
            prompt = (
                f"Generate exactly 10 distinct, high-converting LinkedIn hooks for the topic: '{subject_clean}'.\n"
                "Archetypes required: Pattern Interrupt, Concrete Metric, Hard Lesson, Counter-Intuitive, "
                "Tactical Playbook, Cost of Inaction, Quiet Title, Unpopular Truth, Before vs After, Razor of Leverage.\n"
                "Rules:\n"
                "- NEVER use em-dashes (\u2014). Use clean punctuation.\n"
                "- First line must be under 120 characters so it does not truncate before the 'see more' button on mobile.\n"
                "- Return strictly a valid JSON array of objects with keys: 'archetype', 'hook'. Do not enclose in markdown code blocks."
            )
            resp = call_gemini_api(prompt, system_instruction="You output ONLY raw JSON.")

    if resp:
        try:
            clean_json = resp.strip()
            if clean_json.startswith("```"):
                clean_json = re.sub(r'^```(json)?\n', '', clean_json)
                clean_json = re.sub(r'\n```$', '', clean_json)
            parsed = json.loads(clean_json)
            if isinstance(parsed, list) and len(parsed) >= 5:
                out = []
                for item in parsed[:10]:
                    hk = clean_text_formatting(item.get("hook", ""))
                    first_line_hk = hk.split("\n")[0]
                    char_len = len(first_line_hk)
                    is_safe = char_len <= 140 and len(hk) <= 240
                    out.append({
                        "archetype": item.get("archetype", "High-Converting Hook"),
                        "hook_text": hk,
                        "char_count": len(hk),
                        "mobile_safe": is_safe,
                        "predicted_score": 92 if is_safe else 80
                    })
                return out
        except Exception as e:
            print(f"[BYO-AI Hooks] Fallback to deterministic: {e}")

    # Deterministic Archetype Templates
    templates = [
        {
            "archetype": "Pattern Interrupt / Contrarian",
            "hook": f"{to_sans_bold('Zero manual intervention.')}\n\nThat is the only metric that actually matters when evaluating {subject_clean}."
        },
        {
            "archetype": "Concrete Metric & Statistic",
            "hook": f"{to_sans_bold('80% of teams are using')} {subject_clean} {to_sans_bold('wrong.')}\n\nThey optimize for speed instead of verifiable architecture."
        },
        {
            "archetype": "Hard-Won Experience",
            "hook": f"{to_sans_bold('Stepping into')} {subject_clean} {to_sans_bold('feels like learning a new language.')}\n\nLately, I have been going back to foundational drawing boards:"
        },
        {
            "archetype": "Counter-Intuitive Insight",
            "hook": f"Why faster output in {subject_clean} is actually slowing your organization down:\n\n(A 3-minute breakdown for systems practitioners)"
        },
        {
            "archetype": "Tactical Playbook",
            "hook": f"The 4-step framework for {subject_clean} that eliminated 90% of our production friction:\n\nStep 1: Clean data boundaries."
        },
        {
            "archetype": "The Cost of Inaction",
            "hook": f"If your team ignores foundational {subject_clean} in 2026, here is what quietly breaks first:"
        },
        {
            "archetype": "The Quiet Title",
            "hook": f"“Content Strategist” and “Systems Architect” sound quiet on paper.\n\nUntil you manage {subject_clean} across 12+ enterprise modules."
        },
        {
            "archetype": "Unpopular Truth",
            "hook": f"Unpopular opinion on {subject_clean}:\n\nMost meetings are a proxy for alignment that should have happened in a 2-page document."
        },
        {
            "archetype": "Before vs After Contrast",
            "hook": f"Before: Endless fire drills and reactive patches.\nAfter: Deterministic workflows with {subject_clean}.\n\nHere is how we made the shift:"
        },
        {
            "archetype": "The Razor of Leverage",
            "hook": f"The Razor of Leverage applied to {subject_clean}:\n\nIf a workflow does not compound while you sleep, it is labor, not asset creation."
        }
    ]

    out = []
    for t in templates:
        hk = clean_text_formatting(t["hook"])
        first_line_hk = hk.split("\n")[0]
        char_len = len(first_line_hk)
        is_safe = char_len <= 140 and len(hk) <= 240
        score = 90 if is_safe else 75
        out.append({
            "archetype": t["archetype"],
            "hook_text": hk,
            "char_count": len(hk),
            "mobile_safe": is_safe,
            "predicted_score": score
        })

    return out


def audit_linkedin_algorithm_safety(text: Optional[str]) -> Dict[str, Any]:
    """
    Evaluates draft content against 2026 LinkedIn newsfeed algorithmic distribution guidelines:
    1. Outbound link in post body (incurs -40% distribution penalty)
    2. Hashtag spam (>5 hashtags triggers spam filter)
    3. Wall-of-text dwell time penalty
    4. Em-dash and unnatural corporate syntax
    5. Tagging spam (>3 @mentions)
    6. Estimated dwell time (reading speed ~200 wpm)
    Guarded against null inputs and truncated to MAX_AUDIT_TEXT_LENGTH.
    """
    raw_text = text if isinstance(text, str) else str(text or "")
    text_clean = raw_text[:MAX_AUDIT_TEXT_LENGTH]

    if not text_clean.strip():
        return {
            "safety_score": 100,
            "status_label": "Empty Draft",
            "word_count": 0,
            "estimated_dwell_seconds": 0,
            "penalties": [],
            "recommendations": ["Draft is empty. Add draft content to run algorithmic distribution safety analysis."],
            "has_outbound_links": False,
            "hashtag_count": 0,
            "mention_count": 0
        }

    penalties = []
    recommendations = []
    safety_score = 100

    # 1. Outbound link check
    url_pattern = r'https?://[^\s]+|www\.[^\s]+'
    urls_found = re.findall(url_pattern, text_clean)
    if urls_found:
        safety_score -= 35
        penalties.append("Outbound URL detected in post body (-40% algorithmic reach penalty).")
        recommendations.append("Move external links to the 1st comment or profile banner to maximize organic feed impressions.")

    # 2. Hashtags check
    hashtags = re.findall(r'#\w+', text_clean)
    if len(hashtags) > 5:
        safety_score -= 15
        penalties.append(f"Hashtag stuffing ({len(hashtags)} tags detected; maximum optimal is 3-5).")
        recommendations.append("Reduce to 3-5 niche-relevant tags to avoid spam categorization.")
    elif len(hashtags) == 0:
        recommendations.append("Consider adding 2-3 focused hashtags (e.g. #Enterprise #Systems #Architecture) to aid discovery.")

    # 3. Wall of text check (dense paragraphs > 3 lines without double line breaks)
    paragraphs = text_clean.split("\n\n")
    dense_paragraphs = [p for p in paragraphs if len(p.splitlines()) > 3]
    if dense_paragraphs:
        safety_score -= 15
        penalties.append("Dense paragraph detected (reduces mobile dwell time and scroll stoppage).")
        recommendations.append("Insert line breaks after 1-2 sentences for clean visual cadence.")

    # 4. Em-dashes check
    if chr(0x2014) in text_clean or chr(0x2013) in text_clean:
        safety_score -= 5
        penalties.append("Em-dashes detected (unnatural punctuation).")
        recommendations.append("Click 'Clean Formatting' to use clean commas or periods.")

    # 5. Mentions check
    mentions = re.findall(r'@\w+', text_clean)
    if len(mentions) > 3:
        safety_score -= 10
        penalties.append(f"Excessive tags ({len(mentions)} @mentions).")
        recommendations.append("Tagging >3 people who do not reply within 60 minutes demotes post reach.")

    # 6. Dwell time estimation
    words = len(re.findall(r'\b\w+\b', text_clean))
    est_seconds = int((words / 200) * 60)

    if est_seconds < 15 and len(text_clean.strip()) > 0:
        recommendations.append("Post is brief (<15s read time). Expand on 1-2 core actionable points to boost dwell time.")
    elif 45 <= est_seconds <= 90:
        recommendations.append("Optimal dwell time window (45-90 seconds). High algorithmic retention potential.")

    final_score = max(safety_score, 20)
    status_label = "Optimal" if final_score >= 85 else ("Moderate Risk" if final_score >= 60 else "High Penalty Risk")

    return {
        "safety_score": final_score,
        "status_label": status_label,
        "word_count": words,
        "estimated_dwell_seconds": est_seconds,
        "penalties": penalties,
        "recommendations": recommendations,
        "has_outbound_links": bool(urls_found),
        "hashtag_count": len(hashtags),
        "mention_count": len(mentions)
    }


def repurpose_content(raw_text: Optional[str]) -> List[Dict[str, str]]:
    """
    Transforms raw notes or existing draft into 5 distinct high-performing LinkedIn frameworks.
    Uses Gemini 2.5 Flash if available, with instantaneous fallback to deterministic templates.
    Guarded against null inputs and truncated to MAX_REPURPOSE_INPUT_LENGTH.
    """
    text_str = raw_text if isinstance(raw_text, str) else str(raw_text or "")
    clean_input = clean_text_formatting(text_str.strip()[:MAX_REPURPOSE_INPUT_LENGTH])
    if not clean_input:
        clean_input = "Zero manual intervention and deterministic systems architecture."

    # Attempt AI generation if provider configured
    resp = None
    prompt = (
        f"Repurpose this thought/draft into 5 distinct LinkedIn post frameworks:\n\n'{clean_input}'\n\n"
        "Frameworks:\n"
        "1. The Contrarian Pattern Interrupt\n"
        "2. The 3-Step Tactical Breakdown\n"
        "3. The Hard Truth / Anti-Pattern\n"
        "4. The Razor of Leverage\n"
        "5. The Personal Practitioner Narrative\n\n"
        "Rules:\n"
        "- NEVER use em-dashes (\u2014). Use clean commas, periods, or line breaks.\n"
        "- Short paragraphs (1-2 sentences), generous line breaks.\n"
        "- Return strictly a valid JSON array of objects with keys: 'framework', 'content'. No markdown code blocks."
    )

    if get_current_ai_config and execute_llm_completion:
        cfg = get_current_ai_config()
        if cfg.is_configured:
            try:
                resp = execute_llm_completion(cfg, prompt, system_prompt="You output ONLY raw JSON.", max_tokens=1500)
            except Exception as e:
                print(f"[BYO-AI Repurpose] Failed on {cfg.provider}: {e}")

    # Fallback to direct Gemini if available
    if not resp:
        api_key = get_gemini_api_key()
        if api_key:
            resp = call_gemini_api(prompt, system_instruction="You output ONLY raw JSON.")

    if resp:
        try:
            clean_json = resp.strip()
            if clean_json.startswith("```"):
                clean_json = re.sub(r'^```(json)?\n', '', clean_json)
                clean_json = re.sub(r'\n```$', '', clean_json)
            parsed = json.loads(clean_json)
            if isinstance(parsed, list) and len(parsed) >= 3:
                return [
                    {
                        "framework": item.get("framework", "Framework"),
                        "content": clean_text_formatting(item.get("content", ""))
                    }
                    for item in parsed
                ]
        except Exception as e:
            print(f"[BYO-AI Repurpose] Fallback to deterministic: {e}")

    # Deterministic Fallback Templates
    words = clean_input.split()
    headline = " ".join(words[:8]) if words else "Enterprise Systems Framework"

    f1 = (
        f"{to_sans_bold('Zero manual intervention.')}\n\n"
        f"That is the single metric that matters when building systems around {headline}.\n\n"
        f"Here is why:\n\n"
        f"Most teams focus on typing faster. Top practitioners focus on deterministic execution.\n\n"
        f"What is your team's standard?"
    )

    f2 = (
        f"{to_sans_bold('Stepping into this feels like learning a new language.')}\n\n"
        f"Lately, I have been dissecting foundational architectures around {headline}:\n\n"
        f"1. Decouple your business logic from transient storage.\n"
        f"2. Make every state transition auditable.\n"
        f"3. Eliminate manual handoffs between teams.\n\n"
        f"Simple principles. Difficult discipline."
    )

    f3 = (
        f"{to_sans_bold('80% of organizations are getting this wrong:')}\n\n"
        f"They buy software to fix a broken communication process.\n\n"
        f"Regarding {headline}:\n\n"
        f"• Tools do not fix culture\n"
        f"• Dashboards do not fix broken metrics\n"
        f"• Speed does not fix flawed direction\n\n"
        f"Fix the foundation first."
    )

    f4 = (
        f"The Razor of Leverage applied to {headline}:\n\n"
        f"If an activity does not compound while you sleep, it is labor, not asset creation.\n\n"
        f"Three assets worth building today:\n"
        f"→ Automated verification pipelines\n"
        f"→ Asynchronous documentation\n"
        f"→ High-signal network relationships"
    )

    f5 = (
        f"“Content Strategist” sounds like a quiet title for a loud job.\n\n"
        f"Managing {headline} across enterprise ecosystems taught me one truth:\n\n"
        f"The best strategy is the one that is so simple everyone on the team can repeat it without slides."
    )

    return [
        {"framework": "The Contrarian Pattern Interrupt", "content": clean_text_formatting(f1)},
        {"framework": "The 3-Step Tactical Breakdown", "content": clean_text_formatting(f2)},
        {"framework": "The Hard Truth / Anti-Pattern", "content": clean_text_formatting(f3)},
        {"framework": "The Razor of Leverage", "content": clean_text_formatting(f4)},
        {"framework": "The Personal Practitioner Narrative", "content": clean_text_formatting(f5)}
    ]
