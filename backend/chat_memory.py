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

# Hotel filters the company's results API understands (GET /hotelSearch/search/{id}): star class, free cancellation,
# breakfast, property type, facilities, hotel name and the order. The keys below are the chat's own names for them.
FILTER_KEYS = ("stars", "free_cancel", "breakfast", "property", "amenities", "hotel_name", "order")
PROPERTIES = ("Hotel", "GuestHouse", "Resort", "Palace", "Apartment", "Villa", "Hostel", "Homestay")
AMENITIES = ("Swimming Pool", "Internet", "Parking", "Fitness Facility", "Spa", "Restaurant", "Bar", "Airport Shuttle",
             "Elevator", "Room Service", "Laundry Services", "Electric car charging stations")
ORDERS = ("cheap", "costly", "stars")


def clean_filters(raw: Any) -> Dict[str, Any]:
    """The hotel filters in a block, checked: only known values, right types. {} when there are none."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    stars = raw.get("stars")
    if isinstance(stars, (int, float, str)) and not isinstance(stars, bool):
        stars = [stars]
    if isinstance(stars, list):
        picked = set()
        for v in stars[:5]:
            try:
                n = int(float(v))
            except (TypeError, ValueError):
                continue
            if 1 <= n <= 5:
                picked.add(n)
        if picked:
            out["stars"] = sorted(picked)
    for key in ("free_cancel", "breakfast"):
        if raw.get(key) is True or str(raw.get(key)).lower() == "true":
            out[key] = True
    prop = str(raw.get("property") or "").replace(" ", "").lower()
    match = next((p for p in PROPERTIES if p.lower() == prop), None)
    if match:
        out["property"] = match
    am = raw.get("amenities")
    if isinstance(am, str):
        am = [am]
    if isinstance(am, list):
        known = {a.lower(): a for a in AMENITIES}
        picked_am = []
        for v in am[:6]:
            a = known.get(str(v).strip().lower())
            if a and a not in picked_am:
                picked_am.append(a)
        if picked_am:
            out["amenities"] = picked_am
    name = text(raw.get("hotel_name"), 60).strip()
    if len(name) >= 2:
        out["hotel_name"] = name
    if raw.get("order") in ORDERS and raw.get("order") != "cheap":
        out["order"] = raw["order"]          # cheapest first is the default: not stored
    return out


_AM_LABEL = {
    "Swimming Pool": {"en": "pool", "hinglish": "pool", "hi": "पूल"},
    "Internet": {"en": "Wi-Fi", "hinglish": "Wi-Fi", "hi": "वाई-फाई"},
    "Parking": {"en": "parking", "hinglish": "parking", "hi": "पार्किंग"},
    "Fitness Facility": {"en": "gym", "hinglish": "gym", "hi": "जिम"},
    "Spa": {"en": "spa", "hinglish": "spa", "hi": "स्पा"},
    "Restaurant": {"en": "restaurant", "hinglish": "restaurant", "hi": "रेस्टोरेंट"},
    "Bar": {"en": "bar", "hinglish": "bar", "hi": "बार"},
    "Airport Shuttle": {"en": "airport shuttle", "hinglish": "airport shuttle", "hi": "एयरपोर्ट शटल"},
    "Elevator": {"en": "lift", "hinglish": "lift", "hi": "लिफ्ट"},
    "Room Service": {"en": "room service", "hinglish": "room service", "hi": "रूम सर्विस"},
    "Laundry Services": {"en": "laundry", "hinglish": "laundry", "hi": "लॉन्ड्री"},
    "Electric car charging stations": {"en": "EV charging", "hinglish": "EV charging", "hi": "ईवी चार्जिंग"},
}
_PROP_LABEL = {"Hotel": "hotel", "GuestHouse": "guest house", "Resort": "resort", "Palace": "palace", "Apartment": "apartment",
               "Villa": "villa", "Hostel": "hostel", "Homestay": "homestay"}


def filters_label(f: Dict[str, Any], lang: str = "en") -> str:
    """'3+ star, free cancellation, pool' in the chat's language; '' when no filter is on."""
    lang = lang if lang in ("en", "hinglish", "hi") else "en"
    bits: List[str] = []
    stars = f.get("stars") or []
    if stars:
        top = stars == list(range(stars[0], 6))
        if len(stars) == 1:
            bits.append({"hi": f"{stars[0]} स्टार"}.get(lang, f"{stars[0]} star"))
        elif top:
            bits.append({"en": f"{stars[0]}+ star", "hinglish": f"{stars[0]} star se upar", "hi": f"{stars[0]} स्टार से ऊपर"}[lang])
        else:
            bits.append({"hi": "/".join(map(str, stars)) + " स्टार"}.get(lang, "/".join(map(str, stars)) + " star"))
    if f.get("free_cancel"):
        bits.append({"en": "free cancellation", "hinglish": "free cancellation", "hi": "फ्री कैंसिलेशन"}[lang])
    if f.get("breakfast"):
        bits.append({"en": "breakfast included", "hinglish": "breakfast ke saath", "hi": "नाश्ते के साथ"}[lang])
    if f.get("property"):
        bits.append(_PROP_LABEL.get(f["property"], f["property"]))
    for a in f.get("amenities") or []:
        bits.append(_AM_LABEL.get(a, {}).get(lang, a))
    if f.get("hotel_name"):
        bits.append({"en": f'name "{f["hotel_name"]}"', "hinglish": f'naam "{f["hotel_name"]}"', "hi": f'नाम "{f["hotel_name"]}"'}[lang])
    if f.get("order") == "costly":
        bits.append({"en": "costliest first", "hinglish": "mehenge pehle", "hi": "महंगे पहले"}[lang])
    elif f.get("order") == "stars":
        bits.append({"en": "most stars first", "hinglish": "zyada star wale pehle", "hi": "ज़्यादा स्टार वाले पहले"}[lang])
    return ", ".join(bits)


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


