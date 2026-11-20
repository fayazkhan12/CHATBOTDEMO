"""The step-by-step hotel chatbot API (/api/v1/chatbot), in the shape the Postman collection "DestinoWay Chatbot API" tests.

    GET  /tools                 the tools the bot calls
    POST /start                 a new chat
    POST /message               {sessionId, message} what the user typed, or {sessionId, value} the button they tapped
    GET  /session/{sessionId}   the saved state of a chat

Every answer: {"success", "message", "data": {"sessionId", "step", "reply": {"type", "text", "options", ...}, "collected"}}.
Steps: DESTINATION -> DESTINATION_SELECT -> CHECK_IN -> CHECK_OUT -> ROOMS -> ADULTS -> CHILDREN -> CHILD_AGES -> BUDGET
       -> CONFIRM -> RESULTS. Anything the user already said (one line: "jaipur me 15/12 se 3 raat, 2 adults, budget 15000")
       is not asked again.

Hotels are LIVE (the same company API search as the website chat). Budgets are for the WHOLE stay unless the user says
"per night" ("3000 per night" x 3 nights = 9000). Sessions live in memory (a restart starts new chats; an unknown
sessionId simply gets a new chat)."""
import logging
import re
import time
import uuid
from datetime import date, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("destinoway.step_bot")
router = APIRouter(prefix="/api/v1/chatbot")

STEPS = ["DESTINATION", "DESTINATION_SELECT", "CHECK_IN", "CHECK_OUT", "ROOMS", "ADULTS", "CHILDREN", "CHILD_AGES", "BUDGET",
         "CONFIRM", "RESULTS"]
MAX_ROOMS, MAX_ADULTS, MAX_CHILDREN, MAX_NIGHTS = 5, 10, 6, 30
SESSION_TTL = 3 * 3600
SESSIONS: Dict[str, Dict[str, Any]] = {}
PAGE_SIZE = 12

# set by server.setup(): the live company API helpers the website chat uses too
D: Dict[str, Any] = {}


def setup(**deps: Any) -> None:
    D.update(deps)


# ============================================================================ words
HINDI = {
    "जयपुर": "jaipur", "दिल्ली": "delhi", "मुंबई": "mumbai", "गोवा": "goa", "उदयपुर": "udaipur", "जोधपुर": "jodhpur",
    "आगरा": "agra", "वाराणसी": "varanasi", "बनारस": "varanasi", "ऋषिकेश": "rishikesh", "मनाली": "manali", "शिमला": "shimla",
    "बेंगलुरु": "bengaluru", "बैंगलोर": "bangalore", "हैदराबाद": "hyderabad", "चेन्नई": "chennai", "कोलकाता": "kolkata",
    "पुणे": "pune", "अहमदाबाद": "ahmedabad", "जैसलमेर": "jaisalmer", "अजमेर": "ajmer", "पुष्कर": "pushkar", "लखनऊ": "lucknow",
    "अमृतसर": "amritsar", "नैनीताल": "nainital", "कोटा": "kota", "बीकानेर": "bikaner", "इंदौर": "indore", "भोपाल": "bhopal",
    "सूरत": "surat", "कोच्चि": "kochi", "मैसूर": "mysore", "ऊटी": "ooty", "दार्जिलिंग": "darjeeling", "चंडीगढ़": "chandigarh",
    "हरिद्वार": "haridwar", "मथुरा": "mathura", "वृंदावन": "vrindavan", "पटना": "patna", "गुवाहाटी": "guwahati",
    "में": "me", "मे": "me", "होटल": "hotel", "चाहिए": "chahiye", "से": "se", "रात": "raat", "रातें": "raat", "लोग": "log",
    "कल": "kal", "आज": "aaj", "परसों": "parso", "दिन": "din", "बच्चे": "bachche", "बच्चा": "bachcha", "साल": "saal",
    "कमरा": "kamra", "कमरे": "kamre", "तक": "tak", "कम": "kam", "ज़्यादा": "zyada", "ज्यादा": "zyada", "नमस्ते": "namaste",
    "नमस्कार": "namaskar", "हाँ": "haan", "हां": "haan", "नहीं": "nahi", "और": "aur", "के": "ke", "पास": "paas", "का": "ka",
    "मुझे": "mujhe", "वयस्क": "adults", "बड़े": "adults",
}
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
             "ek": 1, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "zero": 0, "shunya": 0}
STOP = set("""mujhe mujhko muje mere mera meri hum hame hamein me mein main mai mei hotel hotels hotal chahiye chaiye chahie chahiyee
stay stays room rooms book booking karna karni karo kar dikhao dikha dikhaao dikhado batao bata ka ki ke ko se tak aur and for in at on
near paas pass the a an i want need please plz pls hai h hain hay kya ek total budget adult adults kid kids child children no nahi nhi
log logo people person persons guest guests raat raatein night nights din day days bachche bachcha bachchon bachhe saal sal year years
yrs per under kam zyada jyada wala wali wale waala sasta sasti saste mehenga premium madhyam rupees rupay rs inr k upar lagbhag around
about approx star stars free cancellation from to till check checkin checkout out aaj kal parso today tomorrow trip ghumne jana jaana
family with of hi hello hey namaste koi bhi any some show find search looking dhundo chahta chahti hu hoon ho please kahin jagah
kamra kamre se lekar ke liye liye tak upto max min minimum maximum also bhi ya or vala vale vali hotle""".split())
GREET = re.compile(r"^\s*(hi+|hello|helo|hey|hii+|namaste|namaskar|good\s*(morning|evening|afternoon)|hlo|yo)\s*[!.]*\s*$", re.I)
HELP = re.compile(r"^\s*(help|madad|kaise|how\s*(does|do)\s*(this|it)\s*work|\?)\s*[!?.]*\s*$", re.I)
RESET = re.compile(r"^\s*(new\s*search|naya\s*search|nayi\s*search|start\s*over|restart|reset|cancel|band\s*karo|shuru\s*se)\s*[!.]*\s*$", re.I)
BACK = re.compile(r"^\s*(back|go\s*back|peeche|piche|pichla|previous)\s*[!.]*\s*$", re.I)
YES = re.compile(r"^\s*(yes|y|ok|okay|okk|haan|han|ha|hn|haa|ji|sure|search|go|done|confirm|theek\s*hai|thik\s*hai|chalo|kar\s*do|dikhao)\s*[!.]*\s*$", re.I)
SKIP = re.compile(r"^\s*(skip|no\s*budget|koi\s*bhi|any|kuch\s*bhi|budget\s*nahi|nahi\s*pata|no\s*limit|chhodo)\s*[!.]*\s*$", re.I)
MORE = re.compile(r"^\s*(more|show\s*more|aur|aur\s*dikhao|next|agla|aage)\s*[!.]*\s*$", re.I)
NONE_KIDS = re.compile(r"\b(no\s*(kids?|child(ren)?|bachch?[ae])|without\s*(kids?|child(ren)?)|(bachch?[ae]|kids?)\s*(nahi|nhi|no)|koi\s*bachch?a\s*nahi|zero\s*kids?)\b", re.I)


