"""Radar: audience discovery, community ranking and outreach drafting.

Pipeline (mirrors the blueprint):
  1. Event ingestion      -> the event row
  2. Profile building     -> build_profile()
  3. Community ranking    -> rank_communities()   Score = 22*overlaps + 25*(local) + size_factor
  4. Contextual drafting  -> draft_message()      en / hi / mr, facts only from the event form
  5. Human approval gate  -> enforced in main.py (drafts are created as 'pending')
"""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

OVERLAP_WEIGHT = 22
LOCAL_BONUS = 25
SIZE_FACTOR_CAP = 15

# Canonical theme -> keywords that signal it in a free-text description or tag.
THEME_KEYWORDS: dict[str, list[str]] = {
    "ai": ["ai", "artificial intelligence", "machine learning", "ml", "llm", "genai",
           "gen ai", "deep learning", "neural", "nlp", "computer vision"],
    "web": ["web", "frontend", "backend", "full stack", "fullstack", "react", "javascript"],
    "mobile": ["mobile", "android", "ios", "flutter", "app development"],
    "data": ["data", "analytics", "data science", "sql", "visualisation", "visualization"],
    "robotics": ["robot", "robotics", "arduino", "drone", "embedded", "iot", "hardware"],
    "hackathon": ["hackathon", "hack", "buildathon", "ideathon", "build sprint"],
    "design": ["design", "ui", "ux", "figma", "product design"],
    "science": ["science fair", "science", "physics", "chemistry", "biology", "research", "olympiad"],
    "cultural": ["cultural", "dance", "music", "drama", "theatre", "art", "fest", "literary"],
    "startup": ["startup", "entrepreneur", "entrepreneurship", "pitch", "founder", "e-cell"],
    "social-impact": ["social impact", "ngo", "sustainability", "climate", "civic", "community service"],
    "gaming": ["gaming", "game dev", "esports", "game jam"],
    "web3": ["blockchain", "web3", "crypto", "smart contract"],
    "cybersecurity": ["security", "cybersecurity", "ctf", "infosec"],
    "beginner": ["beginner", "beginners", "first-time", "first time", "freshers", "fresher",
                 "no experience", "newbie", "first year", "1st year"],
}

THEME_LABELS: dict[str, str] = {
    "ai": "AI", "web": "Web dev", "mobile": "Mobile", "data": "Data", "robotics": "Robotics",
    "hackathon": "Hackathons", "design": "Design", "science": "Science", "cultural": "Culture",
    "startup": "Startups", "social-impact": "Social impact", "gaming": "Gaming", "web3": "Web3",
    "cybersecurity": "Cybersecurity", "beginner": "Beginner-friendly",
}

ADVANCED_SIGNALS = ["advanced", "experienced", "expert", "senior", "phd", "professionals only"]

# Regional language most likely to land with admins in a given city.
CITY_REGIONAL_LANGUAGE: dict[str, str] = {
    "pune": "mr", "mumbai": "mr", "nagpur": "mr", "nashik": "mr",
    "delhi": "hi", "new delhi": "hi", "sonipat": "hi", "gurugram": "hi", "noida": "hi",
    "jaipur": "hi", "lucknow": "hi", "bhopal": "hi", "indore": "hi", "patna": "hi",
}

PLATFORM_LABELS = {"whatsapp": "WhatsApp", "telegram": "Telegram", "instagram": "Instagram",
                   "discord": "Discord", "facebook": "Facebook", "linkedin": "LinkedIn",
                   "reddit": "Reddit", "other": "chat"}

SUPPORTED_DRAFT_LANGUAGES = ("en", "hi", "mr")
LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "mr": "Marathi"}


# --------------------------------------------------------------------------- #
# Profile building
# --------------------------------------------------------------------------- #
def normalise_tag(tag: str) -> str:
    """Map a raw tag onto a canonical theme when possible ('Machine Learning' -> 'ai')."""
    cleaned = tag.strip().lower()
    if not cleaned:
        return ""
    for theme, keywords in THEME_KEYWORDS.items():
        if cleaned == theme or cleaned in keywords:
            return theme
    return re.sub(r"\s+", "-", cleaned)


def _keyword_hits(text: str) -> set[str]:
    hits: set[str] = set()
    lowered = f" {text.lower()} "
    for theme, keywords in THEME_KEYWORDS.items():
        for kw in keywords:
            if re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", lowered):
                hits.add(theme)
                break
    return hits