def occupancy(raw: Any) -> Dict[str, Any]:
    """The optional rooms / children of a hotel block, checked: {"rooms": 1-5, "children": 1-6, "child_ages": [0-17, one per child]}.
    A part that is missing or wrong is left out (children without one valid age per child are left out as a whole)."""
    out: Dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    try:
        rooms = int(raw.get("rooms"))
        if 1 <= rooms <= 5:
            out["rooms"] = rooms
    except (TypeError, ValueError):
        pass
    try:
        kids = int(raw.get("children"))
        ages = [int(a) for a in (raw.get("child_ages") or [])]
        if 1 <= kids <= 6 and len(ages) == kids and all(0 <= a <= 17 for a in ages):
            out["children"], out["child_ages"] = kids, ages
    except (TypeError, ValueError):
        pass
    return out


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
    if service == "hotels":          # rooms and children of a hotel search (travellers = the adults)
        occ = occupancy(raw)
        if occ:
            out.update(occ)
        out.update(clean_filters(raw))
    if raw.get("budget_tier") in TIERS:
        out["budget_tier"] = raw["budget_tier"]
    for key in ("budget", "budget_min"):
        try:
            b = float(raw.get(key))
            if 0 < b <= 10_000_000:
                out[key] = b
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
    note = text(raw.get("note"), 200)
    if not items and not note and raw.get("total") != 0:
        return None
    out: Dict[str, Any] = {"service": service, "items": items}
    if note:
        out["note"] = note
    if raw.get("widened"):
        out["widened"] = True
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
    if service == "hotels" and trip.get("children"):
        ages = ", ".join(str(a) for a in (trip.get("child_ages") or []))
        bits.append(f"{trip['children']} child{'ren' if trip['children'] != 1 else ''}" + (f" (ages {ages})" if ages else ""))
    if service == "hotels" and (trip.get("rooms") or 1) > 1:
        bits.append(f"{trip['rooms']} rooms")
    if trip.get("budget_tier"):
        bits.append(f"budget tier {trip['budget_tier']}")
    elif trip.get("budget") and trip.get("budget_min"):
        bits.append(f"budget Rs {int(trip['budget_min'])} to Rs {int(trip['budget'])} for the whole stay")
    elif trip.get("budget"):
        bits.append(f"maximum budget Rs {int(trip['budget'])} for the whole stay")
    elif trip.get("budget_min"):
        bits.append(f"budget from Rs {int(trip['budget_min'])} for the whole stay")
    if service == "hotels":
        on = filters_label(clean_filters(trip))
        if on:
            bits.append(f"filters: {on}")
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
    "A new city -> new destination with the same dates, guests and budget, and NO area. If only the check-in date changes, keep the same number of nights.\n"
    "- A question about the results on screen (which is cheapest, best rated, closest, 'the second one') is answered from the numbered list above in one or two sentences, with NO new <search> block. "
    "Never name a result that is not in the list. For photos, rooms or exact prices tell the visitor to tap View on that card.\n"
    "- A short yes (yes, ok, haan, hn, theek hai, chalo) answers YOUR last question or offer: do what you offered, right away. "
    "Never answer it with 'anything else for your trip?' or by starting over.\n"
    "- When the last search found NOTHING, or only the closest prices to the budget, say so in one short line and offer ONE next step yourself "
    "(the next budget up: low -> medium -> high, or the whole city instead of the area, or other dates). If the visitor agrees, search again at once with a complete <search> block.\n"
    "- Thanks, hello and other small talk (or an ok when you had offered nothing): answer in one short sentence, no <search> block, and do not repeat the old search.\n"
    "- NEVER say you are showing, searching or fetching options unless the same reply ends with the <search> block."
)