def _plain(text: str) -> str:
    """Lower case, Hindi words in Latin letters, no HTML, one space."""
    words = []
    for w in str(text or "").split():
        core = w.strip(".,!?;:।")
        words.append(HINDI.get(core, w))
    t = " ".join(words).lower()
    t = re.sub(r"<[^>]*>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _safe(text: Any, limit: int = 60) -> str:
    """Text that may be shown back: no tags or brackets."""
    return re.sub(r"[<>{}\[\]\"`]", "", str(text or ""))[:limit].strip()


def _num(word: str) -> Optional[int]:
    w = word.strip().lower()
    if re.fullmatch(r"-?\d+", w):
        return int(w)
    return NUM_WORDS.get(w)


def _money(v: float) -> str:
    return f"₹{v:,.0f}"


# ============================================================================ dates
def _today() -> date:
    return D["today"]() if "today" in D else date.today()


def _dates_in(t: str) -> Tuple[List[date], str]:
    """Dates in the text (relative words first: aaj / kal / parso), and the text without them."""
    today = _today()
    found: List[date] = []
    work = t
    for rx, days in ((r"\b(day\s*after\s*tomorrow|parso|parson)\b", 2), (r"\b(aaj|today|tonight)\b", 0), (r"\b(kal|tomorrow|tmrw)\b", 1)):
        if re.search(rx, work):
            found.append(today + timedelta(days=days))
            work = re.sub(rx, " ", work)
    more, work = D["find_dates"](work, today)
    for d in more:
        if d.year == today.year and d < today and (today - d).days > 60 and not re.search(r"\b20\d\d\b", t):
            d = d.replace(year=today.year + 1)        # "25 jan" in November: next January
        found.append(d)
    return found, work


NIGHTS = re.compile(r"(\d+|one|two|three|four|five|six|seven|ek|teen|char|chaar|paanch)\s*-?\s*(nights?|raat(?:ein|e|en)?|din|days?)\b", re.I)


def _nights_in(t: str) -> Tuple[Optional[int], str]:
    m = NIGHTS.search(t)
    if not m:
        return None, t
    return _num(m.group(1)), t[:m.start()] + " " + t[m.end():]


# ============================================================================ guests
ROOMS_RX = re.compile(r"(\d+|one|two|three|four|five|ek|teen|char)\s*(rooms?|kamr[ae]|kamra)\b", re.I)
ADULTS_RX = re.compile(r"(\d+|one|two|three|four|five|six|ek|teen|char|paanch)\s*(adults?|log|logo|logon|people|persons?|pax|guests?|bade|bado|vyakti)\b", re.I)
KIDS_RX = re.compile(r"(\d+|one|two|three|four|ek|teen)\s*(kids?|child(?:ren)?|bachch?[ae]|bachchon|bachhe|baby|babies)\b", re.I)
AGES_RX = re.compile(r"(\d{1,2})\s*(saal|sal|years?|yrs?|yr|y/o)\b", re.I)


def _guests_in(t: str) -> Tuple[Dict[str, Any], str]:
    out: Dict[str, Any] = {}
    for key, rx in (("rooms", ROOMS_RX), ("adults", ADULTS_RX), ("children", KIDS_RX)):
        m = rx.search(t)
        if m and _num(m.group(1)) is not None:
            out[key] = _num(m.group(1))
            t = t[:m.start()] + " " + t[m.end():]
    if NONE_KIDS.search(t):
        out["children"] = 0
        t = NONE_KIDS.sub(" ", t)
    ages = [int(x[0]) for x in AGES_RX.findall(t)]
    if ages:
        out["childAges"] = ages
        t = AGES_RX.sub(" ", t)
    return out, t


# ============================================================================ budget
AMOUNT = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)\s*(k|thousand|hazaar|hazar|l|lakh|lac|lacs)?(?![a-z\d])", re.I)
CUE_PER_NIGHT = re.compile(r"per\s*night|/\s*night|a\s*night|per\s*raat|ek\s*raat\s*ka|raat\s*ka|nightly|प्रति\s*रात", re.I)
CUE_MIN = re.compile(r"se\s*(?:upar|uper|zyada|jyada|jaada|adhik)|\babove\b|more\s*than|\bover\b|\bminimum\b|\bmin\b|kam\s*se\s*kam|at\s*least|\+", re.I)
CUE_MAX = re.compile(r"se\s*kam|\bunder\b|\bbelow\b|\btak\b|up\s*to|\bupto\b|\bmax(?:imum)?\b|\bwithin\b|less\s*than|\bbudget\b|\bandar\b", re.I)
CUE_AROUND = re.compile(r"lagbhag|\blg\s*bh?a?g\b|\baround\b|\babout\b|\bapprox|\bka\s*hotel\b|\bwala\b|\bwale\b|\bwali\b|aas\s*-?\s*paas|\bkareeb\b|\bkarib\b", re.I)
RANGE = re.compile(r"(\d[\d,.]*\s*(?:k(?![a-z]))?)\s*(?:-|–|to|se)\s*(\d[\d,.]*\s*(?:k(?![a-z]))?)(?!\s*(?:raat|night|din|day|log|adult|room|star))", re.I)
TIERS = {"sasta": ("low", (0, 1500)), "budget hotel": ("low", (0, 1500)), "cheap": ("low", (0, 1500)),
         "madhyam": ("medium", (1500, 3000)), "medium": ("medium", (1500, 3000)), "mid": ("medium", (1500, 3000)),
         "premium": ("high", (3000, None)), "luxury": ("high", (3000, None)), "mehenga": ("high", (3000, None))}


