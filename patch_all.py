# One patch for everything that is still pending. Safe to run twice.
# If any step cannot be applied, every file is put back as it was.
import json, os, re, sys

FILES = [
    "frontend/src/pages/Checkout.jsx", "frontend/src/App.css", "frontend/src/App.js",
    "frontend/src/lib/GlobalVoice.jsx", "frontend/src/lib/validate.js", "frontend/public/index.html",
    "backend/server.py",
]

def step_checkout():
    P = "frontend/src/pages/Checkout.jsx"
    CSS = "frontend/src/App.css"
    try:
        c = open(P, encoding="utf-8").read()
        css = open(CSS, encoding="utf-8").read()
    except OSError as e:
        sys.exit("STOP: " + str(e) + " (run this from the repo root, D:\\projects\\destinoway-chatbot-demo)")
    if "validateTraveller" in c:
        sys.exit("Already applied. Nothing to do.")
    if not __import__("os").path.exists("frontend/src/lib/validate.js"):
        sys.exit("STOP: frontend/src/lib/validate.js is missing. Run patch_validate.py first.")


    def swap(text, old, new, label):
        if text.count(old) != 1:
            sys.exit("STOP: " + label + " not found (nothing was changed)")
        return text.replace(old, new)


    # a terminal line-wrap once glued two attributes together
    c = c.replace("requireddata-testid", "required data-testid")

    imports = list(re.finditer(r"^import .*$", c, re.M))
    if not imports:
        sys.exit("STOP: no imports found in Checkout.jsx (nothing was changed)")
    last = imports[-1]
    c = c[:last.end()] + '\nimport { validateTraveller } from "../lib/validate";' + c[last.end():]

    form_line = re.search(r"^  const \[form, setForm\] = useState\(.*\);\n", c, re.M)
    if not form_line:
        sys.exit("STOP: form state line not found (nothing was changed)")
    helpers = (
        "  const [errors, setErrors] = useState({});\n"
        "  // re-check the fields that are showing an error while the user fixes them\n"
        "  useEffect(() => {\n"
        "    setErrors((old) => {\n"
        "      if (!Object.keys(old).length) return old;\n"
        "      const now = validateTraveller(form);\n"
        "      const next = {};\n"
        "      Object.keys(old).forEach((k) => { if (now[k]) next[k] = now[k]; });\n"
        "      return next;\n"
        "    });\n"
        "  }, [form]);\n"
        "  const check = (k) => setErrors((old) => {\n"
        "    const msg = validateTraveller(form)[k];\n"
        "    const next = { ...old };\n"
        "    if (msg) next[k] = msg; else delete next[k];\n"
        "    return next;\n"
        "  });\n"
        "  const bad = (k) => (errors[k] ? <small className=\"field-error\" role=\"alert\">{errors[k]}</small> : null);\n"
    )
    c = c[:form_line.end()] + helpers + c[form_line.end():]

    c = swap(c, '    if (!form.name || !form.email || !form.phone) { toast.error("Please fill all details"); return; }\n',
             '    const found = validateTraveller(form);\n'
             '    setErrors(found);\n'
             '    const firstBad = Object.keys(found)[0];\n'
             '    if (firstBad) {\n'
             '      toast.error(found[firstBad]);\n'
             '      const el = document.querySelector(`[data-testid="checkout-${firstBad}"]`);\n'
             '      if (el && el.focus) el.focus();\n'
             '      return;\n'
             '    }\n', "the 'fill all details' check")

    c = swap(c, '<form className="checkout-form" onSubmit={pay}>', '<form className="checkout-form" onSubmit={pay} noValidate>', "form tag")

    pat = re.compile(r'data-testid="checkout-(name|email|phone|city|address)"\s*/>')
    if len(pat.findall(c)) != 5:
        sys.exit("STOP: expected 5 checkout inputs, found %d (nothing was changed)" % len(pat.findall(c)))
    c = pat.sub(lambda m: 'onBlur={() => check("%s")} aria-invalid={!!errors.%s} data-testid="checkout-%s"/>{bad("%s")}' % ((m.group(1),) * 4), c)

    css = css.rstrip("\n") + (
        "\n.field-error { display: block; margin-top: 6px; color: #c62828; font-size: 12.5px; line-height: 1.35; }\n"
        ".checkout-form input[aria-invalid=\"true\"] { border-color: #c62828 !important; }\n"
    )
    open(P, "w", encoding="utf-8").write(c)
    open(CSS, "w", encoding="utf-8").write(css)
    print("OK: checkout form now checks every field (typed or spoken) and shows the reason")


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