def memory_prompt(trip: Optional[Dict[str, Any]], results: Optional[Dict[str, Any]], selection: Optional[Dict[str, Any]]) -> str:
    """The part of the system prompt that carries the memory. Empty when there is nothing to remember."""
    parts: List[str] = []
    if trip:
        parts.append("Current trip (the last search that ran): " + describe_trip(trip) + ".")
    if selection:
        parts.append("Hotel in focus: " + describe_selection(selection) + ".")
    if results and not results["items"]:
        parts.append(f"The last {results['service']} search found NOTHING. The visitor was told: \"{results.get('note') or 'nothing found'}\"")
    elif results:
        parts.append(f"Results on the visitor's screen right now ({results['service']}), numbered as they see them:\n" + describe_results(results))
        if results.get("widened"):
            parts.append(f"Nothing matched the budget exactly, so these are the closest prices. The visitor was told: \"{results.get('note') or ''}\"")
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


_TIER_WORDS = (
    re.compile(r"\bsast[ao]a?\b|\bsasti\b|\bcheap\b|\blow\b|\bbudget\b|सस्ता", re.I),
    re.compile(r"\bmadhyam\b|\bmedium\b|\bmid\b|मध्यम", re.I),
    re.compile(r"\bpremium\b|\bhigh\b|\bluxury\b|प्रीमियम", re.I),
)
_PRICE = re.compile(r"₹|\brs\.?\s*\d|\brupe\w*|\d{3,}|\d\s*k\b|\d[\d,]*\s*(?:se|to|-|–)\s*\d|रुपय|\d{1,3},\d{3}", re.I)


def hide_tier_prices(reply: str, lang: str) -> str:
    """The price limits of sasta / madhyam / premium are the app's own business. A sentence that names two or more of the choices
    together with prices is replaced by the plain question (or dropped when it was not a question). Nothing else is touched."""
    if not reply or not asks_budget(reply):
        return reply
    m = re.search(r"\n?<search>", reply)
    head, tail = (reply[:m.start()], reply[m.start():]) if m else (reply, "")
    parts = re.split(r"(?<=[.!?।])\s+", head.strip())
    out, asked, changed = [], False, False
    for part in parts:
        if _PRICE.search(part) and sum(1 for w in _TIER_WORDS if w.search(part)) >= 2:
            changed = True
            if "?" in part and not asked:
                out.append(fixed("ask_budget", lang))
                asked = True
            continue
        out.append(part)
    if not changed:
        return reply
    if not asked:
        # the choices were only in the dropped sentence: the remaining budget question (or a new one) names them, without prices
        q = next((i for i, x in enumerate(out) if "?" in x and _Q_BUDGET.search(x)), None)
        if q is None:
            out.append(fixed("ask_budget", lang))
        else:
            out[q] = fixed("ask_budget", lang)
    return " ".join(x for x in out if x) + tail


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


_SHORT_YES = re.compile(
    r"^\s*(?:h+n+|ha+n*|haa+n*|han ji|haan ji|ji|ji haan|ji ha+n|yes|yeah|yep|yup|ok(?:ay)?|ok(?:ay)? ji|theek hai|thik hai|thik h|theek|thik|chalo|"
    r"kar ?do|kr ?do|dekh lo|dekho|dikhao|sure|please|haan dikhao|ha dikhao|हाँ|हां|हा|ठीक है|जी|जी हाँ|हाँ जी|दिखाओ)\s*[.!]*\s*$", re.I)


def is_short_yes(user_text: str) -> bool:
    """'hn', 'haan', 'ok', 'yes', 'theek hai': the visitor agrees to what was just offered, nothing more."""
    return bool(_SHORT_YES.match(str(user_text or "")))


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
            edited.pop("budget_min", None)
            changed = True
    m = _GUESTS.search(t)
    if m:
        n = int(next(g for g in m.groups() if g))
        if 1 <= n <= 10 and n != trip.get("travellers"):
            edited["travellers"] = n
            changed = True
    return edited if changed else None