def _amount(s: str, unit: Optional[str] = None) -> Optional[float]:
    s = s.replace(",", "").strip().lower()
    m = re.match(r"(\d+(?:\.\d+)?)\s*(k|thousand|hazaar|hazar|l|lakh|lac|lacs)?(?![a-z])", s)
    if not m:
        return None
    v = float(m.group(1))
    u = (unit or m.group(2) or "").lower()
    if u in ("k", "thousand", "hazaar", "hazar"):
        v *= 1000
    elif u in ("l", "lakh", "lac", "lacs"):
        v *= 100000
    return v


def parse_budget(t: str, nights: int, need_cue: bool = False) -> Optional[Dict[str, Any]]:
    """A budget in the text: {"min", "max", "per_night"} for the WHOLE stay (per-night amounts x nights), or None.
    need_cue: only when the text plainly talks about money (a one-line request or a message on the results)."""
    nights = max(1, nights or 1)
    per = bool(CUE_PER_NIGHT.search(t))
    mult = nights if per else 1
    r = RANGE.search(t)
    if r:
        a, b = _amount(r.group(1)), _amount(r.group(2))
        if a and b and 100 <= min(a, b):
            lo, hi = sorted((a, b))
            return {"min": lo * mult, "max": hi * mult, "per_night": per}
    amounts = [(m, _amount(m.group(1), m.group(2))) for m in AMOUNT.finditer(t)]
    amounts = [(m, v) for m, v in amounts if v and v >= 100]
    tier = next((v for k, v in TIERS.items() if re.search(rf"\b{k}\b", t)), None)
    if not amounts:
        if tier and not need_cue:
            lo, hi = tier[1]
            return {"min": (lo * nights) or None, "max": hi * nights if hi else None, "per_night": True, "tier": tier[0]}
        return None
    m, v = amounts[-1]
    has_money_word = bool(CUE_MAX.search(t) or CUE_MIN.search(t) or CUE_AROUND.search(t) or per or m.group(2)
                          or re.search(r"₹|\brs\.?|\brupe|\binr\b", t))
    if need_cue and not has_money_word:
        return None
    v *= mult
    if CUE_MIN.search(t):
        return {"min": v, "max": None, "per_night": per}
    if CUE_MAX.search(t):
        return {"min": None, "max": v, "per_night": per}
    if CUE_AROUND.search(t):
        return {"min": v, "max": round(v * 1.25), "per_night": per}
    return {"min": None, "max": v, "per_night": per}


# ============================================================================ sessions
def _blank() -> Dict[str, Any]:
    return {"destination": None, "area": None, "pincode": None, "point": None, "checkIn": None, "checkOut": None, "nights": None,
            "rooms": None, "adults": None, "children": None, "childAges": [], "minPrice": None, "maxPrice": None,
            "budgetPerNight": None, "_pn": None, "budgetSkipped": False, "filters": {}, "currency": "INR"}


def _new(currency: str = "INR") -> Dict[str, Any]:
    now = time.time()
    if len(SESSIONS) > 5000:
        for k in [k for k, v in SESSIONS.items() if now - v["updated"] > SESSION_TTL]:
            SESSIONS.pop(k, None)
    s = {"id": str(uuid.uuid4()), "step": "DESTINATION", "c": _blank(), "options": [], "results": None, "page": 1,
         "updated": now, "reply": None}
    s["c"]["currency"] = (currency or "INR")[:3].upper()
    SESSIONS[s["id"]] = s
    return s


def _get(sid: Any) -> Optional[Dict[str, Any]]:
    s = SESSIONS.get(str(sid or ""))
    if s and time.time() - s["updated"] > SESSION_TTL:
        SESSIONS.pop(s["id"], None)
        return None
    return s


def _public(c: Dict[str, Any]) -> Dict[str, Any]:
    d = c.get("destination") or {}
    return {
        "destination": d.get("label"), "destinationId": d.get("locationId"), "area": c.get("area"), "pincode": c.get("pincode"),
        "checkIn": c.get("checkIn"), "checkOut": c.get("checkOut"), "nights": c.get("nights"),
        "rooms": c.get("rooms"), "adults": c.get("adults"), "children": c.get("children"), "childAges": list(c.get("childAges") or []),
        "minPrice": c.get("minPrice"), "maxPrice": c.get("maxPrice"), "budgetPerNight": c.get("budgetPerNight"),
        "filters": dict(c.get("filters") or {}), "currency": c.get("currency"),
    }


def _answer(s: Dict[str, Any], reply: Dict[str, Any], message: str = "Chat reply generated successfully") -> Dict[str, Any]:
    reply.setdefault("options", [])
    reply["text"] = str(reply.get("text") or "")
    s["reply"], s["updated"] = reply, time.time()
    return {"success": True, "message": message, "data": {"sessionId": s["id"], "step": s["step"], "reply": reply, "collected": _public(s["c"])}}


def _text(t: str, options: Optional[List[Dict[str, Any]]] = None, **extra: Any) -> Dict[str, Any]:
    return {"type": "text", "text": t, "options": options or [], **extra}


# ============================================================================ the questions
def _missing(c: Dict[str, Any]) -> str:
    if not c.get("destination"):
        return "DESTINATION"
    if not c.get("checkIn"):
        return "CHECK_IN"
    if not c.get("checkOut"):
        return "CHECK_OUT"
    if not c.get("rooms"):
        return "ROOMS"
    if not c.get("adults"):
        return "ADULTS"
    if c.get("children") is None:
        return "CHILDREN"
    if (c.get("children") or 0) > len(c.get("childAges") or []):
        return "CHILD_AGES"
    if c.get("maxPrice") is None and c.get("minPrice") is None and not c.get("budgetSkipped"):
        return "BUDGET"
    return "CONFIRM"