def step_server():
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


def step_errors():
    CO = "frontend/src/pages/Checkout.jsx"
    SV = "backend/server.py"
    done = []

    # ---- Checkout.jsx: show what the server said, under the right field ----
    if os.path.exists(CO):
        c = open(CO, encoding="utf-8").read()
        old = '    } catch {\n      toast.error("Could not start payment.");\n      setPaying(false);\n    }\n'
        if "const detail = err" in c:
            done.append("Checkout.jsx: already shows the server message")
        elif "validateTraveller" not in c:
            sys.exit("STOP: run patch_checkout.py first (Checkout.jsx has no field checks yet). Nothing was changed.")
        elif c.count(old) != 1:
            sys.exit("STOP: the 'Could not start payment' block was not found in Checkout.jsx (nothing was changed)")
        else:
            new = (
                "    } catch (err) {\n"
                "      const detail = err && err.response && err.response.data && err.response.data.detail;\n"
                "      const msg = typeof detail === \"string\" ? detail : \"Could not start payment.\";\n"
                "      toast.error(msg);\n"
                "      if (typeof detail === \"string\") {\n"
                "        const key = /city/i.test(detail) ? \"city\" : /address/i.test(detail) ? \"address\" : /email/i.test(detail) ? \"email\" : /mobile|phone/i.test(detail) ? \"phone\" : /name/i.test(detail) ? \"name\" : null;\n"
                "        if (key) {\n"
                "          setErrors((o) => ({ ...o, [key]: msg }));\n"
                "          const el = document.querySelector(`[data-testid=\"checkout-${key}\"]`);\n"
                "          if (el && el.focus) el.focus();\n"
                "        }\n"
                "      }\n"
                "      setPaying(false);\n"
                "    }\n"
            )
            open(CO, "w", encoding="utf-8").write(c.replace(old, new, 1))
            done.append("Checkout.jsx: server messages now show on screen")
    else:
        sys.exit("STOP: " + CO + " not found. Run this from the repo root.")

    # ---- server.py: name the wrong value in the message ----
    if os.path.exists(SV):
        s = open(SV, encoding="utf-8").read()
        if "_check_traveller" not in s:
            done.append("server.py: no traveller check yet (run patch_server_check.py), skipped")
        else:
            oc = '        return "Please enter a valid city (a state is not a city)."\n'
            oa = '        return "Please enter the full address, with house number, street and area."\n    return ""\n'
            if "is a state, not a city" in s:
                done.append("server.py: messages already clear")
            elif s.count(oc) == 1 and s.count(oa) == 1:
                s = s.replace(oc, '        return (f"{city.title()} is a state, not a city. Please enter your city, for example Gurugram." if _is_state(city) else "Please enter a valid city name.")\n', 1)
                s = s.replace(oa, '        return ("That is a state. Please enter the full address, with house number, street and area." if _is_state(address) else "Please enter the full address, with house number, street and area.")\n    return ""\n', 1)
                open(SV, "w", encoding="utf-8").write(s)
                done.append("server.py: messages now say e.g. 'Rajasthan is a state, not a city'")
            else:
                sys.exit("STOP: server message lines not found (Checkout.jsx was already changed; run again after checking)")
    print("OK:")
    for d in done:
        print(" -", d)


def step_app():
    APP = "frontend/src/App.js"
    GV = "frontend/src/lib/GlobalVoice.jsx"
    try:
        a = open(APP, encoding="utf-8").read()
        g = open(GV, encoding="utf-8").read()
    except OSError as e:
        sys.exit("STOP: " + str(e) + " (run this from the repo root, D:\\projects\\destinoway-chatbot-demo)")


    def swap(text, old, new, label):
        if text.count(old) != 1:
            sys.exit("STOP: " + label + " not found (nothing was changed)")
        return text.replace(old, new)


    if "AIConcierge" in a:
        a = swap(a, 'import AIConcierge from "./components/AIConcierge";\n', "", "AIConcierge import")
        a = swap(a, "      {!isAgentHome && <AIConcierge />}\n", "", "AIConcierge line")
        # these two only existed to hide the old widget on the chat page
        a = swap(a, "  const location = useLocation();\n  const isAgentHome = location.pathname === \"/\";\n", "", "isAgentHome lines")
        a = swap(a, "import { BrowserRouter, Route, Routes, useLocation } from", "import { BrowserRouter, Route, Routes } from", "react-router import")
        if "AIConcierge" in a or "isAgentHome" in a or "useLocation" in a:
            sys.exit("STOP: something is still left over in App.js (nothing was changed)")
        removed = True
    else:
        removed = False

    m = re.search(r'"bookings": null', g)
    fixed = False
    if m:
        g = g.replace('"bookings": null', '"bookings": "/dashboard"', 1)
        fixed = True

    if not removed and not fixed:
        sys.exit("Already applied. Nothing to do.")
    open(APP, "w", encoding="utf-8").write(a)
    open(GV, "w", encoding="utf-8").write(g)
    print("OK:", "old concierge button removed" if removed else "concierge already gone",
          "| my bookings opens /dashboard" if fixed else "| bookings path already set")


