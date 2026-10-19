import os
import re
import json
import requests

try:  # the shared egress chokepoint
    from . import egress as _egress
except ImportError:
    import egress as _egress
from typing import List, Dict, Optional, Any

try:
    from .database import get_db
    from .formatters import to_sans_bold, clean_text_formatting
    from .agno_agentos.model_gateway import get_current_ai_config, execute_llm_completion, AIProviderConfig
    from .agno_agentos.model_gateway import ProviderError, last_provider_failure
except ImportError:
    try:
        from database import get_db
        from formatters import to_sans_bold, clean_text_formatting
        from agno_agentos.model_gateway import get_current_ai_config, execute_llm_completion, AIProviderConfig
        from agno_agentos.model_gateway import ProviderError, last_provider_failure
    except ImportError:
        get_current_ai_config = None
        execute_llm_completion = None
        AIProviderConfig = None
        ProviderError = RuntimeError
        last_provider_failure = None


def _ask_provider(cfg, prompt: str, system_prompt: str, max_tokens: int) -> str:
    """
    The configured provider's answer.

    A failure is raised for the creator to read, as a ProviderError the route
    answers with. It used to be printed and swallowed, and the caller then
    served its templates as a success under a banner that said the text had
    gone to the provider. A refusal by egress policy is said the same way.
    """
    try:
        return execute_llm_completion(cfg, prompt, system_prompt=system_prompt, max_tokens=max_tokens) or ""
    except _egress.EgressRefused as refused:
        raise ProviderError(f"Model requests are off on this machine. {refused}", status_code=503) from None


def _unreadable(cfg, what: str):
    return ProviderError(
        f"{cfg.provider} ({cfg.model}) answered, but not with {what} the studio could read. Nothing was changed."
    )


def _voice() -> str:
    """The creator's voice pack for a plain prompt, or "" if it cannot be read."""
    try:
        try:
            from .voice_pack import prompt_block
        except ImportError:
            from voice_pack import prompt_block
        return prompt_block()
    except Exception:
        return ""


def _voice_sent() -> List[str]:
    """What _voice() appends, in the creator's terms, or [] if it cannot be read."""
    try:
        try:
            from .voice_pack import disclosure
        except ImportError:
            from voice_pack import disclosure
        return disclosure()
    except Exception:
        return []


# -- Validation & Boundary Constants ----------------------------------------
MAX_COMMAND_LENGTH = 5000
MAX_CONTEXT_LENGTH = 10000
MAX_TOPIC_LENGTH = 1000
MAX_AUDIT_TEXT_LENGTH = 20000
MAX_REPURPOSE_INPUT_LENGTH = 10000
MAX_PROMPT_LENGTH = 15000

try:
    from .secret_settings import seal as _seal_setting, unseal as _unseal_setting