# ------------------------------------------------------------------ what the visitor's last message really is
# A date typed where a place was asked for ("31/10/26" after "where should the bike pick you up?") is not an answer.
# Neither is a date that has passed, or a number of guests or nights the search cannot do. The model used to say
# "Got it" to all of these, so the app now looks at the message itself and answers before (or after) the model.
_MONTHS3 = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_D_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_D_DMON = re.compile(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?" + _MON + r"\b\.?(?:\s*,?\s*(\d{4}))?", re.I)
_D_MOND = re.compile(r"\b" + _MON + r"\b\.?\s*(\d{1,2})(?:st|nd|rd|th)?\b(?:\s*,?\s*(\d{4}))?", re.I)
_D_NUMY = re.compile(r"(?<!\d)(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4}|\d{2})(?!\d)")
_D_NUM = re.compile(r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})")           # day/month: a date only when it is the whole message
_TIME = re.compile(r"(?<!\d)\d{1,2}\s*:\s*\d{2}(?:\s*(?:am|pm))?\b|(?<!\d)\d{1,2}\s*(?:am|pm|baje|bje|o'?clock|hrs?|hours?)\b", re.I)
_WHENW = re.compile(
    r"\b(?:now|abhi|turant|asap|jaldi|today|aaj|aj|tonight|tomorrow|tmrw|kal|parso|day after tomorrow|morning|subah|subha|afternoon|dopahar|evening|shaam|sham|night|raat|noon)\b"
    r"|आज|कल|परसों|सुबह|शाम|रात|अभी", re.I)
_FILLER = re.compile(
    r"\b(?:on|from|to|till|until|upto|by|at|in|ko|se|tak|ke|ka|ki|liye|for|the|of|date|dates|tarikh|check-?in|check-?out|checkin|checkout|please|plz|pls|ji|hai|h|"
    r"chahiye|chahie|chaiye|chhaiye|only|bas|around|about|approx|ek|a)\b|तारीख|को|से|तक|के|लिए|है|चाहिए", re.I)
_UNITS = re.compile(r"\b(?:guests?|people|persons?|pax|adults?|log|logo|travell?ers?|members?|nights?|raat|raate|din|dino|days?)\b|लोग|रात|दिन", re.I)

_NUMW = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|ek|do|teen|char|chaar|paanch|panch|chhe|chhah|saat|aath|nau|das)"
_CUE_NIGHTS = re.compile(
    r"\b" + _NUMW + r"[\s-]*(?:nights?|nites?|raat|raate|raaton|rat|din|dino|days?)\b|\bovernight\b|\b(?:a|single|one) night\b|\bweekend\b|\bweek\b|\bhafte?\b|\bhafta\b|\bcheck[- ]?out\b|\bcheckout\b"
    r"|[0-9०-९]+\s*(?:रात|दिन)|(?:एक|दो|तीन|चार|पाँच|पांच|छह|सात|आठ|नौ|दस)\s*(?:रात|दिन)|हफ्ते|सप्ताह|चेक-?आउट", re.I)
_RANGE = re.compile(
    r"(?<!\d)\d{1,2}(?:st|nd|rd|th)?\s*(?:-|–|to|se|till|until|tak)\s*\d{1,2}(?:st|nd|rd|th)?\s*" + _MON + r"\b"
    r"|\b" + _MON + r"\b\.?\s*\d{1,2}(?:st|nd|rd|th)?\s*(?:-|–|to|se|till|until|tak)\s*\d{1,2}(?!\d)", re.I)

# what the assistant's last question was about
_Q_PLACE = re.compile(
    r"\bpick(?:ed)?[- ]?(?:you |me |us )?up\b|\bpickup\b|\bdrop(?:ped|[- ]?off)?\b|\bwhere\b|\bwhich (?:city|place|town|area|location)\b|\bwhat(?:'s| is)? (?:the )?(?:city|place|location|destination)\b"
    r"|\bkahan\b|\bkahaan\b|\bkaha\b|\bkidhar\b|\bkis (?:shehar|sheher|jagah|city)\b|\bkaun ?s[ei] (?:shehar|sheher|jagah|city)\b|\bshehar\b|\bsheher\b|\bjagah\b|\bdestination\b"
    r"|कहाँ|कहां|किस (?:शहर|जगह)|कौन ?से? (?:शहर|जगह)|शहर|जगह", re.I)
_Q_WHEN_ANY = re.compile(
    r"\b(?:date|dates|day|days|night|nights|when|kab|din|raat|tarikh|tareekh|check[- ]?in|check[- ]?out|checkin|checkout)\b|तारीख|कब|रात|दिन", re.I)