def _question(s: Dict[str, Any], lead: str = "") -> Dict[str, Any]:
    c, step = s["c"], s["step"]
    lead = (lead + " ") if lead else ""
    city = (c.get("destination") or {}).get("city") or "your city"
    if step == "DESTINATION":
        return _text(lead + "Where would you like to stay? Type a city, area, hotel name or pincode.", tool={"name": "destination_search", "payload": None})
    if step == "CHECK_IN":
        return _text(lead + f"Check-in date in {city}? e.g. {(_today() + timedelta(days=7)).strftime('%d/%m/%Y')}, 'kal' or '25 dec'.",
                     [{"label": "Today", "value": "aaj"}, {"label": "Tomorrow", "value": "kal"}])
    if step == "CHECK_OUT":
        return _text(lead + "Check-out date, or how many nights? e.g. '2 nights' or a date.",
                     [{"label": f"{n} night{'s' if n > 1 else ''}", "value": f"{n} nights"} for n in (1, 2, 3)])
    if step == "ROOMS":
        return _text(lead + "How many rooms?", [{"label": str(n), "value": str(n)} for n in (1, 2, 3)])
    if step == "ADULTS":
        return _text(lead + "How many adults?", [{"label": str(n), "value": str(n)} for n in (1, 2, 3, 4)])
    if step == "CHILDREN":
        return _text(lead + "How many children? (0 if none)", [{"label": str(n), "value": str(n)} for n in (0, 1, 2)])
    if step == "CHILD_AGES":
        n = c.get("children") or 0
        return _text(lead + f"Age of {'each child' if n > 1 else 'the child'} (0-17){', e.g. 5, 8' if n > 1 else ', e.g. 6'}?")
    if step == "BUDGET":
        return _text(lead + f"Budget for the whole stay ({c.get('nights')} night{'s' if (c.get('nights') or 1) > 1 else ''})? "
                            "e.g. '10k', '15000 se kam', '3000 per night', or 'skip'.",
                     [{"label": "Sasta (under ₹1,500/night)", "value": "sasta"}, {"label": "Madhyam (₹1,500-3,000/night)", "value": "madhyam"},
                      {"label": "Premium (₹3,000+/night)", "value": "premium"}, {"label": "Skip", "value": "skip"}])
    if step == "CONFIRM":
        return _confirm(s, lead.strip())
    if step == "DESTINATION_SELECT" and s.get("options"):
        return {"type": "options", "text": lead + "Inme se apni jagah chuniye (choose your place):",
                "options": [{k: v for k, v in o.items() if k != "_d"} for o in s["options"]]}
    if step == "RESULTS" and s.get("results"):
        res = s["results"]
        return {"type": "hotels", "text": (lead + "Here are your hotels again.").strip(), "hotels": res.get("hotels") or [],
                "pagination": {"page": res.get("page") or 1, "pageSize": PAGE_SIZE, "total": res.get("total") or 0, "hasMore": bool(res.get("hasMore"))},
                "options": [{"label": "Show more", "value": "more"}] if res.get("hasMore") else []}
    return _text(lead.strip())


def _summary(c: Dict[str, Any]) -> str:
    d = c.get("destination") or {}
    where = d.get("label") or "?"
    if c.get("area"):
        where = f"{c['area']}, {where}"
    if c.get("pincode"):
        where += f" (pincode {c['pincode']})"
    ci, co = date.fromisoformat(c["checkIn"]), date.fromisoformat(c["checkOut"])
    n = c.get("nights") or (co - ci).days
    bits = [where, f"{ci.strftime('%d %b')} - {co.strftime('%d %b %Y')} ({n} night{'s' if n != 1 else ''})",
            f"{c['rooms']} room{'s' if c['rooms'] > 1 else ''}", f"{c['adults']} adult{'s' if c['adults'] > 1 else ''}"]
    if c.get("children"):
        bits.append(f"{c['children']} child{'ren' if c['children'] > 1 else ''} ({', '.join(map(str, c['childAges']))} yrs)")
    lo, hi = c.get("minPrice"), c.get("maxPrice")
    if lo or hi:
        b = f"budget {_money(lo)}-{_money(hi)}" if (lo and hi) else f"budget up to {_money(hi)}" if hi else f"budget from {_money(lo)}"
        if c.get("budgetPerNight"):
            b += f" ({_money(c['budgetPerNight'])} per night)"
        bits.append(b)
    if c.get("filters"):
        bits.append("filters: " + _filters_label(c["filters"]))
    return " · ".join(bits)


def _plan(c: Dict[str, Any]) -> List[Dict[str, Any]]:
    rooms = max(1, min(int(c["rooms"]), int(c["adults"])))
    base, extra = divmod(int(c["adults"]), rooms)
    plan = [{"adults": base + (1 if i < extra else 0), "children": 0, "childAges": []} for i in range(rooms)]
    for k, age in enumerate((c.get("childAges") or [])[: c.get("children") or 0]):
        plan[k % rooms]["children"] += 1
        plan[k % rooms]["childAges"].append(int(age))
    return plan


def _search_body(c: Dict[str, Any]) -> Dict[str, Any]:
    d = c.get("destination") or {}
    body = {"locationId": str(d.get("locationId") or ""), "geoCode": {"lat": d.get("lat"), "long": d.get("long")},
            "checkIn": c["checkIn"], "checkOut": c["checkOut"], "rooms": _plan(c), "nationality": "IN",
            "destinationCountryCode": "IN", "currency": c.get("currency") or "INR"}
    return body


def _confirm(s: Dict[str, Any], lead: str = "") -> Dict[str, Any]:
    c = s["c"]
    return {"type": "confirm", "text": (lead + " " if lead else "") + "Search hotels for: " + _summary(c) + "?",
            "payload": _search_body(c),
            "options": [{"label": "Search hotels", "value": "yes"}, {"label": "Change dates", "value": "edit:dates"},
                        {"label": "Change guests", "value": "edit:guests"}, {"label": "Change budget", "value": "edit:budget"},
                        {"label": "Change city", "value": "edit:destination"}]}


def _go(s: Dict[str, Any], lead: str = "") -> Dict[str, Any]:
    """Ask the first thing still missing (or show the summary)."""
    s["step"] = _missing(s["c"])
    return _question(s, lead)


def _set_budget(c: Dict[str, Any], b: Dict[str, Any]) -> None:
    """A budget into the trip. A per-night one is kept per night too, so the totals follow when the nights change."""
    n = max(1, c.get("nights") or 1)
    c["minPrice"], c["maxPrice"] = b.get("min"), b.get("max")
    c["budgetSkipped"] = False
    if b.get("per_night"):
        c["_pn"] = ((b["min"] / n) if b.get("min") else None, (b["max"] / n) if b.get("max") else None)
        c["budgetPerNight"] = round((c["_pn"][1] or c["_pn"][0]), 2)
    else:
        c["_pn"], c["budgetPerNight"] = None, None


def _clear_budget(c: Dict[str, Any], skipped: bool = False) -> None:
    c["minPrice"] = c["maxPrice"] = c["budgetPerNight"] = c["_pn"] = None
    c["budgetSkipped"] = skipped


def _recount(c: Dict[str, Any]) -> None:
    """Nights from the dates, and a per-night budget for the new number of nights."""
    if c.get("checkIn") and c.get("checkOut"):
        c["nights"] = (date.fromisoformat(c["checkOut"]) - date.fromisoformat(c["checkIn"])).days
        if c.get("_pn"):
            lo, hi = c["_pn"]
            c["minPrice"] = round(lo * c["nights"], 2) if lo else None
            c["maxPrice"] = round(hi * c["nights"], 2) if hi else None


