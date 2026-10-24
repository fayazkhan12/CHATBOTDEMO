BLOCK = r'''# ---------- traveller details check (same rules as the web form) ----------
import re as _re
import unicodedata as _ud

_STATES = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "chattisgarh", "gujarat", "haryana",
    "himachal pradesh", "himachal", "jharkhand", "karnataka", "kerala", "madhya pradesh", "maharashtra", "manipur",
    "meghalaya", "mizoram", "nagaland", "odisha", "orissa", "punjab", "rajasthan", "sikkim", "tamil nadu", "tamilnadu",
    "telangana", "tripura", "uttar pradesh", "uttarakhand", "uttaranchal", "west bengal", "jammu and kashmir",
    "jammu kashmir", "ladakh", "lakshadweep", "andaman and nicobar", "india", "bharat",
}
_EMAIL_RX = _re.compile(r"^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$", _re.I)


def _is_state(text: str) -> bool:
    return " ".join(text.lower().replace("state", " ").split()) in _STATES


def _only_letters(text: str) -> bool:
    # letters and marks of any script (Hindi vowel signs are marks), plus space ' . -
    return all(_ud.category(ch)[0] in ("L", "M") or ch in " '.-" for ch in text)


def _traveller_problem(t) -> str:
    """Returns a message when a traveller field is wrong, or '' when all is fine."""
    t = t if isinstance(t, dict) else {}
    get = lambda k: " ".join(str(t.get(k) or "").split())  # noqa: E731
    phone_raw = get("phone")
    if not phone_raw:
        return ""  # first step of a booking: details are asked later, on the payment page
    name, email, city, address = get("name"), get("email"), get("city"), get("address")
    if not (2 <= len(name) <= 60) or not _only_letters(name) or sum(ch.isalpha() for ch in name) < 2:
        return "Please enter a valid full name."
    if len(email) > 120 or ".." in email or not _EMAIL_RX.match(email):
        return "Please enter a valid email address."
    digits = _re.sub(r"[\s\-()]", "", phone_raw)
    m = _re.match(r"^(?:\+91|0091|91|0)?(\d{10})$", digits)
    if not m or m.group(1)[0] not in "6789" or len(set(m.group(1))) == 1:
        return "Please enter a valid 10 digit Indian mobile number."
    if city and (not (2 <= len(city) <= 40) or any(ch.isdigit() for ch in city) or not _only_letters(city) or _is_state(city)):
        return "Please enter a valid city (a state is not a city)."
    if address and (len(address) < 8 or len(address) > 160 or _is_state(address) or (len(address.split()) < 2 and not any(ch.isdigit() for ch in address))):
        return "Please enter the full address, with house number, street and area."
    return ""


def _check_traveller(t) -> None:
    problem = _traveller_problem(t)
    if problem:
        raise HTTPException(status_code=422, detail=problem)


'''
import re, sys

P = "backend/server.py"
try:
    s = open(P, encoding="utf-8").read()
except OSError:
    sys.exit("STOP: " + P + " not found. Run this from the repo root (D:\\projects\\destinoway-chatbot-demo).")
if "_check_traveller" in s:
    sys.exit("Already applied. Nothing to do.")

deco = '@api.post("/bookings")\nasync def create_booking('
if s.count(deco) != 1:
    sys.exit("STOP: create_booking not found exactly once (nothing was changed)")
if "HTTPException" not in s:
    sys.exit("STOP: HTTPException is not imported in server.py (nothing was changed)")
m = re.search(r"async def create_booking\([^\n]*\):\n", s)
if not m:
    sys.exit("STOP: create_booking signature is not on one line (nothing was changed)")

s = s.replace(deco, BLOCK + deco, 1)
m = re.search(r"async def create_booking\([^\n]*\):\n", s)
s = s[:m.end()] + "    _check_traveller(body.traveller)\n" + s[m.end():]
open(P, "w", encoding="utf-8").write(s)
print("OK: /bookings now rejects wrong traveller details (a state is not a city)")