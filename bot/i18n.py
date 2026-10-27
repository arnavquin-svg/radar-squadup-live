"""English + Hindi strings for the SquadUp Telegram bot."""
from __future__ import annotations

from typing import Any

ROLE_ORDER = ("developer", "designer", "domain_expert", "presenter")
ROLE_EMOJI = {"developer": "💻", "designer": "🎨", "domain_expert": "🧠", "presenter": "🎤"}
EXPERIENCE_ORDER = ("first_time", "some", "veteran")

STRINGS: dict[str, dict[str, Any]] = {
    "en": {
        "choose_language": "👋 Welcome to *{event}*!\nChoose your language:",
        "via_community": "You came in through *{community}* — nice to have you.",
        "via_referral": "*{name}* invited you — we'll try to seat you in their team (Team {team}).",
        "ask_role": "What will you bring to a team?",
        "ask_experience": "How many hackathons have you done before?",
        "roles": {"developer": "Developer", "designer": "Designer",
                  "domain_expert": "Domain expert", "presenter": "Presenter"},
        "experience": {"first_time": "This is my first", "some": "1–2 before", "veteran": "3 or more"},
        "registered": "🎉 You're in, {name}! Here's your squad:",
        "already": "You're already registered for *{event}*. Here's your squad:",
        "card_title": "🛡 *Team {number}* · {filled}/{size} filled",
        "slot_open": "open seat",
        "card_needs": "Looking for: {roles}",
        "card_full": "Squad complete ✅",
        "confirmed_tag": " ✓",
        "invite_cta": "👥 Invite 2 teammates",
        "invite_share_text": "Join my team for {event}! Registration takes under a minute 👇",
        "invite_explain": "Friends who join through your link get priority for the open seats in your team.\n\nYour link:\n{link}",
        "btn_my_team": "🛡 My team",
        "btn_confirm": "✅ Confirm I'm coming",
        "btn_cant": "🙁 I can't make it",
        "btn_yes_withdraw": "Yes, free my seat",
        "btn_keep": "No, keep my seat",
        "ask_withdraw": "Are you sure? Your seat will go to someone on the waitlist.",
        "withdrawn": "Done — your seat is freed. Thanks for letting us know! Send /start any time to rejoin.",
        "kept": "Great — your seat is safe.",
        "confirmed": "Confirmed ✅ Your team can count on you. See you there!",
        "ask_college": "Optional: which college or club are you from? It helps us reach more people like you.",
        "btn_skip": "Skip",
        "college_saved": "Thanks! Added {college}.",
        "skipped": "No problem.",
        "not_registered": "You're not registered yet. Send /start to join.",
        "no_events": "No events are open for registration right now. Please check back soon!",
        "error": "Something went wrong on our side. Please try again in a moment.",
        "lang_set": "Language set to English.",
        "help": ("*RadiUp.ai commands*\n"
                 "/start — register or see your squad\n"
                 "/team — your team card\n"
                 "/invite — your invite link\n"
                 "/confirm — confirm attendance\n"
                 "/lang — switch English / हिंदी\n"
                 "/demo\\_reminder — preview a reminder in 10 seconds"),
        "reminder_d7": "📅 Hi {name}! *{event}* is one week away. Team {team} is shaping up — can you confirm you're coming?",
        "reminder_d2": "⏳ Hi {name}, *{event}* is in 2 days. Team {team} is waiting for your confirmation.",
        "reminder_d1": "🚀 Hi {name}, *{event}* is tomorrow! Team {team} is waiting for your confirmation.",
        "reminder_confirmed": "🚀 See you tomorrow at *{event}*, {name}! Team {team} is counting on you.",
        "demo_scheduled": "A sample reminder will arrive in 10 seconds.",
        "slow_down": "One moment…",
        "input_rejected": "That didn't look right. Please send a plain name, under 120 characters.",
        "server_waking": "Our server is waking up. Please try again in a minute.",
    },
    "hi": {
        "choose_language": "👋 *{event}* में आपका स्वागत है!\nअपनी भाषा चुनें:",
        "via_community": "आप *{community}* के ज़रिए आए हैं — स्वागत है।",
        "via_referral": "*{name}* ने आपको बुलाया है — हम आपको उनकी टीम (टीम {team}) में जगह देने की कोशिश करेंगे।",
        "ask_role": "टीम में आपकी भूमिका क्या होगी?",
        "ask_experience": "आपने पहले कितने हैकाथॉन किए हैं?",
        "roles": {"developer": "डेवलपर", "designer": "डिज़ाइनर",
                  "domain_expert": "डोमेन विशेषज्ञ", "presenter": "प्रेज़ेंटर"},
        "experience": {"first_time": "यह मेरा पहला है", "some": "1–2 बार", "veteran": "3 या ज़्यादा"},
        "registered": "🎉 आप शामिल हो गए, {name}! यह रही आपकी टीम:",
        "already": "आप *{event}* के लिए पहले से रजिस्टर्ड हैं। यह रही आपकी टीम:",
        "card_title": "🛡 *टीम {number}* · {filled}/{size} भरी",
        "slot_open": "खाली जगह",
        "card_needs": "ज़रूरत: {roles}",
        "card_full": "टीम पूरी ✅",
        "confirmed_tag": " ✓",
        "invite_cta": "👥 2 साथियों को बुलाएँ",
        "invite_share_text": "{event} में मेरी टीम से जुड़ो! रजिस्ट्रेशन एक मिनट से भी कम में 👇",
        "invite_explain": "आपके लिंक से जुड़ने वाले दोस्तों को आपकी टीम की खाली जगहों में प्राथमिकता मिलती है।\n\nआपका लिंक:\n{link}",
        "btn_my_team": "🛡 मेरी टीम",
        "btn_confirm": "✅ मैं आ रहा/रही हूँ",
        "btn_cant": "🙁 नहीं आ पाऊँगा/पाऊँगी",
        "btn_yes_withdraw": "हाँ, मेरी जगह खाली करें",
        "btn_keep": "नहीं, जगह रखें",
        "ask_withdraw": "क्या आप पक्का हैं? आपकी जगह किसी और को दे दी जाएगी।",
        "withdrawn": "हो गया — आपकी जगह खाली कर दी गई। बताने के लिए धन्यवाद! फिर से जुड़ने के लिए कभी भी /start भेजें।",
        "kept": "बढ़िया — आपकी जगह सुरक्षित है।",
        "confirmed": "पक्का ✅ आपकी टीम आप पर भरोसा कर सकती है। वहाँ मिलते हैं!",
        "ask_college": "वैकल्पिक: आप किस कॉलेज या क्लब से हैं? इससे हम आप जैसे और लोगों तक पहुँच पाते हैं।",
        "btn_skip": "छोड़ें",
        "college_saved": "धन्यवाद! {college} जोड़ दिया गया।",
        "skipped": "कोई बात नहीं।",
        "not_registered": "आप अभी रजिस्टर्ड नहीं हैं। जुड़ने के लिए /start भेजें।",
        "no_events": "अभी कोई इवेंट रजिस्ट्रेशन के लिए खुला नहीं है। जल्द ही फिर देखें!",
        "error": "हमारी तरफ़ से कुछ गड़बड़ हुई। कृपया थोड़ी देर में फिर कोशिश करें।",
        "lang_set": "भाषा हिंदी कर दी गई।",
        "help": ("*RadiUp.ai कमांड*\n"
                 "/start — रजिस्टर करें या अपनी टीम देखें\n"
                 "/team — आपका टीम कार्ड\n"
                 "/invite — आपका इनवाइट लिंक\n"
                 "/confirm — अपनी उपस्थिति पक्की करें\n"
                 "/lang — English / हिंदी बदलें\n"
                 "/demo\\_reminder — 10 सेकंड में रिमाइंडर का नमूना"),
        "reminder_d7": "📅 नमस्ते {name}! *{event}* में एक हफ़्ता बाकी है। टीम {team} तैयार हो रही है — क्या आप आने की पुष्टि करेंगे?",
        "reminder_d2": "⏳ नमस्ते {name}, *{event}* 2 दिन में है। टीम {team} आपकी पुष्टि का इंतज़ार कर रही है।",
        "reminder_d1": "🚀 नमस्ते {name}, *{event}* कल है! टीम {team} आपकी पुष्टि का इंतज़ार कर रही है।",
        "reminder_confirmed": "🚀 कल *{event}* में मिलते हैं, {name}! टीम {team} आप पर भरोसा कर रही है।",
        "demo_scheduled": "10 सेकंड में एक नमूना रिमाइंडर आएगा।",
        "slow_down": "एक पल…",
        "input_rejected": "यह सही नहीं लगा। कृपया 120 अक्षरों से कम का सादा नाम भेजें।",
        "server_waking": "हमारा सर्वर शुरू हो रहा है। कृपया एक मिनट बाद फिर कोशिश करें।",
    },
}