# ============================================================================ understanding one message
async def _place(text: str) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    """(searchInput, area, pincode place) from the words that are left once dates, guests and budget are cut out."""
    pin = D["pincode_in"](text) if "pincode_in" in D else None
    if pin:
        place = await D["place_from_pincode"](pin)
        if place:
            return place["city"], None, place
    words = [w for w in re.findall(r"[a-z][a-z.'-]*", text) if w not in STOP and len(w) > 1]
    if not words:
        return None, None, None
    if len(words) == 1:
        return words[0], None, None
    for k in range(len(words), 0, -1):               # the longest start that the company knows as a city; the rest is an area
        cand = " ".join(words[:k])
        for d in await D["destinations"](cand):
            name = str(d.get("city") or d.get("label") or "").split(",")[0].strip().lower()
            if d.get("type") == "city" and name == cand:
                rest = " ".join(words[k:])
                return cand, (rest.title() if rest else None), None
    return " ".join(words), None, None


def _apply_slots(c: Dict[str, Any], t: str, step: str = "") -> Tuple[Dict[str, Any], str, List[str]]:
    """Dates, nights, guests and budget in a free sentence go into the trip. Returns (what changed, the text left, problems)."""
    changed: Dict[str, Any] = {}
    problems: List[str] = []
    today = _today()
    dates, t = _dates_in(t)
    nights, t = _nights_in(t)
    if dates:
        ci = dates[0]
        if ci < today:
            problems.append(f"{ci.strftime('%d %b %Y')} has already passed.")
        else:
            c["checkIn"] = ci.isoformat()
            changed["checkIn"] = c["checkIn"]
            c["checkOut"] = None
            if len(dates) > 1 and dates[1] > ci:
                c["checkOut"] = dates[1].isoformat()
    if nights:
        if 1 <= nights <= MAX_NIGHTS and c.get("checkIn"):
            c["checkOut"] = (date.fromisoformat(c["checkIn"]) + timedelta(days=nights)).isoformat()
            changed["checkOut"] = c["checkOut"]
        elif not 1 <= nights <= MAX_NIGHTS:
            problems.append(f"Stays are 1 to {MAX_NIGHTS} nights.")
        else:
            c["_nights"] = nights                    # no check-in yet: kept for when it comes
    if c.get("checkIn") and not c.get("checkOut") and c.get("_nights"):
        c["checkOut"] = (date.fromisoformat(c["checkIn"]) + timedelta(days=c.pop("_nights"))).isoformat()
    _recount(c)
    guests, t = _guests_in(t)
    for k, v in guests.items():
        c[k] = v
        changed[k] = v
    if guests.get("children") == 0:
        c["childAges"] = []
    if guests.get("childAges") and c.get("children") is None:
        c["children"] = len(guests["childAges"])
    b = parse_budget(t, c.get("nights") or (nights or 1), need_cue=True)
    if b:
        if not c.get("nights") and nights:
            c["nights"] = nights
        _set_budget(c, b)
        changed["budget"] = True
        t = AMOUNT.sub(" ", RANGE.sub(" ", t))
    return changed, t, problems


# ============================================================================ hotels
def _filters_label(f: Dict[str, Any]) -> str:
    bits = []
    if f.get("stars"):
        bits.append("/".join(str(n) for n in f["stars"]) + " star")
    if f.get("free_cancel"):
        bits.append("free cancellation")
    if f.get("breakfast"):
        bits.append("breakfast included")
    if f.get("property"):
        bits.append(str(f["property"]))
    bits += [str(a).lower() for a in f.get("amenities") or []]
    if f.get("hotel_name"):
        bits.append(f"name '{_safe(f['hotel_name'], 40)}'")
    if f.get("order") == "costly":
        bits.append("costliest first")
    elif f.get("order") == "stars":
        bits.append("most stars first")
    return ", ".join(bits)


async def _search(s: Dict[str, Any], page: int = 1, lead: str = "") -> Dict[str, Any]:
    c = s["c"]
    d = c["destination"]
    f = c.get("filters") or {}
    point = c.get("point") or {}
    req = D["SearchRequest"](
        service="hotels", origin=d["city"], destination=d["city"], destination_id=str(d.get("locationId") or "") or None,
        start_date=c["checkIn"], end_date=c["checkOut"], travellers=int(c["adults"]), rooms=max(1, min(int(c["rooms"]), int(c["adults"]))),
        children=int(c.get("children") or 0), child_ages=[int(a) for a in (c.get("childAges") or [])],
        budget=c.get("maxPrice") or None, budget_min=c.get("minPrice") or None, area=c.get("area") if not point else None,
        lat=point.get("lat"), lng=point.get("long"), near_label=point.get("label"), page=page, lang="en",
        stars=f.get("stars"), free_cancel=f.get("free_cancel"), breakfast=f.get("breakfast"), property_type=f.get("property"),
        amenities=f.get("amenities"), hotel_name=f.get("hotel_name"), order=f.get("order"))
    s["step"] = "RESULTS"
    s["page"] = page
    live = await D["hotels"](req)
    items = (live or {}).get("items") or []
    nights = max(1, c.get("nights") or 1)
    rooms = max(1, min(int(c["rooms"]), int(c["adults"])))
    hotels = [{
        "supplierHotelId": str(x.get("hotel_id") or str(x.get("id", ""))[3:]), "value": f"hotel:{x.get('hotel_id') or str(x.get('id', ''))[3:]}",
        "name": x.get("title"), "price": x.get("price"), "pricePerNight": round(float(x.get("price") or 0) / (nights * rooms), 2),
        "currency": x.get("currency") or "INR", "stars": x.get("stars"), "rating": x.get("rating"), "reviewCount": x.get("review_count"),
        "address": x.get("location"), "image": x.get("image"), "amenities": x.get("amenities") or [], "tags": x.get("meta") or [],
        "distanceKm": x.get("distance_km"), "lat": x.get("lat"), "lng": x.get("lng"), "searchId": x.get("search_id"),
    } for x in items]
    total = int((live or {}).get("total") or len(hotels))
    page = int((live or {}).get("page") or page)
    has_more = bool(hotels) and page * PAGE_SIZE < total
    s["results"] = {"hotels": hotels, "page": page, "total": total, "hasMore": has_more,
                    "searchId": hotels[0]["searchId"] if hotels else None}
    city = d.get("label") or d["city"]
    parts = [lead] if lead else []
    if hotels:
        parts.append(f"Found {total} hotels in {city}, showing {len(hotels)}" + (f" (page {page})" if page > 1 else "") + ".")
    else:
        parts.append((live or {}).get("note") or "No hotel came back for this search. Try other dates or a bigger budget.")
    if f:
        parts.append("Filters: " + _filters_label(f) + ".")
    lo, hi = c.get("minPrice"), c.get("maxPrice")
    if lo or hi:
        parts.append(("Budget: " + (f"{_money(lo)}-{_money(hi)}" if (lo and hi) else f"up to {_money(hi)}" if hi else f"from {_money(lo)}")) + ".")
    if hotels and (live or {}).get("note"):
        parts.append(str(live["note"]))
    opts = ([{"label": "Show more", "value": "more"}] if has_more else []) + [{"label": "Refresh prices", "value": "refresh"}]
    if lo or hi:
        opts.append({"label": "Remove budget", "value": "remove_budget"})
    if f:
        opts.append({"label": "Clear filters", "value": "filters hatao"})
    opts += [{"label": "Change dates", "value": "change dates"}, {"label": "New search", "value": "new search"}]
    return {"type": "hotels", "text": " ".join(p for p in parts if p), "hotels": hotels,
            "pagination": {"page": page, "pageSize": PAGE_SIZE, "total": total, "hasMore": has_more}, "options": opts}