_Q_NIGHTS = re.compile(
    r"\bhow many (?:nights?|days?)\b|\bhow long\b|\bnumber of (?:nights?|days?)\b|\bkitni (?:raat|rat|raate|raaton|din)\b|\bkitne (?:din|dino|raat)\b|\bcheck[- ]?out\b|\bkab tak\b|\b(?:till|until) when\b"
    r"|कितनी रात|कितने दिन|चेक-?आउट|कब तक", re.I)
_SENT_SPLIT = re.compile(r"(?<=[.!?।？])\s+")


def _mk(y: int, m: int, d: int) -> Optional[date]:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _resolve(day: int, month: int, year: Optional[str], today: date) -> Optional[date]:
    """A written date. Without a year it is the next one that is not long gone: a day that passed a few days ago stays in the past."""
    if year:
        y = int(year)
        return _mk(y + 2000 if y < 100 else y, month, day)
    this = _mk(today.year, month, day)
    if this is None:
        return None
    if this < today and (today - this).days > 45:
        return _mk(today.year + 1, month, day) or this
    return this


def _find_dates(t: str, today: date) -> Tuple[List[date], str]:
    """Every date written in the (lower-case) text, day first as in India, and the text with those dates cut out."""
    found: List[date] = []
    work = t

    def take(pattern: Any, build: Any) -> None:
        nonlocal work

        def sub(m: Any) -> str:
            got = build(m)
            if got is None:
                return m.group(0)
            found.append(got)
            return " "
        work = pattern.sub(sub, work)

    take(_D_ISO, lambda m: _mk(int(m[1]), int(m[2]), int(m[3])))
    take(_D_DMON, lambda m: _resolve(int(m[1]), _MONTHS3[m[2].lower()[:3]], m[3], today))
    take(_D_MOND, lambda m: _resolve(int(m[2]), _MONTHS3[m[1].lower()[:3]], m[3], today))
    take(_D_NUMY, lambda m: _resolve(int(m[1]), int(m[2]), m[3], today))
    return found, work


def classify(message: str, today: date) -> Dict[str, Any]:
    """What a short message is. kind: "date", "past_date" (a date before today), "time", "number" or "text" (anything else)."""
    out: Dict[str, Any] = {"kind": "text", "date": None, "number": None}
    t = " ".join(str(message or "").lower().split())
    if not t or len(t) > 60:
        return out
    m = _D_NUM.fullmatch(t)
    if m and 1 <= int(m[2]) <= 12:
        d = _resolve(int(m[1]), int(m[2]), None, today)
        if d:
            return {"kind": "past_date" if d < today else "date", "date": d, "number": None}
    dates, rest = _find_dates(t, today)
    had_time = bool(_TIME.search(rest))
    rest = _TIME.sub(" ", rest)
    had_when = bool(_WHENW.search(rest))
    rest = _FILLER.sub(" ", _WHENW.sub(" ", rest))
    rest = re.sub(r"[\s,.:;!?\-–—/()'\"]+", " ", rest).strip()
    if not rest:
        if dates:
            return {"kind": "past_date" if all(d < today for d in dates) else "date", "date": dates[0], "number": None}
        if had_time:
            return {**out, "kind": "time"}
        if had_when:
            return {**out, "kind": "date"}
        return out
    alone = _UNITS.sub(" ", rest).strip()
    if not dates and re.fullmatch(r"\d{1,3}", alone):
        return {**out, "kind": "number", "number": int(alone)}
    return out


def not_a_place(name: str, today: date) -> bool:
    """True for a "place" that is really a date, a time or a number (or has no letters at all)."""
    s = str(name or "")
    return not any(ch.isalpha() for ch in s) or classify(s, today)["kind"] != "text"


def questions(model_text: str) -> List[str]:
    """The questions in one of the assistant's replies, in order (the <search> block and a cut-off tag are ignored)."""
    body = re.sub(r"<search>.*?</search>", " ", str(model_text or ""), flags=re.S | re.I)
    body = re.sub(r"<[^>]*$", "", body)
    parts = [p.strip() for p in _SENT_SPLIT.split(" ".join(body.split())) if p.strip()]
    return [p[:220] for p in parts if p.endswith("?") or p.endswith("？")]


def last_question(model_text: str) -> str:
    qs = questions(model_text)
    return qs[-1] if qs else ""


