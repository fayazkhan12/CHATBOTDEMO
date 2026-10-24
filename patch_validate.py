import os, sys

NEWCITY = r'''// States and union territories are not cities. Goa, Delhi, Chandigarh and Puducherry are left out on purpose:
// people use them as city names.
const NOT_CITIES = new Set([
  "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "chattisgarh", "gujarat", "haryana",
  "himachal pradesh", "himachal", "jharkhand", "karnataka", "kerala", "madhya pradesh", "maharashtra", "manipur",
  "meghalaya", "mizoram", "nagaland", "odisha", "orissa", "punjab", "rajasthan", "sikkim", "tamil nadu", "tamilnadu",
  "telangana", "tripura", "uttar pradesh", "uttarakhand", "uttaranchal", "west bengal", "jammu and kashmir",
  "jammu kashmir", "ladakh", "lakshadweep", "andaman and nicobar", "india", "bharat",
  "आंध्र प्रदेश", "असम", "बिहार",
  "छत्तीसगढ़", "छत्तीसगढ", "गुजरात",
  "हरियाणा", "हिमाचल प्रदेश", "झारखंड",
  "कर्नाटक", "केरल", "मध्य प्रदेश",
  "महाराष्ट्र", "ओडिशा", "पंजाब",
  "राजस्थान", "तमिलनाडु", "तेलंगाना",
  "उत्तर प्रदेश", "उत्तराखंड",
  "पश्चिम बंगाल", "भारत",
  "ਪੰਜਾਬ", "ਹਰਿਆਣਾ",
]);

export function isStateName(text) {
  const t = normalizeWords(text).replace(/\b(state|rajya)\b/g, "").replace(/\s+/g, " ").trim();
  return NOT_CITIES.has(t);
}

function stateName(text) {
  return titleCase(normalizeWords(text).replace(/\b(state|rajya)\b/g, "").replace(/\s+/g, " ").trim());
}

export function parseCity(text) {
  let t = String(text || "").replace(/[.,!?;:।]+/g, " ").replace(/\s+/g, " ").trim();
  t = t.replace(/^(my )?(city|town) is\s+|^(i live in|i am from|i'm from|im from|from|mera shehar|mera sheher|mera city)\s+/i, "");
  t = t.replace(/\s+(hai|hoon|hu|se|se hu|se hoon|है|से)$/i, "").trim();
  if (t.length < 2 || t.length > 40 || /\d/.test(t)) return null;
  if (!/^[\p{L}\p{M}'. \-]+$/u.test(t)) return null;
  if (t.split(" ").length > 4) return null;
  if (isStateName(t)) return null;
  return titleCase(t);
}

export function explainCity(text) {
  const t = String(text || "").replace(/^(my )?(city|town) is\s+/i, "");
  if (isStateName(t)) return `${stateName(t)} is a state, not a city. Please say your city name, for example Gurugram, or say skip.`;
  return null;
}

export function parseAddress(text) {
  let t = String(text || "").replace(/\s+/g, " ").trim();
  t = t.replace(/^(my )?address is\s+|^(mera )?pata\s+/i, "").trim();
  if (t.length < 8 || t.length > 160) return null;
  if (!/[\p{L}]/u.test(t)) return null;
  if (isStateName(t)) return null;
  if (t.split(" ").length < 2 && !/\d/.test(t)) return null;
  return t;
}

export function explainAddress(text) {
  const t = String(text || "").replace(/^(my )?address is\s+/i, "");
  if (isStateName(t)) return "That is a state. Please say the full address, with house number, street and area, or say skip.";
  return "Please say the full address, with house number, street and area, or say skip.";
}

'''
VALIDATE = r'''// One set of checks for traveller details, used by the form and by voice.
import { isStateName } from "./voicecmd";

const EMAIL_RE = /^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$/i;
const DOMAIN_TYPOS = {
  "gmial.com": "gmail.com", "gmai.com": "gmail.com", "gamil.com": "gmail.com", "gmail.con": "gmail.com",
  "gmail.co": "gmail.com", "gmaill.com": "gmail.com", "gmil.com": "gmail.com",
  "yahooo.com": "yahoo.com", "yaho.com": "yahoo.com", "hotmial.com": "hotmail.com", "outlok.com": "outlook.com",
};

export function validateName(v) {
  const t = String(v || "").replace(/\s+/g, " ").trim();
  if (!t) return "Please enter your full name.";
  if (t.length < 2 || t.length > 60) return "Name must be 2 to 60 letters.";
  if (!/^[\p{L}\p{M}'. \-]+$/u.test(t)) return "Name can have only letters and spaces.";
  if (t.replace(/[^\p{L}]/gu, "").length < 2) return "Please enter your full name.";
  return "";
}

export function validateEmail(v) {
  const t = String(v || "").trim().toLowerCase();
  if (!t) return "Please enter your email.";
  if (t.length > 120 || !EMAIL_RE.test(t) || t.includes("..")) return "Please enter a valid email, like name@gmail.com.";
  const domain = t.split("@")[1];
  if (DOMAIN_TYPOS[domain]) return `Did you mean ${t.split("@")[0]}@${DOMAIN_TYPOS[domain]}?`;
  return "";
}

export function validatePhone(v) {
  const d = String(v || "").replace(/[\s\-()]/g, "");
  if (!d) return "Please enter your mobile number.";
  const m = d.match(/^(?:\+91|0091|91|0)?(\d{10})$/);
  if (!m) return "Enter a 10 digit mobile number, like +91 9876543210.";
  if (!/^[6-9]/.test(m[1])) return "Indian mobile numbers start with 6, 7, 8 or 9.";
  if (/^(\d)\1{9}$/.test(m[1])) return "Please enter a real mobile number.";
  return "";
}

// City and address are optional, but when given they must make sense.
export function validateCity(v) {
  const t = String(v || "").replace(/\s+/g, " ").trim();
  if (!t) return "";
  if (t.length < 2 || t.length > 40 || /\d/.test(t) || !/^[\p{L}\p{M}'. \-]+$/u.test(t)) return "Please enter a valid city name.";
  if (isStateName(t)) return `${t} is a state. Please enter your city, for example Gurugram.`;
  return "";
}

export function validateAddress(v) {
  const t = String(v || "").replace(/\s+/g, " ").trim();
  if (!t) return "";
  if (isStateName(t)) return "That is a state. Please enter the full address, with house number, street and area.";
  if (t.length < 8) return "Please enter the full address, with house number, street and area.";
  if (t.length > 160) return "Address is too long. Please keep it under 160 characters.";
  if (t.split(" ").length < 2 && !/\d/.test(t)) return "Please enter the full address, with house number, street and area.";
  return "";
}

// Returns { name, email, phone, city, address } with a message for every field that is wrong.
export function validateTraveller(t) {
  const e = {
    name: validateName(t && t.name),
    email: validateEmail(t && t.email),
    phone: validatePhone(t && t.phone),
    city: validateCity(t && t.city),
    address: validateAddress(t && t.address),
  };
  Object.keys(e).forEach((k) => { if (!e[k]) delete e[k]; });
  return e;
}
'''