NEWNAME = r'''// Names that are placeholders, not a real person. "Traveller" is what a new account is called.
const GENERIC_NAMES = new Set([
  "traveller", "traveler", "guest", "user", "customer", "test", "testing", "demo", "dummy", "name", "fullname",
  "full", "your", "my", "na", "n", "a", "none", "unknown", "admin", "abc", "xyz", "asdf", "qwerty", "sample", "example",
]);

export function validateName(v) {
  const t = String(v || "").replace(/\s+/g, " ").trim();
  if (!t) return "Please enter the traveller's full name.";
  if (t.length < 2 || t.length > 60) return "Name must be 2 to 60 letters.";
  if (!/^[\p{L}\p{M}'. \-]+$/u.test(t)) return "Name can have only letters and spaces.";
  const letters = t.replace(/[^\p{L}]/gu, "");
  if (letters.length < 2) return "Please enter the traveller's full name.";
  if (/^(.)\1+$/u.test(letters.toLowerCase())) return "Please enter a real name.";
  if (t.toLowerCase().split(" ").every((w) => GENERIC_NAMES.has(w.replace(/[.']/g, "")))) {
    return `"${t}" is not a real name. Please enter the traveller's full name, as on their ID.`;
  }
  return "";
}

// A saved name that is only a placeholder should not be pre-filled.
export function cleanName(n) {
  const t = String(n || "").trim();
  return validateName(t) ? "" : t;
}

function titleCaseWords(s) {
  return s.split(" ").map((w) => (w ? w[0].toUpperCase() + w.slice(1).toLowerCase() : w)).join(" ");
}

// Tidy what was typed before it is sent: spaces, capital letters, +91 on the number.
export function tidyTraveller(t) {
  const x = { ...(t || {}) };
  if (x.name) x.name = titleCaseWords(String(x.name).replace(/\s+/g, " ").trim());
  if (x.city) x.city = titleCaseWords(String(x.city).replace(/\s+/g, " ").trim());
  if (x.address) x.address = String(x.address).replace(/\s+/g, " ").trim();
  if (x.email) x.email = String(x.email).trim().toLowerCase();
  if (x.phone) {
    const m = String(x.phone).replace(/[\s\-()]/g, "").match(/^(?:\+91|0091|91|0)?(\d{10})$/);
    if (m) x.phone = `+91 ${m[1]}`;
  }
  return x;
}

'''
GENERIC = r'''_GENERIC_NAMES = {
    "traveller", "traveler", "guest", "user", "customer", "test", "testing", "demo", "dummy", "name", "fullname",
    "full", "your", "my", "na", "n", "a", "none", "unknown", "admin", "abc", "xyz", "asdf", "qwerty", "sample", "example",
}
'''

