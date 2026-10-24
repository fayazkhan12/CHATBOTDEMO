import os, re, sys

NEWNAME = r'''const NAME_FILLER = new Set(["my", "name", "is", "full", "the", "i", "am", "im", "this", "naam", "mera", "meraa", "poora", "pura", "hai", "ha", "me", "main", "hoon", "hu", "it", "its", "uh", "um", "ok", "okay"]);

export function parseName(text) {
  let t = String(text || "").replace(/[.,!?;:]+/g, " ").replace(/\s+/g, " ").trim();
  for (let i = 0; i < 3; i += 1) {
    t = t.replace(/^(my (full )?name is|my name|name is|this is|i am|i'm|im|mera (poora |pura )?naam|mera name|mera|naam|मेरा (पूरा )?नाम|नाम)(\s+|$)/i, "");
  }
  t = t.replace(/\s+(hai|hoon|hu|है|हूँ|हूं)$/i, "").trim();
  if (!t || t.length > 60 || /\d/.test(t)) return null;
  if (!/^[\p{L}\p{M}'\- ]+$/u.test(t)) return null;
  const words = t.split(" ").filter(Boolean);
  if (words.length > 5 || t.replace(/[^\p{L}]/gu, "").length < 2) return null;
  if (words.every((w) => NAME_FILLER.has(w.toLowerCase()))) return null;
  return titleCase(words.join(" "));
}

'''
PARTS_CMD = r'''
// Digits spoken one by one ("nine eight seven") or typed; used for OTP and PIN codes.
export function parseDigits(text, min, max) {
  const toks = normalizeWords(text).split(" ").filter(Boolean);
  let digits = "";
  let mult = 1;
  for (const w of toks) {
    if (w === "double" || w === "dabal") { mult = 2; continue; }
    if (w === "triple" || w === "tripal") { mult = 3; continue; }
    let d = null;
    if (/^\d+$/.test(w)) d = w;
    else if (Object.prototype.hasOwnProperty.call(DIGIT_WORDS, w)) d = String(DIGIT_WORDS[w]);
    if (d === null) { mult = 1; continue; }
    digits += d.length === 1 ? d.repeat(mult) : d;
    mult = 1;
  }
  return digits.length >= min && digits.length <= max ? digits : null;
}
'''
GVTPL = r'''import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useVoiceDock, routeChanged } from "./useVoiceDock";
import { isHomeIntent, isBookingsIntent, isLoginIntent } from "./voicecmd";
import { createPageGuide } from "./pageform";

// Paths found in App.js when this was installed.
__PATHSLINE__

const BACK_RE = /\b(go back|back|wapas|vapas|peeche)\b/;

function AppDock() {
  const navigate = useNavigate();
  const formRef = useRef(null);
  const go = (path, msg) => {
    if (!path) return { say: "That page is not available here.", listen: true };
    navigate(path);
    return { say: msg, listen: false };
  };
  useVoiceDock({
    maxTurns: 40,
    onStart: () => {
      formRef.current = createPageGuide();
      if (formRef.current) return formRef.current.start();
      return { say: "Say home, my bookings, login or back. You can also just use the screen.", listen: true };
    },
    onText: (said) => {
      if (BACK_RE.test(said.toLowerCase())) { navigate(-1); return { listen: false }; }
      if (formRef.current) return formRef.current.handle(said);
      if (isHomeIntent(said)) return go(PATHS.home, "Taking you home.");
      if (isBookingsIntent(said)) return go(PATHS.bookings, "Opening your bookings.");
      if (isLoginIntent(said)) return go(PATHS.login, "Opening login.");
      return { say: "Sorry. Say home, my bookings, login or back.", listen: true };
    },
  }, 0);
  return null;
}

// Every page gets the mic. The chat page has its own mic, so it is skipped there.
export default function GlobalVoice() {
  const { pathname } = useLocation();
  useEffect(() => { routeChanged(); }, [pathname]);
  if (pathname === PATHS.home) return null;
  return <AppDock />;
}
'''
PAGEFORM = r'''// Reads the form on the current page and guides the user through it by voice.
import { parsePhone, parseEmail, parseName, parseCity, parseAddress, parseDigits } from "./voicecmd";
import { createFormGuide } from "./voicedock";

const SKIP_TYPES = new Set(["hidden", "password", "checkbox", "radio", "file", "submit", "button", "reset", "range", "color", "image", "date", "time", "datetime-local", "month", "week"]);

function isVisible(el) {
  try {
    if (el.closest && (el.closest(".vdock") || el.closest("[hidden]"))) return false;
    if (typeof window.getComputedStyle === "function") {
      const s = window.getComputedStyle(el);
      if (s.display === "none" || s.visibility === "hidden") return false;
    }
  } catch (e) { /* treat as visible */ }
  return true;
}

function labelOf(el) {
  let t = "";
  try {
    if (el.labels && el.labels.length) t = el.labels[0].textContent;
    if (!t && el.closest) { const p = el.closest("label"); if (p) t = p.textContent; }
    if (!t) t = el.getAttribute("aria-label") || "";
    if (!t) {
      const p = el.previousElementSibling;
      if (p && /^(label|div|span|p)$/i.test(p.tagName) && p.textContent.length < 40) t = p.textContent;
    }
  } catch (e) { /* fall through */ }
  if (!t) t = el.placeholder || el.name || el.id || "field";
  return t.replace(/\*/g, " ").replace(/\(.*?\)/g, " ").replace(/\s+/g, " ").trim();
}

function kindOf(el, label) {
  const s = [el.type, el.name, el.id, el.autocomplete, label, el.placeholder].join(" ").toLowerCase();
  if (/otp|verification|one.?time|passcode/.test(s)) return "otp";
  if (el.type === "email" || /e-?mail/.test(s)) return "email";
  if (el.type === "tel" || /phone|mobile|contact|whatsapp/.test(s)) return "phone";
  if (/city|shehar/.test(s)) return "city";
  if (/address|pata|street/.test(s)) return "address";
  if (/pin ?code|zip|postal/.test(s)) return "pin";
  if (/name|naam/.test(s)) return "name";
  if (el.type === "number") return "number";
  return "text";
}

function phoneParser(el, label) {
  const withCode = /^\+/.test(el.placeholder || "") || /code/i.test(label) || /with code/i.test(el.closest && el.closest("label") ? el.closest("label").textContent : "");
  return (text) => {
    const v = parsePhone(text);
    if (!v) return null;
    return withCode ? v : v.replace(/\D/g, "").slice(-10);
  };
}

function specFor(kind, el, label, optional) {
  const skip = optional ? " Say skip to skip." : "";
  const lower = label.toLowerCase();
  switch (kind) {
    case "name": return { ask: `What is your ${lower}?`, retry: "Sorry, please say it again.", parse: parseName };
    case "email": return { ask: "Your email address. Say at the rate and dot where needed." + skip, retry: "I could not get a valid email. Please say it again, for example name at the rate gmail dot com.", parse: parseEmail };
    case "phone": return { ask: "Your mobile number, digit by digit." + skip, retry: "I could not get a valid 10 digit mobile number. Please say it again, digit by digit.", parse: phoneParser(el, label) };
    case "otp": return { ask: "Say the code, digit by digit.", retry: "I could not get the code. Please say the digits again.", parse: (t) => parseDigits(t, 4, 8) };
    case "pin": return { ask: "Say the PIN code, digit by digit." + skip, retry: "Please say the PIN code again, digit by digit.", parse: (t) => parseDigits(t, 5, 6) };
    case "number": return { ask: `Say the ${lower}.` + skip, retry: "Please say the number again.", parse: (t) => parseDigits(t, 1, 9) };
    case "city": return { ask: "Which city?" + skip, retry: "Please say the city name." + skip, parse: parseCity };
    case "address": return { ask: "Your address?" + skip, retry: "Please say the address." + skip, parse: parseAddress };
    default: return { ask: `Please say ${lower}.` + skip, retry: `Please say ${lower} again.` + skip, parse: (t) => { const s = String(t || "").replace(/\s+/g, " ").trim(); return s.length >= 1 && s.length <= 120 ? s : null; } };
  }
}

export function scanFields() {
  if (typeof document === "undefined") return [];
  const out = [];
  const nodes = document.querySelectorAll("input, textarea");
  for (const el of nodes) {
    const type = (el.type || "text").toLowerCase();
    if (SKIP_TYPES.has(type) || el.disabled || el.readOnly) continue;
    if (!isVisible(el)) continue;
    if (String(el.value || "").trim()) continue;
    const label = labelOf(el);
    const optional = !(el.required || (el.labels && el.labels[0] && /\*/.test(el.labels[0].textContent)));
    const kind = kindOf(el, label);
    const spec = specFor(kind, el, label, optional);
    out.push({ el, key: out.length, label, optional, words: label.toLowerCase().split(" ").filter(Boolean), ...spec });
  }
  return out;
}

// Sets a value the way a user typing would, so React sees it.
export function setFieldValue(el, value) {
  const proto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
  setter.call(el, value);
  el.dispatchEvent(new window.Event("input", { bubbles: true }));
  el.dispatchEvent(new window.Event("change", { bubbles: true }));
}

// Returns a guide for the fields on this page, or null when the page has none to fill.
export function createPageGuide() {
  const fields = scanFields();
  if (!fields.length) return null;
  return createFormGuide(() => ({
    fields,
    onValue: (k, v) => setFieldValue(fields[k].el, v),
    doneText: "All fields are filled. Please check the screen and tap the button yourself to continue.",
    editText: "All fields are filled. Say change and the field name to edit, or tap the button to continue.",
  }));
}
'''

