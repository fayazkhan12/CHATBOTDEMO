"""What the chat remembers between messages.

The model only sees the text we send it, so "memory" means sending the right text. Three things were
going wrong before this file existed:

1. The <search> block the model wrote was stripped from the history the browser sends back. The model then
   saw its own earlier "showing options" replies WITHOUT a block, learned that this is how it answers, and
   later said "showing premium hotels" without searching anything.
2. The model was never told what the screen shows, so "which one is cheapest?" or "tell me about the second
   one" had no answer.
3. The city had to be repeated: it was checked against the last few messages only.

The browser now sends (all optional, all untrusted, all re-checked here):

    history  [{role, text, search?}]   the last messages; `search` = the verified block of that turn
    context.trip       the last search that ran
    context.results    the cards on screen: {service, total, shown, items: [{n, title, price, ...}]}
    context.selection  the hotel the visitor opened or booked

and this file turns them into plain text for the model, and checks the model's answer for the one mistake that
hurts most: promising results without asking for them.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

SERVICES = ("hotels", "flights", "buses", "rides")      # "cabs" is the old name of "rides"
TIERS = ("low", "medium", "high")
VEHICLES = ("bike", "auto", "cab", "any")

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_TAGS = re.compile(r"</?\s*(search|ride|open)\s*>", re.I)
_ANGLE = re.compile(r"[<>]")
_ID = re.compile(r"^[A-Za-z0-9_.:\-]{1,40}$")
_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}$")


def text(value: Any, limit: int = 80) -> str:
    """One line of plain text: no control characters, no angle brackets (so nobody can fake a tag)."""
    s = _CTRL.sub("", str(value if value is not None else ""))
    s = _ANGLE.sub("", " ".join(s.split()))
    return s[:limit].strip()


def _day(value: Any) -> Optional[str]:
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date().isoformat()
    except (TypeError, ValueError):
        return None


def clean_search(raw: Any) -> Optional[Dict[str, Any]]:
    """A safe copy of a search block (only known keys, right types), or None when it is not usable."""
    if not isinstance(raw, dict):
        return None
    service = str(raw.get("service") or "").strip().lower()
    if service == "cabs":
        service = "rides"
    if service not in SERVICES:
        return None
    out: Dict[str, Any] = {"service": service}
    for key in ("origin", "destination", "area", "pickup", "drop"):
        if key in raw:
            out[key] = text(raw.get(key))
    dest_id = raw.get("destination_id")
    if isinstance(dest_id, (str, int)) and _ID.match(str(dest_id)):
        out["destination_id"] = str(dest_id)
    for key in ("start_date", "end_date"):
        d = _day(raw.get(key))
        if d:
            out[key] = d
    try:
        n = int(raw.get("travellers"))
        if 1 <= n <= 10:
            out["travellers"] = n
    except (TypeError, ValueError):
        pass
    if raw.get("budget_tier") in TIERS:
        out["budget_tier"] = raw["budget_tier"]
    try:
        b = float(raw.get("budget"))
        if 0 < b <= 10_000_000:
            out["budget"] = b
    except (TypeError, ValueError):
        pass
    if raw.get("vehicle") in VEHICLES:
        out["vehicle"] = raw["vehicle"]
    when = str(raw.get("when") or "").strip()
    if when.lower() == "now" or _WHEN.match(when):
        out["when"] = "now" if when.lower() == "now" else when
    return out


def block_json(block: Dict[str, Any]) -> str:
    return json.dumps(block, ensure_ascii=False, separators=(",", ":"))


def render_history(history: Any, max_items: int = 30, max_chars: int = 1000) -> List[Tuple[str, str]]:
    """[(role, text)] with role "user" or "model". Replies that ran a search get their block back."""
    items: List[Tuple[str, str]] = []
    for h in (history if isinstance(history, list) else [])[-max_items:]:
        if not isinstance(h, dict):
            continue
        who = h.get("role")
        if who not in ("user", "assistant"):
            continue
        body = _CTRL.sub("", str(h.get("text") or "")).strip()
        body = _TAGS.sub("", body)[:max_chars].strip()
        if who == "assistant":
            block = clean_search(h.get("search"))
            if block:
                body = f"{body}\n<search>{block_json(block)}</search>".strip()
            items.append(("model", body))
        else:
            items.append(("user", body))
    merged: List[Tuple[str, str]] = []
    for role, body in items:
        if not body:
            continue
        if merged and merged[-1][0] == role:          # two in a row (a failed reply in between)
            merged[-1] = (role, f"{merged[-1][1]}\n{body}"[: max_chars * 2])
        else:
            merged.append((role, body))
    while merged and merged[0][0] != "user":           # the conversation must open with the visitor
        merged.pop(0)
    return merged


def user_texts(history: Any) -> List[str]:
    return [t for r, t in render_history(history) if r == "user"]


# ------------------------------------------------------------------ the three kinds of memory
def clean_trip(ctx: Any) -> Optional[Dict[str, Any]]:
    return clean_search((ctx or {}).get("trip")) if isinstance(ctx, dict) else None


def clean_selection(ctx: Any) -> Optional[Dict[str, Any]]:
    raw = (ctx or {}).get("selection") if isinstance(ctx, dict) else None
    if not isinstance(raw, dict) or not text(raw.get("name")):
        return None
    out: Dict[str, Any] = {"name": text(raw.get("name"), 100), "kind": text(raw.get("kind") or "hotel", 12) or "hotel"}
    for key in ("city", "address", "booking_id"):
        if raw.get(key):
            out[key] = text(raw.get(key), 100)
    for key in ("check_in", "check_out"):
        d = _day(raw.get(key))
        if d:
            out[key] = d
    try:
        out["guests"] = max(1, min(10, int(raw.get("guests"))))
    except (TypeError, ValueError):
        pass
    out["status"] = "booked" if raw.get("status") == "booked" else "viewed"
    for key in ("lat", "lng"):
        try:
            v = float(raw.get(key))
            if -180 <= v <= 180:
                out[key] = round(v, 6)
        except (TypeError, ValueError):
            pass
    return out


def clean_results(ctx: Any, max_items: int = 12) -> Optional[Dict[str, Any]]:
    raw = (ctx or {}).get("results") if isinstance(ctx, dict) else None
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        return None
    service = str(raw.get("service") or "").lower()
    service = "rides" if service == "cabs" else service
    if service not in SERVICES:
        return None
    items = []
    for i, it in enumerate(raw["items"][:max_items], start=1):
        if not isinstance(it, dict) or not text(it.get("title")):
            continue
        row: Dict[str, Any] = {"n": i, "title": text(it.get("title"), 70)}
        for key in ("brand", "location", "extra"):
            if it.get(key):
                row[key] = text(it.get(key), 70)
        try:
            p = float(it.get("price"))
            if 0 <= p <= 10_000_000:
                row["price"] = int(round(p))
        except (TypeError, ValueError):
            pass
        try:
            r = float(it.get("rating"))
            if 0 < r <= 10:
                row["rating"] = round(r, 1)
        except (TypeError, ValueError):
            pass
        if isinstance(it.get("meta"), list):
            row["meta"] = [text(m, 40) for m in it["meta"][:3] if text(m, 40)]
        items.append(row)
    if not items:
        return None
    out: Dict[str, Any] = {"service": service, "items": items}
    for key in ("total", "shown"):
        try:
            out[key] = max(0, min(100000, int(raw.get(key))))
        except (TypeError, ValueError):
            pass
    if raw.get("area"):
        out["area"] = text(raw.get("area"))
    return out


# ------------------------------------------------------------------ plain-English memory for the model
def _nice(d: Optional[str]) -> str:
    try:
        return date.fromisoformat(str(d)).strftime("%a %d %b %Y")
    except (TypeError, ValueError):
        return ""


def describe_trip(trip: Dict[str, Any]) -> str:
    service = trip.get("service")
    if service == "rides":
        bits = [f"ride from {trip.get('pickup') or '?'} to {trip.get('drop') or '?'}"]
        if trip.get("vehicle") and trip["vehicle"] != "any":
            bits.append(f"vehicle: {trip['vehicle']}")
        bits.append("pickup: " + (trip.get("when") or "now"))
        return ", ".join(bits)
    if service == "hotels":
        bits = [f"hotels in {trip.get('destination') or '?'}"]
        if trip.get("area"):
            bits.append(f"near {trip['area']}")
    else:
        bits = [f"{service} from {trip.get('origin') or '?'} to {trip.get('destination') or '?'}"]
    a, b = trip.get("start_date"), trip.get("end_date")
    if a and b and a != b:
        try:
            nights = (date.fromisoformat(b) - date.fromisoformat(a)).days
        except ValueError:
            nights = 0
        bits.append(f"{a} ({_nice(a)}) to {b}" + (f", {nights} night{'s' if nights != 1 else ''}" if nights > 0 else ""))
    elif a:
        bits.append(f"on {a} ({_nice(a)})")
    if trip.get("travellers"):
        bits.append(f"{trip['travellers']} traveller{'s' if trip['travellers'] != 1 else ''}")
    if trip.get("budget_tier"):
        bits.append(f"budget tier {trip['budget_tier']}")
    elif trip.get("budget"):
        bits.append(f"maximum budget Rs {int(trip['budget'])}")
    return ", ".join(bits)


def describe_selection(sel: Dict[str, Any]) -> str:
    where = f" in {sel['city']}" if sel.get("city") else ""
    when = ""
    if sel.get("check_in") and sel.get("check_out"):
        when = f", {sel['check_in']} to {sel['check_out']}"
    guests = f", {sel['guests']} guest{'s' if sel['guests'] != 1 else ''}" if sel.get("guests") else ""
    verb = "BOOKED" if sel.get("status") == "booked" else "is looking at"
    return f"the visitor {verb} the {sel.get('kind', 'hotel')} \"{sel['name']}\"{where}{when}{guests}"


def describe_results(res: Dict[str, Any]) -> str:
    lines = []
    for it in res["items"]:
        bits = [it["title"]]
        if it.get("brand"):
            bits.append(it["brand"])
        if it.get("price") is not None:
            bits.append(f"Rs {it['price']:,}")
        if it.get("rating"):
            bits.append(f"rating {it['rating']}")
        if it.get("location"):
            bits.append(it["location"])
        if it.get("extra"):
            bits.append(it["extra"])
        if it.get("meta"):
            bits.append(", ".join(it["meta"]))
        lines.append(f"{it['n']}. " + " | ".join(bits))
    more = ""
    if res.get("total") and res.get("shown") is not None and res["total"] > res["shown"]:
        more = f" ({res['total']} found in all; only the first {res['shown']} are on screen, the rest appear when the visitor taps Show more)"
    return "\n".join(lines) + more


FOLLOW_UP_RULES = (
    "FOLLOW-UP RULES (strict):\n"
    "- When the visitor changes ANY detail (budget, guests, dates, city, area, vehicle) or asks to see options again, keep every other detail of the current trip "
    "and end your reply with a COMPLETE new <search> block, in the same reply. Never ask 'shall I show them?', 'which city?' or 'which dates?' when the memory above already has the answer.\n"
    "- cheaper / sasta / budget -> budget_tier low. normal / madhyam -> medium. premium / luxury / best / costly -> high. 'N guests / log / people' -> travellers N. "
    "A new city -> new destination with the same dates, guests and budget, and NO area.\n"
    "- A question about the results on screen (which is cheapest, best rated, closest, 'the second one') is answered from the numbered list above in one or two sentences, with NO new <search> block. "
    "Never name a result that is not in the list. For photos, rooms or exact prices tell the visitor to tap View on that card.\n"
    "- Thanks, ok, hello and other small talk: answer in one short sentence, no <search> block, and do not repeat the old search.\n"
    "- NEVER say you are showing, searching or fetching options unless the same reply ends with the <search> block."
)


def memory_prompt(trip: Optional[Dict[str, Any]], results: Optional[Dict[str, Any]], selection: Optional[Dict[str, Any]]) -> str:
    """The part of the system prompt that carries the memory. Empty when there is nothing to remember."""
    parts: List[str] = []
    if trip:
        parts.append("Current trip (the last search that ran): " + describe_trip(trip) + ".")
    if selection:
        parts.append("Hotel in focus: " + describe_selection(selection) + ".")
    if results:
        parts.append(f"Results on the visitor's screen right now ({results['service']}), numbered as they see them:\n" + describe_results(results))
    if not parts:
        return ""
    return "\n\nCONVERSATION MEMORY (kept by the app, trust it over your own guesses):\n" + "\n".join(parts) + "\n" + FOLLOW_UP_RULES


# ------------------------------------------------------------------ catching "I'm showing options" without a search
_PROMISE = re.compile(
    r"\bshowing (?:you |the |these |those |some |all |more |your |options|hotels|results|premium|cheaper|budget|luxury|flights|buses|rides)"
    r"|\bhere (?:are|is|you go)\b|\bhere's (?:the|a|some|your)\b"
    r"|\bi(?:'ll| will| am|'m) (?:show|find|search|fetch|pull|check)(?:ing)?\b"
    r"|\blet me (?:show|find|search|fetch|pull|check)\b|\bpulling up\b|\bfetching (?:the|your|some)\b|\bsearching (?:now|for the|the|options)\b"
    r"|dikha(?:te|ta|ti|ata|ati|ye|iye|oon|un)\b|dikha rah[aei]\b|dikha (?:dete|deta|deti|diya|du|dun)\b|\byeh lo\b|\bye lo\b|\bye rahe\b|\byeh rahe\b|\blijiye\b"
    r"|dhoondh|dhundh|search kar"
    r"|दिखा|ये रहे|यह रहे|ये लीजिए|खोज", re.I)
_ASKS_TO_SHOW = re.compile(
    r"(?:\b(?:shall|should|want|would you like|do you want|like) (?:me |i |us )?(?:to )?(?:show|search|see|check|look)\b[^?]*\?"
    r"|dikha(?:oon|un|ana|u)\b[^?]*\?|dikhau?n?\?|dekhna chahenge\b[^?]*\?|dekhna hai\b[^?]*\?|\bsearch (?:karun|karu)\b[^?]*\?"
    r"|दिखाऊं[^?]*\?|दिखाऊँ[^?]*\?|दिखाएं\?|दिखाएँ\?)", re.I)
_WANTS = re.compile(
    r"\b(?:show|dikha\w*|options?|list|find|search|dekh\w*|chahiye|chahie|chaiye|need|want|looking for|get me|give me|batao|btao|suggest|cheaper|cheap|sasta|sasti|premium|luxury|"
    r"expensive|costly|instead|change|badal\w*|switch|again|phir se|dobara|me|mein|ke liye|guests?|people|log)\b|दिखा|चाहिए|बताओ|खोज|बदल|फिर से|दोबारा", re.I)


def promises_results(reply: str) -> bool:
    return bool(reply and _PROMISE.search(reply))


def asks_to_show(reply: str) -> bool:
    return bool(reply and _ASKS_TO_SHOW.search(reply))


def wants_results(user_message: str) -> bool:
    return bool(user_message and _WANTS.search(user_message))


def _is_question(reply: str) -> bool:
    return reply.rstrip().endswith("?") or "?" in reply.rsplit(".", 1)[-1]


def needs_search_repair(spoken: str, has_block: bool, trip: Optional[Dict[str, Any]], user_message: str = "") -> bool:
    """True when the reply says options are coming (a false claim) or, with the trip already known, asks permission to show
    what the visitor just asked for, and carries no <search> block."""
    if has_block or not spoken:
        return False
    if promises_results(spoken) and not _is_question(spoken):
        return True
    return bool(trip) and asks_to_show(spoken) and wants_results(user_message)


# ---- questions the memory already answers ("udaipur me dikhao" -> "which dates?" although the dates are known)
_Q_DATES = re.compile(
    r"\bwhich dates?\b|\bwhat dates?\b|\bcheck-?in\b|\bwhen (?:do|will|would|are)\b|\bhow many (?:nights|days)\b|\bkitni (?:raat|rat|dates?|din)\b|\bkaun ?si dates?\b"
    r"|\bkis dates?\b|\bkab se kab\b|\bkab (?:tak|se)\b|\bkaunsi dates?\b|कितनी रात|कौन सी तारीख|कौनसी तारीख|तारीख", re.I)
_Q_GUESTS = re.compile(
    r"\bhow many (?:guests?|people|travell?ers?|adults?|persons?)\b|\bkitne (?:log|logon|guests?|travell?ers?|vyakti|members?)\b|कितने (?:लोग|यात्री|मेहमान|व्यक्ति)", re.I)
_Q_BUDGET = re.compile(r"\bbudget\b|\bsasta\b|\bmadhyam\b|\bpremium\b|\bcheap\b|बजट|सस्ता|मध्यम|प्रीमियम", re.I)
_CUE_DATES = re.compile(
    r"\b(?:date|dates|tarikh|kal|aaj|parso|tomorrow|today|tonight|night|nights|raat|raato|din|days?|week|weekend|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december|check-?in|check-?out)\b|तारीख|कल|आज|परसों|रात|दिन|\d{1,2}\s*(?:/|-)\s*\d{1,2}", re.I)
_CUE_GUESTS = re.compile(r"\d|\b(?:guest|guests|people|persons?|log|logo|adults?|couple|family|solo|alone|akele|dost|friends|members?|travell?ers?)\b|लोग|अकेले|परिवार", re.I)
_CUE_BUDGET = re.compile(
    r"\d{3,}|\b(?:budget|sasta|sasti|sastaa|cheap|cheaper|low|medium|mid|madhyam|premium|luxury|luxurious|high|expensive|costly|mehnga|mehenga|economy|affordable|normal|average|"
    r"any|anything|whatever|koi bhi|kuch bhi|fark nahi|five star|5 star|5-star|rupees?|rs|inr)\b|सस्त|मध्यम|प्रीमियम|महंग|बजट|कोई भी|कुछ भी", re.I)


def asks_budget(spoken: str) -> bool:
    return "?" in (spoken or "") and bool(_Q_BUDGET.search(spoken))


def has_budget_cue(user_message: str) -> bool:
    return bool(user_message and _CUE_BUDGET.search(user_message))


def asks_known_slot(spoken: str, trip: Optional[Dict[str, Any]], user_message: str) -> bool:
    """The reply asks for dates, guests or a budget that the current trip already has, and the visitor did not just change that detail."""
    if not trip or not spoken or "?" not in spoken or len(str(user_message or "").split()) > 8:
        return False
    if trip.get("service") not in ("hotels", "flights", "buses"):
        return False
    msg = str(user_message or "")
    if _Q_DATES.search(spoken) and trip.get("start_date") and not _CUE_DATES.search(msg):
        return True
    if _Q_GUESTS.search(spoken) and trip.get("travellers") and not _CUE_GUESTS.search(msg):
        return True
    return bool(trip.get("service") == "hotels" and _Q_BUDGET.search(spoken) and (trip.get("budget_tier") or trip.get("budget")) and not _CUE_BUDGET.search(msg))


REPAIR_NOTE = (
    "[system note] Your last reply did not run a search: it either said options were coming (or asked whether to show them) without a <search> block, "
    "or asked for details that the conversation memory already has. Reply again now: ONE short line in the visitor's language, then the complete <search> block on a new line. "
    "Take every detail the visitor did not change from the conversation memory and do not ask for it again."
)


# ------------------------------------------------------------------ last resort: a plain edit of the current trip
_LOW = re.compile(r"\b(?:cheap|cheaper|cheapest|budget|low|sasta|sasti|sastaa|sastey|affordable|economy|kam daam|kam price)\b|सस्त", re.I)
_HIGH = re.compile(r"\b(?:premium|luxury|luxurious|costly|expensive|five star|5 star|5-star|mehnga|mehenga|mahenga|high end|best)\b|प्रीमियम|महंग|लक्ज़री|लग्जरी", re.I)
_MID = re.compile(r"\b(?:medium|mid|midrange|mid-range|normal|average|madhyam|theek thaak|thik thak)\b|मध्यम", re.I)
_GUESTS = re.compile(
    r"(?<!\d)(\d{1,2})\s*(?:guests?|people|persons?|pax|adults?|log|logo|vyakti|travell?ers?|members?|जन|लोग|व्यक्ति)\b"
    r"|\bfor\s+(\d{1,2})\b(?!\s*(?:nights?|days?|din|raat))|(?<!\d)(\d{1,2})\s+ke liye\b", re.I)


def quick_edit(trip: Optional[Dict[str, Any]], user_text: str) -> Optional[Dict[str, Any]]:
    """The visitor only changed the budget or the number of guests: apply it to the current trip. None when it is anything else."""
    if not trip or trip.get("service") not in ("hotels", "flights", "buses"):
        return None
    t = " ".join(str(user_text or "").split())
    edited = dict(trip)
    changed = False
    if trip["service"] == "hotels" and not re.search(r"\d{3,}", t):          # "budget 5000" is an amount, not a tier
        tier = "high" if _HIGH.search(t) else "low" if _LOW.search(t) else "medium" if _MID.search(t) else None
        if tier and tier != trip.get("budget_tier"):
            edited["budget_tier"] = tier
            edited.pop("budget", None)
            changed = True
    m = _GUESTS.search(t)
    if m:
        n = int(next(g for g in m.groups() if g))
        if 1 <= n <= 10 and n != trip.get("travellers"):
            edited["travellers"] = n
            changed = True
    return edited if changed else None


# ------------------------------------------------------------------ words for the few fixed replies we write ourselves
FIXED = {
    "updating": {
        "en": "Sure, updating your search now.",
        "hinglish": "Theek hai, search update kar raha hoon.",
        "hi": "ठीक है, खोज अपडेट कर रहा हूँ।",
    },
    "no_search": {
        "en": "Tell me what to change: dates, guests, budget or city.",
        "hinglish": "Bataiye kya badalna hai: dates, log, budget ya shehar.",
        "hi": "बताइए क्या बदलना है: तारीख, लोग, बजट या शहर।",
    },
}


def fixed(key: str, lang: str) -> str:
    table = FIXED[key]
    return table.get(lang) or table["en"]