async def _details(s: Dict[str, Any], hid: str) -> Dict[str, Any]:
    res = s.get("results") or {}
    hotel = next((h for h in res.get("hotels") or [] if h["supplierHotelId"] == hid), None)
    sid = (hotel or {}).get("searchId") or res.get("searchId") or ""
    c = s["c"]
    booking = {"searchId": str(sid), "hotelId": str(hid), "checkIn": c.get("checkIn"), "checkOut": c.get("checkOut"),
               "rooms": _plan(c) if c.get("rooms") and c.get("adults") else []}
    details, rooms, text = None, None, ""
    if sid and "details" in D:
        try:
            got = await D["details"](str(sid), str(hid), c.get("nights"))
            details, rooms = got.get("content"), got.get("rooms")
            n = len(rooms or [])
            text = f"{(hotel or {}).get('name') or (details or {}).get('name') or 'This hotel'}: {n} room option{'s' if n != 1 else ''}" + (
                f", from {_money(got['from_price'])}" if got.get("from_price") else "") + "."
        except Exception as exc:
            logger.warning("hotel details failed: %s", type(exc).__name__)
    if not details and not rooms:
        details = hotel
        text = text or ("Details could not be loaded right now; here is what the search showed." if hotel else "This hotel is not in the last results. Search again.")
    return {"type": "hotel_details", "text": text, "booking": booking, "details": details, "rooms": rooms,
            "options": [{"label": "Back to hotels", "value": "refresh"}, {"label": "New search", "value": "new search"}]}


# ============================================================================ the steps
async def _destination(s: Dict[str, Any], t: str, raw_value: Any = None, lead: str = "") -> Dict[str, Any]:
    c = s["c"]
    if isinstance(raw_value, dict):                  # the frontend sent the destination search body itself
        payload = {"searchInput": _safe(raw_value.get("searchInput"), 60)}
        search, area, place = payload["searchInput"], None, None
    else:
        _changed, rest, problems = _apply_slots(c, t)
        if problems:
            lead = (lead + " " + " ".join(problems)).strip()
        search, area, place = await _place(rest)
        payload = {"searchInput": search} if search else None
    if not search:
        s["step"] = "DESTINATION"
        return _text((lead + " " if lead else "") + "Which city or area? e.g. 'Jaipur' or 'Vaishali Nagar, Jaipur'.",
                     tool={"name": "destination_search", "payload": None})
    found = await D["destinations"](search)
    cities = [d for d in found if d.get("type") == "city"]
    others = [d for d in found if d.get("type") not in ("city", "hotel")]
    pick = (cities + others)[:8]
    if not pick:
        s["step"] = "DESTINATION"
        return _text(f"I couldn't find '{_safe(search, 40)}'. Try another city or area.", tool={"name": "destination_search", "payload": payload})
    c["area"] = area or c.get("area")
    if place:
        c["pincode"] = place.get("pincode")
        c["point"] = {"lat": place["lat"], "long": place["long"], "label": place["label"]}
    s["options"] = [{"label": d.get("label") or d.get("city"), "value": f"loc:{d.get('supplierLocationId') or d.get('id')}",
                     "type": d.get("type"), "_d": d} for d in pick]
    s["step"] = "DESTINATION_SELECT"
    head = (lead + " " if lead else "")
    if place:
        spot = re.sub(r"\s*\(\d{6}\)$", "", str(place.get("label") or "")).strip()
        head += f"Pincode {place['pincode']} is {spot + ', ' if spot and spot.lower() != place['city'].lower() else ''}{place['city']}. "
    if c.get("area"):
        head += f"Hotels near {_safe(c['area'])}. "
    return {"type": "options", "text": head + "Inme se apni jagah chuniye (choose your place):",
            "tool": {"name": "destination_search", "payload": payload},
            "options": [{k: v for k, v in o.items() if k != "_d"} for o in s["options"]]}


async def _choose(s: Dict[str, Any], o: Dict[str, Any]) -> Dict[str, Any]:
    d = o["_d"]
    c = s["c"]
    coords = d.get("coordinates") or {}
    if d.get("type") != "city":                      # an area: hotels near it, in its city
        c["area"] = c.get("area") or str(d.get("label") or "").split(",")[0]
        city = next((x for x in await D["destinations"](str(d.get("city") or "")) if x.get("type") == "city"), None)
        if city:
            d, coords = city, city.get("coordinates") or coords
    city_name = d.get("city") or str(d.get("label") or "").split(",")[0]
    c["destination"] = {"label": city_name, "city": city_name, "locationId": str(d.get("supplierLocationId") or d.get("id") or ""),
                        "lat": coords.get("lat"), "long": coords.get("long"), "type": d.get("type")}
    s["options"] = []
    return _go(s, f"{c['destination']['city']} it is.")