LIB = "frontend/src/lib/"
CMD, DOCK, GV, PF = LIB + "voicecmd.js", LIB + "voicedock.js", LIB + "GlobalVoice.jsx", LIB + "pageform.js"
for p in (CMD, DOCK, GV):
    if not os.path.exists(p):
        sys.exit("STOP: " + p + " is missing. Run patch_everywhere.py first, from the repo root.")


def read(p):
    return open(p, encoding="utf-8").read()


cmd, dock, gv = read(CMD), read(DOCK), read(GV)
if os.path.exists(PF) or "parseDigits" in cmd:
    sys.exit("Already applied. Nothing to do.")


def swap(text, old, new, label, count=1):
    if text.count(old) != count:
        sys.exit("STOP: " + label + " not found (nothing was changed)")
    return text.replace(old, new)


# ---- voicecmd.js: a better parseName ("my name is" alone is not a name) + digit parser ----
a = cmd.find("export function parseName")
b = cmd.find("export function parseCity")
if a < 0 or b < a:
    sys.exit("STOP: parseName not found (nothing was changed)")
cmd = cmd[:a] + NEWNAME.lstrip("\n") + cmd[b:]
if "DIGIT_WORDS" not in cmd:
    sys.exit("STOP: DIGIT_WORDS not found (nothing was changed)")