def step_names():
    VAL, CO, SV = "frontend/src/lib/validate.js", "frontend/src/pages/Checkout.jsx", "backend/server.py"
    for p in (VAL, CO):
        if not os.path.exists(p):
            sys.exit("STOP: " + p + " is missing. Run the earlier patches first, from the repo root.")
    v, c = open(VAL, encoding="utf-8").read(), open(CO, encoding="utf-8").read()
    if "cleanName" in v:
        sys.exit("Already applied. Nothing to do.")
    if "validateTraveller" not in c:
        sys.exit("STOP: run patch_checkout.py first (nothing was changed)")


    def swap(text, old, new, label):
        if text.count(old) != 1:
            sys.exit("STOP: " + label + " not found (nothing was changed)")
        return text.replace(old, new)


    a, b = v.find("export function validateName"), v.find("export function validateEmail")
    if a < 0 or b < a:
        sys.exit("STOP: validateName not found (nothing was changed)")
    v = v[:a] + NEWNAME + v[b:]

    c = swap(c, 'import { validateTraveller } from "../lib/validate";', 'import { validateTraveller, cleanName, tidyTraveller } from "../lib/validate";', "validate import")
    c = swap(c, 'useState({ name: user?.name || "",', 'useState({ name: cleanName(user?.name),', "initial name")
    c = swap(c, 'name: data.traveller?.name || user?.name || "",', 'name: cleanName(data.traveller?.name) || cleanName(user?.name),', "saved name")
    c = swap(c, "traveller: form,", "traveller: tidyTraveller(form),", "traveller sent to server")

    out_sv = "server.py not found, skipped"
    if os.path.exists(SV):
        s = open(SV, encoding="utf-8").read()
        if "_check_traveller" not in s:
            out_sv = "server.py has no traveller check yet, skipped"
        elif "_GENERIC_NAMES" in s:
            out_sv = "server.py already checks placeholder names"
        else:
            old = '    if not (2 <= len(name) <= 60) or not _only_letters(name) or sum(ch.isalpha() for ch in name) < 2:\n        return "Please enter a valid full name."\n'
            if s.count(old) != 1:
                sys.exit("STOP: name check not found in server.py (nothing was changed)")
            new = old + (
                '    if all(w.replace(".", "").replace("\'", "").lower() in _GENERIC_NAMES for w in name.split()):\n'
                '        return f\'"{name}" is not a real name. Please enter the traveller\\\'s full name, as on their ID.\'\n'
                '    if len(set(name.replace(" ", "").lower())) == 1:\n'
                '        return "Please enter a real name."\n'
            )
            s = s.replace(old, new, 1)
            anchor = "_EMAIL_RX = "
            if s.count(anchor) != 1:
                sys.exit("STOP: _EMAIL_RX anchor not found in server.py (nothing was changed)")
            s = s.replace(anchor, GENERIC + anchor, 1)
            open(SV, "w", encoding="utf-8").write(s)
            out_sv = "server.py rejects placeholder names too"

    open(VAL, "w", encoding="utf-8").write(v)
    open(CO, "w", encoding="utf-8").write(c)
    print("OK: 'Traveller' is no longer accepted as a name; names and cities are tidied before sending")
    print(" -", out_sv)


def step_emergent():
    P = "frontend/public/index.html"
    try:
        h = open(P, encoding="utf-8").read()
    except OSError:
        sys.exit("STOP: " + P + " not found. Run this from the repo root (D:\\projects\\destinoway-chatbot-demo).")

    if "posthog" not in h.lower() and "emergent" not in h.lower():
        sys.exit("Already clean. Nothing to do.")

    pat = re.compile(r"[ \t]*<script\b[^>]*>(?:(?!</script>).)*?posthog(?:(?!</script>).)*?</script>[ \t]*\n?", re.S | re.I)
    found = pat.findall(h)
    if len(found) != 1:
        sys.exit("STOP: expected exactly 1 posthog script, found %d (nothing was changed)" % len(found))
    h = pat.sub("", h, count=1)
    h = re.sub(r'(<meta name="description" content=")[^"]*(")', r"\1DestinoWay AI - plan and book your trip by chat or voice\2", h, count=1)

    if "posthog" in h.lower():
        sys.exit("STOP: posthog text is still there after removal (nothing was changed)")
    open(P, "w", encoding="utf-8").write(h)
    print("OK: tracking script removed from index.html")
    left = [l.strip() for l in h.splitlines() if "emergent" in l.lower()]
    print("Remaining lines that mention emergent:", left if left else "none")


STEPS = [
    ("Checkout form checks (typed and spoken)", step_checkout),
    ("Server checks on /bookings", step_server),
    ("Show server messages on screen", step_errors),
    ("Remove old concierge button, My bookings path", step_app),
    ("Reject placeholder names, tidy input", step_names),
    ("Remove Emergent tracking script", step_emergent),
]


def main():
    snapshot = {}
    for p in FILES:
        if os.path.exists(p):
            snapshot[p] = open(p, encoding="utf-8").read()
    if "frontend/src/pages/Checkout.jsx" not in snapshot:
        sys.exit("STOP: run this from the repo root (D:\\projects\\destinoway-chatbot-demo).")
    for label, fn in STEPS:
        print("==", label)
        try:
            fn()
        except SystemExit as e:
            msg = str(e.code) if e.code is not None else ""
            if msg.startswith("Already"):
                print("   already done, skipped")
                continue
            for p, text in snapshot.items():
                open(p, "w", encoding="utf-8").write(text)
            print("\nSTOPPED at: " + label)
            print(msg)
            print("Every file was put back as it was. Send me the lines above.")
            sys.exit(1)
    print("\nALL DONE. Now: git add -A, git commit, git push")


main()