async def _handle(s: Dict[str, Any], message: str, value: Any) -> Dict[str, Any]:
    raw = value if value not in (None, "") else message
    t = _plain(raw if isinstance(raw, str) else "")
    c, step = s["c"], s["step"]

    # ---------------------------------------------------------- anywhere
    if isinstance(value, dict):
        return await _destination(s, "", value)
    if RESET.match(t):
        cur = c.get("currency")
        s["c"], s["options"], s["results"] = _blank(), [], None
        s["c"]["currency"] = cur
        s["step"] = "DESTINATION"
        return _question(s, "Okay, a new search.")
    if not t:
        return _question(s, "Please type something.")
    if GREET.match(t):
        return _question(s, "Hello! I'm the DestinoWay hotel assistant.")
    if HELP.match(t):
        return _question(s, "Tell me everything in one line, e.g. 'jaipur me 15/12 se 3 raat, 2 adults, budget 15000'. "
                            "You can also say: back, change dates, change budget, new search.")
    if t in ("edit:dates", "change dates", "change date", "dates badlo", "date badlo") and c.get("destination"):
        c["checkIn"] = c["checkOut"] = None
        s["step"] = "CHECK_IN"
        return _question(s, "Okay, new dates.")
    if t in ("edit:budget", "change budget", "budget badlo") and c.get("destination"):
        _clear_budget(c)
        s["step"] = "BUDGET"
        return _question(s, "Okay, a new budget.")
    if t in ("edit:guests", "change guests", "guests badlo") and c.get("destination"):
        c["rooms"] = c["adults"] = c["children"] = None
        c["childAges"] = []
        s["step"] = "ROOMS"
        return _question(s, "Okay, the guests again.")
    if t in ("edit:destination", "change city", "city badlo"):
        c["destination"], c["area"], c["point"], c["pincode"] = None, None, None, None
        s["step"] = "DESTINATION"
        return _question(s)
    if BACK.match(t):
        prev = {"DESTINATION_SELECT": "DESTINATION", "CHECK_IN": "DESTINATION", "CHECK_OUT": "CHECK_IN", "ROOMS": "CHECK_OUT",
                "ADULTS": "ROOMS", "CHILDREN": "ADULTS", "CHILD_AGES": "CHILDREN", "BUDGET": "CHILDREN", "CONFIRM": "BUDGET",
                "RESULTS": "CONFIRM"}.get(step, "DESTINATION")
        clear = {"DESTINATION": ("destination",), "CHECK_IN": ("checkIn", "checkOut"), "CHECK_OUT": ("checkOut",), "ROOMS": ("rooms",),
                 "ADULTS": ("adults",), "CHILDREN": ("children",), "BUDGET": ("minPrice", "maxPrice", "budgetPerNight", "_pn"), "CONFIRM": ()}[prev]
        for k in clear:
            c[k] = None
        if prev == "BUDGET":
            c["budgetSkipped"] = False
        if prev == "CHILDREN":
            c["childAges"] = []
        s["step"] = prev
        return _question(s)

    # ---------------------------------------------------------- per step
    if step == "DESTINATION":
        return await _destination(s, t)

    if step == "DESTINATION_SELECT":
        opts = s.get("options") or []
        o = next((o for o in opts if o["value"] == t or o["value"] == str(raw).strip()), None)
        if not o and re.fullmatch(r"\d{1,2}", t) and 1 <= int(t) <= len(opts):
            o = opts[int(t) - 1]
        if not o:
            o = next((o for o in opts if str(o["label"]).lower().startswith(t) and len(t) >= 3), None)
        if o:
            return await _choose(s, o)
        return await _destination(s, t)

    if step == "CHECK_IN":
        dates, rest = _dates_in(t)
        if not dates:
            city = (c.get("destination") or {}).get("city") or ""
            words = " ".join(w for w in re.findall(r"[a-z][a-z.'-]*", t) if w not in STOP)
            area = await D["resolve_area"](city, words) if (words and len(words) >= 3 and city and "resolve_area" in D) else None
            label = str((area or {}).get("label") or "").lower()
            if area and (words in label or label.split(",")[0].strip() in words):
                c["area"] = words.title()
                return _question(s, f"Okay, {c['area']} noted - hotels near it.")
            return _question(s, "I couldn't read a date there.")
        if dates[0] < _today():
            return _question(s, f"{dates[0].strftime('%d %b %Y')} has already passed.")
        if (dates[0] - _today()).days > 365:
            return _question(s, "Bookings open up to a year ahead.")
        c["checkIn"], c["checkOut"] = dates[0].isoformat(), None
        nights, _ = _nights_in(rest)
        if len(dates) > 1 and dates[1] > dates[0]:
            c["checkOut"] = dates[1].isoformat()
        elif nights and 1 <= nights <= MAX_NIGHTS:
            c["checkOut"] = (dates[0] + timedelta(days=nights)).isoformat()
        _recount(c)
        return _go(s)

    if step == "CHECK_OUT":
        ci = date.fromisoformat(c["checkIn"])
        nights, rest = _nights_in(t)
        dates, _ = _dates_in(rest)
        if nights is None and not dates and re.fullmatch(r"\d{1,2}", t):
            nights = int(t)
        if nights is not None:
            if not 1 <= nights <= MAX_NIGHTS:
                return _question(s, f"Stays are 1 to {MAX_NIGHTS} nights.")
            co = ci + timedelta(days=nights)
        elif dates:
            co = dates[0]
            if co <= ci:
                return _question(s, f"Check-out must be after check-in ({ci.strftime('%d %b %Y')}).")
            if (co - ci).days > MAX_NIGHTS:
                return _question(s, f"Stays are 1 to {MAX_NIGHTS} nights.")
        else:
            return _question(s, "I couldn't read that.")
        c["checkOut"] = co.isoformat()
        _recount(c)
        return _go(s)

    if step in ("ROOMS", "ADULTS", "CHILDREN"):
        guests, _ = _guests_in(t)
        key = step.lower()
        n = guests.get(key)
        if n is None:
            m = re.fullmatch(r"\s*(-?\d+|[a-z]+)\s*", t)
            n = _num(m.group(1)) if m else None
        if step == "CHILDREN" and n is None and re.fullmatch(r"(no|nahi|nhi|none|zero|koi nahi)", t):
            n = 0
        if n is None:
            return _question(s, "Please send a number.")
        if step == "ROOMS" and not 1 <= n <= MAX_ROOMS:
            return _question(s, f"Rooms: 1 to {MAX_ROOMS}.")
        if step == "ADULTS":
            if n < (c.get("rooms") or 1):
                return _question(s, f"Every room needs at least one adult: at least {c.get('rooms')} adults for {c.get('rooms')} rooms.")
            if n > MAX_ADULTS:
                return _question(s, f"Up to {MAX_ADULTS} adults in one booking.")
        if step == "CHILDREN" and not 0 <= n <= MAX_CHILDREN:
            return _question(s, f"Children: 0 to {MAX_CHILDREN}.")
        c[key] = n
        if step == "CHILDREN" and n == 0:
            c["childAges"] = []
        return _go(s)

    if step == "CHILD_AGES":
        ages = [int(x) for x in re.findall(r"-?\d+", t)]
        need = c.get("children") or 0
        if any(a < 0 or a > 17 for a in ages):
            return _question(s, "A child is 0 to 17 years old.")
        if len(ages) != need:
            return _question(s, f"Please send {need} age{'s' if need > 1 else ''}, one for each child.")
        c["childAges"] = ages
        return _go(s)

    if step == "BUDGET":
        if SKIP.match(t):
            _clear_budget(c, True)
            return _go(s, "No budget limit.")
        b = parse_budget(t, c.get("nights") or 1)
        if not b:
            return _question(s, "I couldn't read a budget.")
        _set_budget(c, b)
        return _go(s)

    if step == "CONFIRM":
        if YES.match(t):
            return await _search(s, 1)
        changed, _rest, problems = _apply_slots(c, t)
        if changed or problems:
            return _go(s, " ".join(problems) if problems else "Updated.")
        return _question(s, "Say 'ok' to search, or tap a button to change something.")

    if step == "RESULTS":
        if isinstance(raw, str) and raw.strip().lower().startswith("hotel:"):
            return await _details(s, raw.strip().split(":", 1)[1].strip())
        if MORE.match(t):
            res = s.get("results") or {}
            if not res.get("hasMore"):
                return {"type": "text", "text": "That was the last page. Change a filter or the budget to see other hotels.",
                        "options": [{"label": "Refresh prices", "value": "refresh"}, {"label": "New search", "value": "new search"}]}
            return await _search(s, (res.get("page") or 1) + 1)
        if t == "refresh":
            return await _search(s, s.get("page") or 1)
        if t == "remove_budget":
            _clear_budget(c, True)
            return await _search(s, 1, "Budget removed.")
        found, clear = D["filters_in_text"](t)
        if found or clear:
            merged = D["merge_filters"](dict(c.get("filters") or {}), found, clear)
            c["filters"] = {k: v for k, v in merged.items() if k in ("stars", "free_cancel", "breakfast", "property", "amenities", "hotel_name", "order")}
            return await _search(s, 1, "Filters cleared." if (clear and not found) else "")
        b = parse_budget(t, c.get("nights") or 1, need_cue=True)
        if b:
            _set_budget(c, b)
            return await _search(s, 1)
        changed, _rest, problems = _apply_slots(c, t)
        if changed and not problems:
            return await _search(s, 1, "Updated.")
        res = s.get("results") or {}
        return {"type": "hotels", "text": "I didn't get that. Say 'more', a filter ('3 star se upar', 'free cancellation'), "
                                          "a budget ('under 8000'), 'change dates' or 'new search'.",
                "hotels": res.get("hotels") or [], "pagination": {"page": res.get("page") or 1, "pageSize": PAGE_SIZE,
                                                                  "total": res.get("total") or 0, "hasMore": bool(res.get("hasMore"))},
                "options": [{"label": "Show more", "value": "more"}] if res.get("hasMore") else []}

    return _question(s)