def pre_check(turns: List[Tuple[str, str]], user_text: str, today: date, lang: str) -> Optional[str]:
    """A ready reply when the visitor's message plainly does not fit the question the assistant just asked
    (a date or a number given as a place, a date that has passed, 15 guests, 90 nights). None: let the model answer."""
    if not turns or turns[-1][0] != "model":
        return None
    ask = last_question(turns[-1][1])
    if not ask:
        return None
    c = classify(user_text, today)
    kind, n = c["kind"], c["number"]
    if kind == "text":
        return None
    about_place = bool(_Q_PLACE.search(ask)) and not _Q_WHEN_ANY.search(ask) and not _Q_GUESTS.search(ask)
    if about_place and kind in ("date", "past_date", "time"):
        return f"{fixed('not_place_date', lang)} {ask}"
    if about_place and kind == "number":
        return f"{fixed('not_place', lang)} {ask}"
    if kind == "past_date" and _Q_WHEN_ANY.search(ask):
        return f"{fixed('date_passed', lang)} {ask}"
    if kind == "number" and n is not None:
        if _Q_GUESTS.search(ask) and not 1 <= n <= 10:
            return fixed("bad_travellers", lang)
        if _Q_NIGHTS.search(ask) and not 1 <= n <= 30:
            return fixed("bad_nights", lang)
    return None


def input_note(user_text: str, today: date) -> str:
    """Facts about the latest message for the model: it names a date that has already passed (and no date that has not)."""
    low = " ".join(str(user_text or "").lower().split())[:300]
    dates, _ = _find_dates(low, today)
    if not dates or any(d >= today for d in dates):
        return ""
    names = ", ".join(_nice(d.isoformat()) for d in sorted(set(dates)))
    return ("\n\nINPUT CHECK (done by the app, trust it): the visitor's latest message has the date " + names + ", which is already in the past "
            "(today is " + _nice(today.isoformat()) + "). Do not search with it: say in one short line that it has passed and ask for another date.")


def nights_known(turns: List[Tuple[str, str]], user_text: str, today: date) -> bool:
    """Has the length of the stay been settled in this conversation: said by the visitor, or asked for (and so answered)?"""
    if any(role == "model" and any(_Q_NIGHTS.search(q) for q in questions(body)) for role, body in turns):
        return True
    for body in [b for r, b in turns if r == "user"] + [str(user_text or "")]:
        low = " ".join(body.lower().split())[:400]
        if _CUE_NIGHTS.search(low) or _RANGE.search(low) or len(_find_dates(low, today)[0]) >= 2:
            return True
    return False