cmd = cmd.rstrip("\n") + "\n" + PARTS_CMD

# ---- voicedock.js: no more plain "Listening..." bubble; form guide texts can be set by the page ----
dock = swap(dock, 'onInterim: (t) => setNote(t ? `\\u201c${t}\\u201d` : "Listening..."),',
            'onInterim: (t) => { if (t) setNote(`\\u201c${t}\\u201d`); },', "interim note")
dock = swap(dock, '    setListening(true);\n    setNote("Listening...");\n', '    setListening(true);\n', "listening note")
dock = swap(dock, "  const fields = () => getOpts().fields;\n",
            '  const fields = () => getOpts().fields;\n'
            '  const DONE = () => getOpts().doneText || "All details are filled. Please check the screen and tap Pay.";\n'
            '  const EDIT = () => getOpts().editText || "All details are filled. Say change name, phone or email to edit, or tap Pay.";\n',
            "form guide header")
dock = swap(dock, 'return T("All details are filled. Please check the screen and tap Pay.", false);', "return T(DONE(), false);", "done text")
dock = swap(dock, 'return T("All details are filled. Say change name, phone or email to edit, or tap Pay.", true);', "return T(EDIT(), true);", "edit text (start)")
dock = swap(dock, 'return T("All details are filled. Say change name, phone or email to edit, or tap Pay.", false);', "return T(EDIT(), false);", "edit text (handle)")

# ---- GlobalVoice.jsx: fill the fields found on any page ----
m = re.search(r"^const PATHS = .*;$", gv, re.M)
if not m:
    sys.exit("STOP: PATHS line not found in GlobalVoice.jsx (nothing was changed)")
gv = GVTPL.replace("__PATHSLINE__", m.group(0))

open(CMD, "w", encoding="utf-8").write(cmd)
open(DOCK, "w", encoding="utf-8").write(dock)
open(GV, "w", encoding="utf-8").write(gv)
open(PF, "w", encoding="utf-8").write(PAGEFORM)
print("OK: voice now reads each page's form and fills it; Listening bubble removed")