# ============================================================================ routes
TOOLS = [
    {"name": "destination_search", "description": "Find a city, area or hotel", "endpoint": "POST /api/v1/destination/search",
     "payload": {"searchInput": "string"}},
    {"name": "hotel_search", "description": "Start a live hotel search", "endpoint": "POST /api/v1/hotelSearch/search",
     "payload": {"locationId": "string", "geoCode": {"lat": "number", "long": "number"}, "checkIn": "YYYY-MM-DD", "checkOut": "YYYY-MM-DD",
                 "rooms": [{"adults": "number", "children": "number", "childAges": ["number"]}], "nationality": "IN", "currency": "INR"}},
    {"name": "hotel_results", "description": "A page of the results, with filters", "endpoint": "GET /api/v1/hotelSearch/search/{searchId}"},
    {"name": "hotel_details", "description": "A hotel's details and rooms", "endpoint": "GET /api/v1/hotelDetails/search/{searchId}/{hotelId}/rooms"},
]


def _limit(request: Request) -> Optional[JSONResponse]:
    if "rate_limit" in D:
        try:
            D["rate_limit"](f"stepbot:{D['client_ip'](request)}", 150, 60)
        except Exception:
            return JSONResponse({"success": False, "message": "Too many requests. Please slow down."}, status_code=429)
    return None


@router.get("/tools")
async def tools():
    return {"success": True, "message": "Tools", "data": TOOLS}


@router.post("/start")
async def start(request: Request):
    stop = _limit(request)
    if stop:
        return stop
    s = _new(request.headers.get("currency") or "INR")
    return _answer(s, _question(s, "Hi! I'll help you find a hotel.") | {"type": "text"}, "Chat started successfully")


@router.post("/message")
async def message(request: Request):
    stop = _limit(request)
    if stop:
        return stop
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "message": "The body must be JSON: {sessionId, message} or {sessionId, value}."}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"success": False, "message": "The body must be a JSON object."}, status_code=400)
    msg, value = body.get("message"), body.get("value")
    if msg is not None and not isinstance(msg, str):
        return JSONResponse({"success": False, "message": "`message` must be a string."}, status_code=400)
    if value is not None and not isinstance(value, (str, dict)):
        return JSONResponse({"success": False, "message": "`value` must be a string or an object."}, status_code=400)
    msg = (msg or "")[:500]
    if isinstance(value, str):
        value = value[:200]
    s = _get(body.get("sessionId")) or _new(request.headers.get("currency") or "INR")
    try:
        reply = await _handle(s, msg, value)
    except Exception:
        logger.exception("step bot failed")
        reply = _question(s, "Something went wrong on our side. Please try again.")
    return _answer(s, reply)


@router.get("/session/{session_id}")
async def session(session_id: str):
    s = _get(session_id)
    if not s:
        return JSONResponse({"success": False, "message": "Session not found"}, status_code=404)
    return {"success": True, "message": "Session", "data": {"sessionId": s["id"], "step": s["step"], "reply": s.get("reply") or {},
                                                            "collected": _public(s["c"]), "results": s.get("results")}}
