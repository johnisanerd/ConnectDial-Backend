"""
ai_utils.py – Gemini AI caption generator for ConnectDial bots
──────────────────────────────────────────────────────────────
Uses google-genai SDK (pip install google-genai).

SETUP — add to your .env:
  GEMINI_API_KEY=your_key_here   ← get free key at aistudio.google.com

When Gemini works: generates personality-driven captions (hype/analytical/toxic/funny).
When Gemini fails: uses rich offline templates — NEVER falls back to a generic string.
"""

import random
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# ─── MODEL PRIORITY ──────────────────────────────────────────────────────────
_MODEL_PRIORITY = [
    'gemini-2.5-flash',
    'gemini-2.0-flash',
    'gemini-1.5-flash',
]

# ─── BOT PERSONALITIES ───────────────────────────────────────────────────────
_PERSONALITIES = {
    'hype': (
        "You are a die-hard passionate sports fan. Be extremely positive and energetic. "
        "Use phrases like 'LETS GO', 'WE ARE SO BACK', or 'INSANE'. "
        "Write like a real excited fan tweeting, not like a news anchor."
    ),
    'toxic': (
        "You are a salty rival fan reacting to news about the opposing team. "
        "Be critical but funny. Use words like 'L', 'Ratioed', 'Finished club energy'. "
        "Keep it sports banter, not personal."
    ),
    'analytical': (
        "You are a football/sports tactics analyst. Reference concepts like "
        "'expected goals', 'pressing intensity', 'defensive shape', or 'ball progression'. "
        "Sound knowledgeable and measured."
    ),
    'funny': (
        "You are a sports meme account. Use dry wit, sarcasm, and references to "
        "famous sports moments. Be genuinely funny, not try-hard."
    ),
    'fan': (
        "You are a loyal supporter reacting to news about your team. "
        "Be passionate, personal, and genuine. Write in first person."
    ),
}

# ─── RICH OFFLINE FALLBACKS (used when Gemini is unavailable) ────────────────
# These replace the old "Unreal scenes in the {league}!" single-string fallback.
# Combinatorial so every bot gets something different.

_FALLBACK_OPENERS = {
    'hype':       ["LETS GO 🔥", "WE ARE SO BACK 🙌", "HUGE NEWS 🚨", "THIS IS MASSIVE 💥", "NO WAY 🤯"],
    'toxic':      ["That's an L 💀", "Finished club energy 🤡", "Not even surprised 😂", "Ratioed 📉", "Yikes 💀"],
    'analytical': ["Tactically interesting —", "Worth noting —", "The data suggests —", "From a tactical standpoint,", "Statistically speaking,"],
    'funny':      ["Tell me you're panicking without telling me 😂", "The audacity 😭", "Bro really said 💀", "Not me screaming 😭", "This timeline 🙏"],
    'fan':        ["As a supporter,", "I genuinely cannot believe", "This changes everything —", "My heart right now 💙", "Been waiting for this —"],
}

_FALLBACK_TAKES = [
    "this is what {league} football is all about.",
    "{title} — and the season just got a lot more interesting.",
    "every {league} fan needs to pay attention to this.",
    "the {league} title race just shifted again.",
    "this is the story of the {league} season right here.",
    "{title}. I don't think people realise how big this is.",
    "football never stops surprising you — {league} proving it again.",
]

_FALLBACK_CTAS = [
    "Who else is watching this unfold? 👀",
    "Drop your take below. 💬",
    "Am I wrong? 👇",
    "Tell me I'm not the only one 😤",
    "",
    "Agree or disagree? 👀",
]