# ------------------------------------------------------------------ words for the few fixed replies we write ourselves
FIXED = {
    "updating": {
        "en": "Sure, updating your search now.",
        "hinglish": "Theek hai, search abhi update ho rahi hai.",
        "hi": "ठीक है, खोज अभी अपडेट हो रही है।",
    },
    "no_search": {
        "en": "Tell me what to change: dates, guests, budget or city.",
        "hinglish": "Bataiye kya badalna hai: dates, log, budget ya shehar.",
        "hi": "बताइए क्या बदलना है: तारीख, लोग, बजट या शहर।",
    },
    "ask_budget": {
        "en": "What budget would you like: cheap, medium or premium?",
        "hinglish": "Budget kaisa chahiye: sasta, madhyam ya premium?",
        "hi": "बजट कैसा चाहिए: सस्ता, मध्यम या प्रीमियम?",
    },
    "widened_amount": {
        "en": "No hotel here fits ₹{amount} a night, so these are the closest prices. Shall I look a little higher?",
        "hinglish": "₹{amount} per night me yahan koi hotel nahi mila, isliye iske sabse kareeb wale hotels ye rahe. Thoda upar ke budget me dekhun?",
        "hi": "₹{amount} प्रति रात में यहाँ कोई होटल नहीं मिला, इसलिए उसके सबसे करीब वाले होटल ये रहे। थोड़ा ऊपर के बजट में देखूँ?",
    },
    "widened_tier": {
        "en": "No hotel here fits that budget exactly, so these are the closest prices. Shall I look a little higher?",
        "hinglish": "Is budget me yahan koi hotel nahi mila, isliye iske sabse kareeb wale hotels ye rahe. Thoda upar ke budget me dekhun?",
        "hi": "इस बजट में यहाँ कोई होटल नहीं मिला, इसलिए उसके सबसे करीब वाले होटल ये रहे। थोड़ा ऊपर के बजट में देखूँ?",
    },
    "widened_area": {
        "en": "No hotel near {area} fits that budget, so these are the nearby hotels with the closest prices. Shall I look a little higher?",
        "hinglish": "{area} ke paas is budget me koi hotel nahi mila, isliye wahan ke sabse kam daam wale hotels ye rahe. Thoda upar ke budget me dekhun?",
        "hi": "{area} के पास इस बजट में कोई होटल नहीं मिला, इसलिए वहाँ के सबसे कम दाम वाले होटल ये रहे। थोड़ा ऊपर के बजट में देखूँ?",
    },
    "widened_tier_down": {
        "en": "No hotel here fits that budget exactly, so these are the closest prices. Shall I look at medium instead?",
        "hinglish": "Is budget me yahan koi hotel nahi mila, isliye iske sabse kareeb wale hotels ye rahe. Madhyam budget me dekhun?",
        "hi": "इस बजट में यहाँ कोई होटल नहीं मिला, इसलिए उसके सबसे करीब वाले होटल ये रहे। मध्यम बजट में देखूँ?",
    },
    "budget_up": {
        "en": "Okay, looking a little higher.",
        "hinglish": "Theek hai, thoda upar ke budget me dekhte hain.",
        "hi": "ठीक है, थोड़ा ऊपर के बजट में देखते हैं।",
    },
    "budget_down": {
        "en": "Okay, looking at medium prices.",
        "hinglish": "Theek hai, madhyam budget me dekhte hain.",
        "hi": "ठीक है, मध्यम बजट में देखते हैं।",
    },
    "search_again": {
        "en": "Okay, trying again.",
        "hinglish": "Theek hai, dobara dekhte hain.",
        "hi": "ठीक है, फिर से देखते हैं।",
    },
    "filters_on": {
        "en": "Done, showing hotels with: {what}.",
        "hinglish": "Theek hai, ye filter laga diye: {what}.",
        "hi": "ठीक है, ये फ़िल्टर लगा दिए: {what}।",
    },
    "filters_off": {
        "en": "Filters removed, showing all hotels again.",
        "hinglish": "Filter hata diye, ab saare hotels dikh rahe hain.",
        "hi": "फ़िल्टर हटा दिए, अब सारे होटल दिख रहे हैं।",
    },
    "filters_none": {
        "en": "No hotel here matches {what}, so these are without that filter.",
        "hinglish": "{what} wala koi hotel yahan nahi mila, isliye bina is filter ke dikha rahe hain.",
        "hi": "{what} वाला कोई होटल यहाँ नहीं मिला, इसलिए बिना इस फ़िल्टर के दिखा रहे हैं।",
    },
    "hotels_unavailable": {
        "en": "Live hotels are not available right now. Please try again shortly.",
        "hinglish": "Abhi live hotels nahi mil paa rahe. Thodi der baad dobara try karein.",
        "hi": "अभी लाइव होटल नहीं मिल पा रहे। थोड़ी देर बाद फिर कोशिश करें।",
    },
    "ask_city": {
        "en": "Which city should I look in? Please tell me the city name again.",
        "hinglish": "Kaunse shehar ke liye dekhna hai? Shehar ka naam ek baar dobara bata dijiye.",
        "hi": "किस शहर के लिए देखना है? शहर का नाम एक बार फिर बता दीजिए।",
    },
    "city_not_found": {
        "en": "I could not find that city. Please check the spelling and tell me again.",
        "hinglish": "Mujhe wo shehar nahi mila, spelling ek baar check karke dobara bata dijiye.",
        "hi": "मुझे वह शहर नहीं मिला, कृपया स्पेलिंग जाँचकर दोबारा बताइए।",
    },
    "ask_places": {
        "en": "Where from and where to? Please tell me the pickup place and the drop place.",
        "hinglish": "Kahan se kahan jana hai? Pickup aur drop ki jagah bata dijiye.",
        "hi": "कहाँ से कहाँ जाना है? पिकअप और ड्रॉप की जगह बता दीजिए।",
    },
    "same_place": {
        "en": "Pickup and drop are the same place. Where would you like to go?",
        "hinglish": "Pickup aur drop ek hi jagah hai. Aapko kahan jana hai?",
        "hi": "पिकअप और ड्रॉप एक ही जगह है। आपको कहाँ जाना है?",
    },
    "bad_place": {
        "en": "That does not look like a place name. Please tell me the pickup and drop places, like Jaipur Airport to Hawa Mahal.",
        "hinglish": "Yeh jagah ka naam nahi lag raha. Pickup aur drop ki jagah bataiye, jaise Jaipur Airport se Hawa Mahal.",
        "hi": "यह जगह का नाम नहीं लग रहा। पिकअप और ड्रॉप की जगह बताइए, जैसे जयपुर एयरपोर्ट से हवा महल।",
    },
    "not_place_date": {
        "en": "That looks like a date or time, not a place.",
        "hinglish": "Yeh date ya time lag raha hai, jagah ka naam nahi.",
        "hi": "यह तारीख या समय लग रहा है, जगह का नाम नहीं।",
    },
    "not_place": {
        "en": "That does not look like a place name.",
        "hinglish": "Yeh jagah ka naam nahi lag raha.",
        "hi": "यह जगह का नाम नहीं लग रहा।",
    },
    "date_passed": {
        "en": "That date has already passed.",
        "hinglish": "Woh date toh nikal chuki hai.",
        "hi": "वह तारीख तो निकल चुकी है।",
    },
    "past_date": {
        "en": "That date has already passed. Which date do you want?",
        "hinglish": "Woh date toh nikal chuki hai. Kaunsi date chahiye?",
        "hi": "वह तारीख तो निकल चुकी है। कौन सी तारीख चाहिए?",
    },
    "ask_date": {
        "en": "Which date should I search for?",
        "hinglish": "Kaunsi date ke liye dekhna hai?",
        "hi": "किस तारीख के लिए देखना है?",
    },
    "ask_nights": {
        "en": "How many nights will you stay? You can also tell me the check-out date.",
        "hinglish": "Kitni raat rukna hai? Check-out date bhi bata sakte hain.",
        "hi": "कितनी रात रुकना है? चेक-आउट की तारीख भी बता सकते हैं।",
    },
    "bad_nights": {
        "en": "I can search stays of 1 to 30 nights. How many nights?",
        "hinglish": "Ek baar mein 1 se 30 raat tak ki stay dekhi ja sakti hai. Kitni raat?",
        "hi": "एक बार में 1 से 30 रात तक की स्टे देखी जा सकती है। कितनी रात?",
    },
    "bad_travellers": {
        "en": "I can search for 1 to 10 guests at a time. How many guests?",
        "hinglish": "Ek baar mein 1 se 10 log tak ki search ho sakti hai. Kitne log honge?",
        "hi": "एक बार में 1 से 10 लोगों तक की खोज हो सकती है। कितने लोग होंगे?",
    },
    "ask_child_ages": {
        "en": "How old is each child? Please tell me the age of every child travelling.",
        "hinglish": "Har bachche ki umar kitni hai? Jo bachche saath hain unki umar bata dijiye.",
        "hi": "हर बच्चे की उम्र कितनी है? साथ चल रहे हर बच्चे की उम्र बता दीजिए।",
    },
    "bad_rooms": {
        "en": "Every room needs at least one adult, and I can search up to 5 rooms. How many rooms and adults?",
        "hinglish": "Har room me kam se kam ek adult chahiye, aur 5 room tak ki search ho sakti hai. Kitne room aur kitne adult?",
        "hi": "हर कमरे में कम से कम एक वयस्क चाहिए, और 5 कमरों तक की खोज हो सकती है। कितने कमरे और कितने वयस्क?",
    },
    "past_time": {
        "en": "That pickup time has already passed. What time should I book the ride for?",
        "hinglish": "Woh time toh nikal chuka hai. Ride kis time ki chahiye?",
        "hi": "वह समय तो निकल चुका है। राइड किस समय की चाहिए?",
    },
    "far_time": {
        "en": "I can schedule a ride up to 30 days ahead. Which day and time?",
        "hinglish": "Ride 30 din aage tak ki schedule ho sakti hai. Kaunsa din aur time?",
        "hi": "राइड 30 दिन आगे तक की शेड्यूल हो सकती है। कौन सा दिन और समय?",
    },
    "ask_grocery": {
        "en": "What would you like to order? For example, 2 milk, bread and potatoes.",
        "hinglish": "Kya mangwana hai? Jaise 2 doodh, bread aur aloo.",
        "hi": "क्या मँगवाना है? जैसे 2 दूध, ब्रेड और आलू।",
    },
    "area_missing": {
        "en": "(I could not find the exact spot for {area}, so I am showing hotels across {dest}.)",
        "hinglish": "({area} ka exact location nahi mila, isliye poore {dest} ke hotels dikhaye ja rahe hain.)",
        "hi": "({area} की सटीक जगह नहीं मिली, इसलिए पूरे {dest} के होटल दिखाए जा रहे हैं।)",
    },
}


def fixed(key: str, lang: str) -> str:
    table = FIXED[key]
    return table.get(lang) or table["en"]