except ImportError:
    from secret_settings import seal as _seal_setting, unseal as _unseal_setting

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
        stored = _unseal_setting("gemini_api_key", row["value"]).strip() if row and row["value"] else ""
        if len(stored) > 10:
            return stored
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
    _egress.remember_secret(api_key)
    if not api_key:
        return None

    # The key goes in a header. In the URL it reached the egress ledger and
    # every printed connection error.
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
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
        headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
        # Refuses rather than connecting when this category is off. See egress.py.
        _egress.require(url, "model")
        resp = requests.post(url, json=payload, headers=headers, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
        else:
            print(f"[Gemini Bridge] Response code {resp.status_code}: {_egress.redact(resp.text[:160])}")
    except Exception as e:
        print(f"[Gemini Bridge] Connection issue: {_egress.redact(e)}")

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

    # The last provider request that failed, until one succeeds. Read by the
    # Prompt tab, so a key that stopped working is visible there too.
    failure = last_provider_failure() if (has_key and last_provider_failure) else {}

    return {
        "provider": provider_name,
        "has_api_key": has_key,
        "model": model_name,
        "active_mode": active_mode,
        "last_error": failure.get("message"),
        "last_error_at": failure.get("at"),
        # What goes with every Re-Hook and Command request once a provider is
        # connected, from the creator's own profile and posts.
        "voice_pack_sent": _voice_sent(),
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

    # Written for whoever owns this studio. It used to describe one particular
    # author, a content strategist in enterprise systems, for every user; the
    # voice pack appended below now says who the author is when the studio knows.
    system_prompt = (
        "You are a writing assistant for a practitioner who posts on LinkedIn.\n"
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
    full_prompt += _voice()

    ai_out = None
    engine_name = "Antigravity Local Engine"

    # Route through configured BYO-AI provider
    if get_current_ai_config and execute_llm_completion:
        cfg = get_current_ai_config()
        if cfg.is_configured:
            ai_out = _ask_provider(cfg, full_prompt, system_prompt, 1500)
            if not ai_out.strip():
                raise _unreadable(cfg, "an answer")
            engine_name = f"{cfg.provider.capitalize()} ({cfg.model})"

    # No silent fallback to Google.
    #
    # This read "if not ai_out: call_gemini_api(...)", and get_gemini_api_key
    # reads GEMINI_API_KEY, GOOGLE_API_KEY, or a gemini_api_key settings row,
    # none of which has anything to do with the provider the creator chose. So
    # an Anthropic user whose Anthropic call failed, or who had configured no
    # provider at all, had their draft sent to Google because a Gemini key was
    # left in settings from an earlier experiment. They were never asked, and
    # the response was labelled "Gemini 2.5 Flash" only after the fact.
    #
    # A provider that fails is now an error the creator reads, raised above.
    # Falling through to the deterministic engine below served a template as
    # the provider's answer, under a banner saying it had been sent.

    if ai_out:
        cleaned = clean_text_formatting(ai_out.strip())
        return {
            "status": "success",
            "engine": engine_name,
            "output": cleaned,
            # What went to the provider with this instruction, so the answer
            # carries its own record of what left the machine.
            "sent": ["your instruction"] + (["your Composer draft"] if context_clean else []) + _voice_sent(),
        }

    # No model, so nothing is written.
    #
    # This was a fixed post about "zero manual intervention" and "deterministic
    # architecture" with the creator's first line dropped into it, offered as
    # their own writing. For a bakery owner it was another author's opinions;
    # for anyone it was claims they had not made. An instruction needs a model
    # to carry it out, so the honest answer is to say there is none.
    return {
        "status": "success",
        "engine": "No model set up",
        "output": (
            "No model is set up, so nothing was written for this instruction. "
            "Connect a provider on the Prompt tab of the Composer inspector to run instructions. "
            "Without one, Re-Hook offers fill-in templates built around your own words, and the "
            "formatting tools work on your text."
        ),
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
        subject = "[your topic]"
    subject_clean = subject.rstrip(".:,;")

    # Attempt AI generation if provider configured
    resp = None
    configured = None
    if get_current_ai_config and execute_llm_completion:
        cfg = get_current_ai_config()
        if cfg.is_configured:
            configured = cfg
            prompt = (
                f"Generate exactly 10 distinct, high-converting LinkedIn hooks for the topic: '{subject_clean}'.\n"
                "Archetypes required: Pattern Interrupt, Concrete Metric, Hard Lesson, Counter-Intuitive, "
                "Tactical Playbook, Cost of Inaction, Quiet Title, Unpopular Truth, Before vs After, Razor of Leverage.\n"
                "Rules:\n"
                "- NEVER use em-dashes (\u2014). Use clean punctuation.\n"
                "- First line must be under 120 characters so it does not truncate before the 'see more' button on mobile.\n"
                "- Return strictly a valid JSON array of objects with keys: 'archetype', 'hook'. Do not enclose in markdown code blocks."
            ) + _voice()
            resp = _ask_provider(cfg, prompt, "You output ONLY raw JSON.", 1000)

    # No silent fallback to Google. See the note in repurpose_content: the
    # Gemini key is read from the environment and from a settings row
    # regardless of which provider the creator configured, so this sent their
    # topic to a third party they had not chosen. The configured path above
    # builds the identical prompt, so nothing is lost but the bypass.

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
                        # There was a "predicted_score" here: 92 if the hook
                        # fit the fold, 80 if not. The interface showed it as
                        # "SCORE 92", which read as a forecast of performance.
                        # Its only information is the fold verdict, which
                        # mobile_safe already carries under its real name.
                        "mobile_safe": is_safe,
                        "source": "model",
                    })
                return out
        except Exception as e:
            print(f"[BYO-AI Hooks] Unreadable answer: {_egress.redact(e)}")
    if configured is not None:
        # The provider was asked and gave nothing usable. Saying so, rather
        # than serving the templates below as though it had written them.
        raise _unreadable(configured, "hooks")

    # Fill-in templates, used only when no model is set up.
    #
    # Structure and the creator's own words, nothing else. These used to be
    # finished openings that claimed things: "80% of teams are using X
    # wrong", "eliminated 90% of our production friction", "across 12+
    # enterprise modules", one author's job titles. Every fact now has a
    # visible [placeholder] the creator replaces with theirs, so a template
    # cannot be posted as though it were true.
    templates = [
        {
            "archetype": "Pattern Interrupt",
            "hook": f"Most advice about {subject_clean} gets one thing backwards: [the thing]."
        },
        {
            "archetype": "Concrete Number",
            "hook": f"[A number you measured]. That is what {subject_clean} [did, saved or cost] for [who]."
        },
        {
            "archetype": "Hard Lesson",
            "hook": f"The hardest lesson {subject_clean} has taught [you or your team]:\n\n[The lesson, in one line.]"
        },
        {
            "archetype": "Counter-Intuitive",
            "hook": f"Why [the usual approach] to {subject_clean} [backfires], and what to do instead:"
        },
        {
            "archetype": "Tactical Playbook",
            "hook": f"[How many] steps for {subject_clean}, from [where you started]:\n\nStep 1: [the first step]."
        },
        {
            "archetype": "Cost of Inaction",
            "hook": f"What [breaks or slips] first when {subject_clean} is left alone:"
        },
        {
            "archetype": "Plain Statement",
            "hook": f"{subject_clean}, said plainly:\n\n[Your point, in one sentence.]"
        },
        {
            "archetype": "Unpopular Truth",
            "hook": f"Unpopular opinion on {subject_clean}:\n\n[Your opinion, in one sentence.]"
        },
        {
            "archetype": "Before vs After",
            "hook": f"Before: [how it used to be].\nAfter: [how it is now] with {subject_clean}.\n\n[What changed in between.]"
        },
        {
            "archetype": "Direct Question",
            "hook": f"What would change if you [did one thing differently] about {subject_clean}?"
        }
    ]

    out = []
    for t in templates:
        hk = clean_text_formatting(t["hook"])
        first_line_hk = hk.split("\n")[0]
        char_len = len(first_line_hk)
        is_safe = char_len <= 140 and len(hk) <= 240
        # No score. See the model path above: it was the fold verdict restated
        # as a number that looked like a prediction.
        out.append({
            "archetype": t["archetype"],
            "hook_text": hk,
            "char_count": len(hk),
            "mobile_safe": is_safe,
            # Said, so the interface can label these for what they are.
            "source": "template",
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
        recommendations.append("Consider adding 2-3 focused hashtags about your topic to aid discovery.")

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
    given = bool(clean_input)

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
    ) + _voice()

    configured = None
    if get_current_ai_config and execute_llm_completion:
        cfg = get_current_ai_config()
        if cfg.is_configured:
            configured = cfg
            resp = _ask_provider(cfg, prompt, "You output ONLY raw JSON.", 1500)

    # No silent fallback to Google. See the note in repurpose_content: the
    # Gemini key is read from the environment and from settings regardless of
    # which provider the creator configured, so this routed their content to a
    # third party they had not chosen.

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
            print(f"[BYO-AI Repurpose] Unreadable answer: {_egress.redact(e)}")
    if configured is not None:
        raise _unreadable(configured, "posts")

    # Fill-in frameworks, used only when no model is set up.
    #
    # The creator's text, laid out five ways, with a [placeholder] wherever a
    # point of theirs has to go. These were finished posts that claimed "80% of
    # organizations are getting this wrong" and "lately, I have been
    # dissecting foundational architectures", whatever the notes were about.
    notes = clean_input if given else "[Your notes.]"
    words = clean_input.split()
    headline = " ".join(words[:8]) if words else "[your topic]"

    f1 = (
        f"Most advice about {headline} gets one thing backwards: [the thing].\n\n"
        f"{notes}\n\n"
        f"[What you do instead, in one or two sentences.]\n\n"
        f"[A question for your readers?]"
    )

    f2 = (
        f"[How many] steps for {headline}:\n\n"
        f"1. [The first step.]\n"
        f"2. [The second step.]\n"
        f"3. [The third step.]\n\n"
        f"{notes}"
    )

    f3 = (
        f"The hard truth about {headline}: [your point].\n\n"
        f"{notes}\n\n"
        f"[What to stop doing.]"
    )

    f4 = (
        f"One rule for {headline}: [the rule].\n\n"
        f"{notes}\n\n"
        f"[Why the rule holds.]"
    )

    f5 = (
        f"[When and where it happened.]\n\n"
        f"{notes}\n\n"
        f"[What you took from it.]"
    )

    return [
        {"framework": "The Contrarian Pattern Interrupt", "content": clean_text_formatting(f1)},
        {"framework": "The 3-Step Tactical Breakdown", "content": clean_text_formatting(f2)},
        {"framework": "The Hard Truth / Anti-Pattern", "content": clean_text_formatting(f3)},
        {"framework": "The Razor of Leverage", "content": clean_text_formatting(f4)},
        {"framework": "The Personal Practitioner Narrative", "content": clean_text_formatting(f5)}
    ]