# League-specific verified facts for extra richness in fallbacks
_LEAGUE_FACTS = {
    "premier league":   ["Arsenal lead with 85pts", "Haaland Golden Boot 27 goals", "Bruno Fernandes 21 assists record"],
    "la liga":          ["Barcelona champions 29th title", "Mbappé 24 goals", "El Clásico crowd 78,107"],
    "champions league": ["Final: Budapest May 30", "Mbappé top scorer 15 UCL goals", "3.49 goals/game average"],
    "saudi pro league": ["Quiñones 28 goals top scorer", "Al-Hilal 29 unbeaten", "Al-Nassr 16-win streak"],
    "bundesliga":       ["Kane 33 goals Golden Boot", "Bayern 16pts clear", "Olise 19 assists"],
    "serie a":          ["Inter champions", "Lautaro 16 goals", "Milan 24-match unbeaten run"],
    "nba":              ["OKC defending champions", "SGA Finals MVP + scoring title", "Wembanyama Conference Finals"],
    "fifa world cup":   ["48 teams 104 matches", "Final MetLife July 19", "June 11 kickoff Mexico City"],
}


def _rich_fallback(news_title: str, league: str, personality: str = 'hype') -> str:
    """
    Produces a varied, intelligent-looking caption without Gemini.
    Never returns the same string twice in a row thanks to randomisation.
    """
    opener = random.choice(_FALLBACK_OPENERS.get(personality, _FALLBACK_OPENERS['hype']))
    take   = random.choice(_FALLBACK_TAKES).format(
        league=league,
        title=news_title[:60].strip(),
    )
    cta    = random.choice(_FALLBACK_CTAS)

    # Occasionally inject a verified league fact for credibility
    facts  = _LEAGUE_FACTS.get(league.lower(), [])
    fact_line = f" ({random.choice(facts)})" if facts and random.random() < 0.4 else ""

    parts = [f"{opener} {take}{fact_line}"]
    if cta:
        parts.append(cta)

    return " ".join(parts).strip()[:220]


# ─── MAIN FUNCTION ────────────────────────────────────────────────────────────

def generate_intelligent_caption(
    news_title: str,
    news_desc: str,
    league: str,
    team: str = None,
    personality: str = None,
) -> str:
    """
    Generates a personality-driven sports caption via Gemini.

    Personality is randomly chosen if not specified, so bots naturally vary.
    Falls back to rich offline templates (not a generic string) if Gemini fails.

    Args:
        news_title:  Article headline
        news_desc:   Article description/snippet
        league:      League name e.g. "Premier League"
        team:        Team name if known e.g. "Arsenal"
        personality: 'hype' | 'toxic' | 'analytical' | 'funny' | 'fan' | None (random)
    """
    # Randomly assign personality if not specified — gives each bot a different voice
    if not personality:
        personality = random.choice(list(_PERSONALITIES.keys()))

    # ── Try Gemini ────────────────────────────────────────────────────────────
    api_key = getattr(settings, 'GEMINI_API_KEY', None)
    if not api_key:
        logger.warning(
            "GEMINI_API_KEY not set — using offline caption. "
            "Add GEMINI_API_KEY to your .env for AI-generated captions."
        )
        return _rich_fallback(news_title, league, personality)

    try:
        from google import genai
    except ImportError:
        logger.error("google-genai not installed: pip install google-genai")
        return _rich_fallback(news_title, league, personality)

    tone   = _PERSONALITIES[personality]
    prompt = (
        f"Role: {tone}\n\n"
        f"Context:\n"
        f"League: {league}\n"
        f"Team in focus: {team or 'General News'}\n"
        f"News headline: {news_title}\n"
        f"News detail: {news_desc[:300]}\n\n"
        f"Instructions:\n"
        f"Write a social media reaction post (max 200 characters). "
        f"Stay strictly in character. Use exactly 2 emojis. "
        f"Do not use hashtags. Sound like a real person, not a press release."
    )

    client = genai.Client(api_key=api_key)

    for model in _MODEL_PRIORITY:
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            text = (response.text or "").strip()
            if text:
                logger.debug("Caption via %s [%s personality]", model, personality)
                return text[:220]
        except Exception as exc:
            logger.warning("Gemini model %s failed: %s", model, exc)
            continue

    logger.error("All Gemini models failed — using offline fallback for league=%s", league)
    return _rich_fallback(news_title, league, personality)