def build_profile(event: dict[str, Any]) -> dict[str, Any]:
    tags = {normalise_tag(t) for t in event.get("tags", [])}
    tags.discard("")
    text = f"{event.get('name', '')} {event.get('description', '')}"
    themes = sorted(tags | _keyword_hits(text))

    lowered = text.lower()
    if "beginner" in themes:
        skill_level = "beginner-friendly"
    elif any(sig in lowered for sig in ADVANCED_SIGNALS):
        skill_level = "advanced"
    else:
        skill_level = "open to all levels"

    city = (event.get("city") or "").strip()
    regional = CITY_REGIONAL_LANGUAGE.get(city.lower())
    languages = ["en", "hi"]
    if regional and regional not in languages:
        languages.append(regional)

    return {
        "themes": themes,
        "theme_labels": [THEME_LABELS.get(t, t.replace("-", " ").title()) for t in themes],
        "skill_level": skill_level,
        "city": city,
        "languages": languages,
        "primary_language": regional or "en",
        "team_size": event.get("team_size", 4),
    }


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #
def size_factor(size: int) -> float:
    """Diminishing returns on group size: 100 members -> 10, 1000 -> 15 (cap)."""
    return round(float(min(SIZE_FACTOR_CAP, 5 * math.log10(max(size, 1)))), 1)


def score_community(profile: dict[str, Any], community: dict[str, Any]) -> dict[str, Any]:
    community_tags = {normalise_tag(t) for t in community.get("tags", [])}
    overlaps = sorted(set(profile["themes"]) & community_tags)
    is_local = community.get("city", "").strip().lower() == profile["city"].lower()
    sf = size_factor(int(community.get("size", 0)))
    score = OVERLAP_WEIGHT * len(overlaps) + (LOCAL_BONUS if is_local else 0) + sf
    return {
        "community": community,
        "overlaps": overlaps,
        "is_local": is_local,
        "size_factor": sf,
        "score": round(score, 1),
        "rationale": build_rationale(overlaps, is_local, community),
    }


def build_rationale(overlaps: list[str], is_local: bool, community: dict[str, Any]) -> str:
    """One plain sentence explaining the score (size/platform are shown separately in the UI)."""
    labels = [THEME_LABELS.get(o, o) for o in overlaps]
    if len(labels) > 1:
        topics = f"Shares {', '.join(labels[:-1])} and {labels[-1]}"
    elif labels:
        topics = f"Shares {labels[0]}"
    else:
        topics = "No topic overlap"
    city = community.get("city", "")
    if is_local:
        where = f"local to {city}"
    elif city.lower() == "online":
        where = "online, pan-India"
    else:
        where = f"based in {city}"
    return f"{topics}; {where}."