def t(lang: str, key: str, **kwargs: Any) -> str:
    table = STRINGS.get(lang, STRINGS["en"])
    template = table.get(key, STRINGS["en"][key])
    return template.format(**kwargs) if kwargs else template


def role_label(lang: str, role: str) -> str:
    return STRINGS.get(lang, STRINGS["en"])["roles"][role]


def experience_label(lang: str, level: str) -> str:
    return STRINGS.get(lang, STRINGS["en"])["experience"][level]


def escape_md(text: str) -> str:
    """Escape user-supplied text for Telegram's legacy Markdown parse mode."""
    for ch in ("\\", "_", "*", "`", "["):
        text = text.replace(ch, "\\" + ch)
    return text


def render_team_card(lang: str, card: dict[str, Any]) -> str:
    lines = [t(lang, "card_title", number=card["number"], filled=card["filled"], size=card["size"])]
    by_role: dict[str, list[dict[str, Any]]] = {}
    for m in card["members"]:
        by_role.setdefault(m["role"], []).append(m)
    for role in ROLE_ORDER:
        members = by_role.get(role, [])
        if members:
            for m in members:
                tick = t(lang, "confirmed_tag") if m["confirmed"] else ""
                lines.append(f"{ROLE_EMOJI[role]} {role_label(lang, role)} — {escape_md(m['first_name'])}{tick}")
        elif not card["is_full"]:
            lines.append(f"⬜ {role_label(lang, role)} — _{t(lang, 'slot_open')}_")
    lines.append("")
    if card["is_full"]:
        lines.append(t(lang, "card_full"))
    else:
        needs = ", ".join(role_label(lang, r) for r in card["missing_roles"])
        lines.append(t(lang, "card_needs", roles=needs))
    return "\n".join(lines)