LIB = "frontend/src/lib/"
CMD, DOCK, PF, VAL = LIB + "voicecmd.js", LIB + "voicedock.js", LIB + "pageform.js", LIB + "validate.js"
for p in (CMD, DOCK, PF):
    if not os.path.exists(p):
        sys.exit("STOP: " + p + " is missing. Run the earlier patches first, from the repo root.")


def read(p):
    return open(p, encoding="utf-8").read()


cmd, dock, pf = read(CMD), read(DOCK), read(PF)
if os.path.exists(VAL) or "explainCity" in cmd:
    sys.exit("Already applied. Nothing to do.")
if "spokenDigits" not in cmd:
    sys.exit("STOP: run patch_perfect.py first (nothing was changed)")


def swap(text, old, new, label, count=1):
    if text.count(old) != count:
        sys.exit("STOP: " + label + " not found (nothing was changed)")
    return text.replace(old, new)


a, b = cmd.find("export function parseCity"), cmd.find("export function isSkip")
if a < 0 or b < a:
    sys.exit("STOP: parseCity/isSkip not found (nothing was changed)")
cmd = cmd[:a] + NEWCITY + cmd[b:]

dock = swap(dock, "parseAddress, phonePartial, emailPartial } from", "parseAddress, phonePartial, emailPartial, explainCity, explainAddress } from", "voicedock import")
dock = swap(dock, "parse: parseCity, optional: true,", "parse: parseCity, explain: explainCity, optional: true,", "checkout city")
dock = swap(dock, "parse: parseAddress, dictation: true, optional: true,", "parse: parseAddress, explain: explainAddress, dictation: true, optional: true,", "checkout address")
dock = swap(dock, "        return T(cur.retry, true);", "        return T((cur.explain && cur.explain(joined)) || cur.retry, true);", "retry message")

pf = swap(pf, "parseDigits, phonePartial, emailPartial, digitsPartial } from", "parseDigits, phonePartial, emailPartial, digitsPartial, explainCity, explainAddress } from", "pageform import")
pf = swap(pf, "parse: parseCity };", "parse: parseCity, explain: explainCity };", "pf city")
pf = swap(pf, "parse: parseAddress, dictation: true };", "parse: parseAddress, explain: explainAddress, dictation: true };", "pf address")

open(CMD, "w", encoding="utf-8").write(cmd)
open(DOCK, "w", encoding="utf-8").write(dock)
open(PF, "w", encoding="utf-8").write(pf)
open(VAL, "w", encoding="utf-8").write(VALIDATE)
print("OK: city and address are checked (a state is not a city); validate.js added")