def rank_communities(
    event: dict[str, Any],
    communities: list[dict[str, Any]],
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Return the best-fitting communities. A community needs topic overlap or locality to qualify."""
    profile = build_profile(event)
    scored = [score_community(profile, c) for c in communities]
    qualified = [s for s in scored if s["overlaps"] or s["is_local"]]
    qualified.sort(key=lambda s: (-s["score"], -len(s["overlaps"]), s["community"]["name"]))
    return qualified[:limit]


def pick_draft_language(profile: dict[str, Any], community: dict[str, Any]) -> str:
    """Prefer the regional language if the community lists it, then Hindi, then English."""
    langs = community.get("languages") or ["en"]
    regional = profile.get("primary_language", "en")
    if regional != "en" and regional in langs:
        return regional
    if "en" in langs:
        return "en"
    for lang in langs:
        if lang in SUPPORTED_DRAFT_LANGUAGES:
            return lang
    return "en"


# --------------------------------------------------------------------------- #
# Drafting — every fact here comes from the event form. No invented numbers,
# no false urgency, no testimonials.
# --------------------------------------------------------------------------- #
def _summary(description: str, max_len: int = 220) -> str:
    text = re.sub(r"\s+", " ", description or "").strip()
    if not text:
        return ""
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    if len(first) > max_len:
        first = first[: max_len - 1].rsplit(" ", 1)[0] + "…"
    return first


def _format_date(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return date.fromisoformat(raw[:10]).strftime("%d %b %Y")
    except ValueError:
        return raw


TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "greeting_named": "Hi {admin}! 👋",
        "greeting": "Hi there! 👋",
        "date": " on {date}",
        "venue": " at {venue}",
        "intro": "We're organising {event} in {city}{date}{venue}. Since {community} is into {interests}, "
                 "we thought your members might find it relevant.",
        "interests_fallback": "student events in {city}",
        "what": "What it is: {summary}",
        "beginner": "First-timers are welcome — no prior experience needed.",
        "how": "Registration takes under a minute on the web, and solo participants are matched "
               "into balanced teams of {team_size}.",
        "ask": "If you think it fits, would you be open to forwarding this to your group? Link: {link}",
        "close": "No pressure at all — thanks for reading!",
    },
    "hi": {
        "greeting_named": "नमस्ते {admin} जी! 👋",
        "greeting": "नमस्ते! 👋",
        "date": " ({date} को)",
        "venue": " — स्थान: {venue}",
        "intro": "हम {city} में {event} आयोजित कर रहे हैं{date}{venue}। {community} के सदस्य {interests} में "
                 "रुचि रखते हैं, इसलिए हमें लगा यह उनके लिए उपयोगी हो सकता है।",
        "interests_fallback": "{city} के छात्र आयोजनों",
        "what": "क्या है: {summary}",
        "beginner": "पहली बार भाग लेने वालों का भी स्वागत है — पहले अनुभव की ज़रूरत नहीं।",
        "how": "वेब चैट पर रजिस्ट्रेशन एक मिनट से भी कम में हो जाता है, और अकेले आने वालों को "
               "{team_size} लोगों की संतुलित टीम में जोड़ा जाता है।",
        "ask": "अगर आपको ठीक लगे, तो क्या आप इसे अपने ग्रुप में फ़ॉरवर्ड कर सकते हैं? लिंक: {link}",
        "close": "कोई दबाव नहीं — पढ़ने के लिए धन्यवाद!",
    },
    "mr": {
        "greeting_named": "नमस्कार {admin}! 👋",
        "greeting": "नमस्कार! 👋",
        "date": " ({date} रोजी)",
        "venue": " — ठिकाण: {venue}",
        "intro": "आम्ही {city} मध्ये {event} आयोजित करत आहोत{date}{venue}. {community} चे सदस्य {interests} "
                 "मध्ये रस घेतात, म्हणून हे त्यांच्यासाठी उपयुक्त ठरेल असं आम्हाला वाटलं.",
        "interests_fallback": "{city} मधील विद्यार्थी उपक्रमां",
        "what": "काय आहे: {summary}",
        "beginner": "पहिल्यांदाच सहभागी होणाऱ्यांचेही स्वागत आहे — आधीच्या अनुभवाची गरज नाही.",
        "how": "वेब चॅटवर नोंदणी एका मिनिटापेक्षा कमी वेळात होते, आणि एकट्याने येणाऱ्यांना "
               "{team_size} जणांच्या संतुलित टीममध्ये जोडलं जातं.",
        "ask": "तुम्हाला योग्य वाटल्यास, हे तुमच्या ग्रुपमध्ये फॉरवर्ड कराल का? लिंक: {link}",
        "close": "कोणताही दबाव नाही — वाचल्याबद्दल धन्यवाद!",
    },
}


def draft_message(
    event: dict[str, Any],
    community: dict[str, Any],
    overlaps: list[str],
    language: str,
    link: str,
) -> str:
    lang = language if language in TEMPLATES else "en"
    t = TEMPLATES[lang]
    profile = build_profile(event)
    topic_overlaps = [o for o in overlaps if o != "beginner"]

    admin = (community.get("admin_name") or "").strip()
    greeting = t["greeting_named"].format(admin=admin) if admin else t["greeting"]

    pretty_date = _format_date(event.get("start_date"))
    venue = (event.get("venue") or "").strip()
    interests = (
        ", ".join(THEME_LABELS.get(o, o) for o in topic_overlaps)
        if topic_overlaps
        else t["interests_fallback"].format(city=event["city"])
    )

    lines = [
        greeting,
        "",
        t["intro"].format(
            event=event["name"],
            city=event["city"],
            date=t["date"].format(date=pretty_date) if pretty_date else "",
            venue=t["venue"].format(venue=venue) if venue else "",
            community=community["name"],
            interests=interests,
        ),
        "",
    ]
    summary = _summary(event.get("description", ""))
    if summary:
        lines.append(t["what"].format(summary=summary))
    if profile["skill_level"] == "beginner-friendly":
        lines.append(t["beginner"])
    lines.append(t["how"].format(team_size=event.get("team_size", 4)))
    lines += ["", t["ask"].format(link=link), t["close"]]
    return "\n".join(lines)
