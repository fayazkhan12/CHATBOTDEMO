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

import os, sys

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