import os, re, sys, json

CMD_ADD = r'''
// ---- dictation helpers: phone numbers and emails arrive in several pieces ----

// All digits in the text, whether typed ("73 89") or spoken ("seven three").
export function spokenDigits(text) {
  const toks = normalizeWords(text).split(" ").filter(Boolean);
  let digits = "";
  let mult = 1;
  for (const w of toks) {
    if (w === "double" || w === "dabal" || w === "डबल") { mult = 2; continue; }
    if (w === "triple" || w === "tripal" || w === "ट्रिपल") { mult = 3; continue; }
    let d = null;
    if (/^\d+$/.test(w)) d = w;
    else if (Object.prototype.hasOwnProperty.call(DIGIT_WORDS, w)) d = String(DIGIT_WORDS[w]);
    if (d === null) { mult = 1; continue; }
    digits += d.length === 1 ? d.repeat(mult) : d;
    mult = 1;
  }
  return digits;
}

function sayDigits(d) { return d.split("").join(" "); }

// Returns what to tell the user when only part of a number was heard, or null when it is hopeless.
export function digitsPartial(text, min) {
  const d = spokenDigits(text);
  if (d.length > 0 && d.length < min) return `I heard ${d.length} digits: ${sayDigits(d)}. Say the remaining digits.`;
  return null;
}

export function phonePartial(text) {
  let d = spokenDigits(text);
  if (d.startsWith("91") && d.length > 10) d = d.slice(2);
  if (d.length > 0 && d.length < 10) return `I heard ${d.length} digits: ${sayDigits(d)}. Say the remaining digits.`;
  return null;
}

export function emailPartial(text) {
  const t = String(text || "").toLowerCase();
  const hasAt = /@|\bat\b|attherate|एट|ऐट/.test(t);
  const letters = t.replace(/[^a-z0-9ऀ-ॿ]/g, "").length;
  if (!hasAt) return letters >= 2 ? "Got it. Now say at the rate, then the domain, for example gmail dot com." : null;
  const after = t.split(/@|\bat the rate( of)?\b|\bat rate\b|\battherate\b|\bat\b/).pop() || "";
  if (after.replace(/[^a-zऀ-ॿ]/g, "").length < 2) return "Now say the domain, for example gmail dot com.";
  return null;
}
'''
GUIDE = r'''// getOpts() -> { fields, onValue(key, value), onDone(), doneText, editText }
const FIELD_RX = {
  name: /name|naam/,
  phone: /phone|mobile|tel|contact/,
  email: /mail/,
  city: /city|shehar/,
  address: /address|pata|street/,
};

function guessField(key) {
  const rx = FIELD_RX[key];
  if (!rx) return null;
  const nodes = document.querySelectorAll("input, textarea");
  for (const el of nodes) {
    if (el.closest && el.closest(".vdock")) continue;
    let label = "";
    try { if (el.labels && el.labels[0]) label = el.labels[0].textContent; } catch (e) { /* ignore */ }
    const s = [el.type, el.name, el.id, el.getAttribute("data-testid"), el.placeholder, el.getAttribute("aria-label"), label].join(" ").toLowerCase();
    if (key === "name" && /mail|user/.test(s)) continue;
    if (rx.test(s)) return el;
  }
  return null;
}

// Outlines the field being asked about, so the screen shows where the answer goes.
function markField(f) {
  try {
    document.querySelectorAll(".vfield-attn").forEach((n) => n.classList.remove("vfield-attn"));
    if (!f) return;
    const el = f.el || guessField(f.key);
    if (!el) return;
    el.classList.add("vfield-attn");
    if (el.scrollIntoView) el.scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (e) { /* ignore */ }
}

export function createFormGuide(getOpts) {
  let idx = 0;
  let fails = 0;
  let buf = "";
  let partials = 0;
  const fields = () => getOpts().fields;
  const DONE = () => getOpts().doneText || "All details are filled. Please check the screen and tap Pay.";
  const EDIT = () => getOpts().editText || "All details are filled. Say change name, phone or email to edit, or tap Pay.";
  // Phone numbers, emails and addresses come with pauses, so wait longer before cutting in.
  const T = (say, listen) => {
    const f = fields()[idx];
    return { say, listen, lang: "en-IN", silenceMs: listen && f && f.dictation ? 3200 : undefined };
  };

  function advance(got) {
    const f = fields();
    if (idx >= f.length) {
      const o = getOpts();
      if (o.onDone) o.onDone();
      return T(DONE(), false);
    }
    return T(`${got ? "Got it. " : ""}${f[idx].ask}`, true);
  }

  const inner = {
    start() {
      const f = fields();
      buf = ""; partials = 0;
      if (idx >= f.length) return T(EDIT(), true);
      return T(`${idx === 0 ? "Let us fill your details. " : ""}${f[idx].ask}`, true);
    },
    handle(text) {
      const raw = String(text || "");
      const t = normalizeWords(raw);
      const f = fields();
      if (/\b(stop|cancel|exit|quit|band|ruko)\b/.test(t)) { buf = ""; return T("Okay, I stopped. Tap the mic to continue.", false); }
      if (/\b(pay|payment|paisa|bhugtan)\b/.test(t)) return T("Please tap the Pay button yourself when you are ready.", false);
      if (/\b(change|edit|correct|badlo|badal|galat|wrong)\b/.test(t)) {
        const j = f.findIndex((x) => x.words.some((w) => t.split(" ").includes(w)));
        if (j >= 0) { idx = j; fails = 0; buf = ""; partials = 0; return T(f[j].ask, true); }
      }
      if (/\b(repeat|again|dobara|once more)\b/.test(t) && idx < f.length) { buf = ""; partials = 0; return T(f[idx].ask, true); }
      if (idx >= f.length) return T(EDIT(), false);
      const cur = f[idx];
      if (cur.optional && isSkip(t)) { idx += 1; fails = 0; buf = ""; partials = 0; return advance(false); }
      const joined = cur.dictation ? `${buf} ${raw}`.trim() : raw;
      const v = cur.parse(joined);
      if (v == null) {
        if (cur.dictation && cur.partial && partials < 4) {
          const hint = cur.partial(joined);
          if (hint) { buf = joined; partials += 1; return T(hint, true); }
        }
        buf = ""; partials = 0;
        fails += 1;
        if (fails >= 3) {
          fails = 0;
          idx += 1;
          if (idx >= f.length) return T("I could not hear that. Please type it, then tap the button.", false);
          return T("I am having trouble hearing that. Please type this one, then tap the mic to continue.", false);
        }
        return T(cur.retry, true);
      }
      buf = ""; partials = 0;
      getOpts().onValue(cur.key, v);
      idx += 1;
      fails = 0;
      return advance(true);
    },
  };

  const mark = () => {
    const f = fields();
    markField(idx < f.length ? f[idx] : null);
  };
  return {
    start() { const r = inner.start(); mark(); return r; },
    handle(text) { const r = inner.handle(text); mark(); return r; },
  };
}
'''
CSS_ADD = r'''.vdock-note { position: fixed; top: 84px; left: 50%; transform: translateX(-50%); z-index: 70; max-width: min(360px, calc(100vw - 32px)); }
.vfield-attn { outline: 3px solid #E8820C !important; outline-offset: 2px; border-radius: 12px; transition: outline-color 0.2s; }
'''

LIB = "frontend/src/lib/"
CMD, DOCK, PF, CSS = LIB + "voicecmd.js", LIB + "voicedock.js", LIB + "pageform.js", "frontend/src/App.css"
for p in (CMD, DOCK, PF, CSS):
    if not os.path.exists(p):
        sys.exit("STOP: " + p + " is missing. Run the earlier patches first, from the repo root.")


def read(p):
    return open(p, encoding="utf-8").read()


cmd, dock, pf, css = read(CMD), read(DOCK), read(PF), read(CSS)
if "spokenDigits" in cmd:
    sys.exit("Already applied. Nothing to do.")


def swap(text, old, new, label, count=1):
    if text.count(old) != count:
        sys.exit("STOP: " + label + " not found (nothing was changed)")
    return text.replace(old, new)


# ---- voicecmd.js ----
HI_DIGITS = {"शून्य":0,"जीरो":0,"ज़ीरो":0,"एक":1,"वन":1,"दो":2,"टू":2,"तीन":3,"थ्री":3,"चार":4,"फोर":4,"पांच":5,"पाँच":5,"पंच":5,"फाइव":5,"छह":6,"छः":6,"छे":6,"सिक्स":6,"सात":7,"सेवन":7,"आठ":8,"नौ":9,"नाइन":9,"ਸਿਫਰ":0,"ਇੱਕ":1,"ਦੋ":2,"ਤਿੰਨ":3,"ਚਾਰ":4,"ਪੰਜ":5,"ਛੇ":6,"ਸੱਤ":7,"ਅੱਠ":8,"ਨੌਂ":9}
cmd = swap(cmd, "  eight: 8, aath: 8, ath: 8, nine: 9, nau: 9,\n};",
    "  eight: 8, aath: 8, ath: 8, nine: 9, nau: 9,\n" + "".join("  %s: %d,\n" % (json.dumps(k), v) for k, v in HI_DIGITS.items()) + "};", "DIGIT_WORDS")
cmd = swap(cmd, '  five: "5", six: "6", seven: "7", eight: "8", nine: "9",\n};',
    '  five: "5", six: "6", seven: "7", eight: "8", nine: "9",\n' + "".join("  %s: %s,\n" % (json.dumps(k), json.dumps(str(v))) for k, v in HI_DIGITS.items() if k[0] < "\u0a00" and k not in ("वन","टू","थ्री","फोर","फाइव","सिक्स","सेवन","नाइन","जीरो","ज़ीरो","छः","छे","पंच")) + "};", "EMAIL_DIGITS")
cmd = swap(cmd, '  let t = String(text || "").toLowerCase().trim();\n  t = t.replace(/\\bat the rate',
    '  let t = String(text || "").toLowerCase().trim();\n'
    '  t = t.replace(/(एट|ऐट) (द|दा|दी) रेट/g, " @ ").replace(/डॉट/g, " . ")\n'
    '    .replace(/जी ?मेल/g, "gmail").replace(/कॉम/g, "com").replace(/याहू/g, "yahoo")\n'
    '    .replace(/आउटलुक/g, "outlook").replace(/हॉटमेल/g, "hotmail")\n'
    '    .replace(/अंडरस्कोर/g, " _ ").replace(/डैश/g, " - ");\n'
    '  t = t.replace(/\\bat the rate', "parseEmail start")
cmd = swap(cmd, 'if (w === "double" || w === "dabal") { mult = 2; continue; }',
           'if (w === "double" || w === "dabal" || w === "\\u0921\\u092c\\u0932") { mult = 2; continue; }', "double word", 2)
cmd = swap(cmd, 'if (w === "triple" || w === "tripal") { mult = 3; continue; }',
           'if (w === "triple" || w === "tripal" || w === "\\u091f\\u094d\\u0930\\u093f\\u092a\\u0932") { mult = 3; continue; }', "triple word", 2)
cmd = cmd.rstrip("\n") + "\n" + CMD_ADD

# ---- voicedock.js ----
dock = swap(dock, 'import { normalizeWords, isSkip, parseName, parsePhone, parseEmail, parseCity, parseAddress } from "./voicecmd";',
            'import { normalizeWords, isSkip, parseName, parsePhone, parseEmail, parseCity, parseAddress, phonePartial, emailPartial } from "./voicecmd";', "voicecmd import")
dock = swap(dock, '  const setNote = (t) => { note.textContent = t || ""; note.hidden = !t; };\n',
            '  // Prompts are spoken and the asked field is outlined, so no bubble covers the form.\n'
            '  // Only real problems (mic blocked, no device...) show a short message.\n'
            '  let toastTimer = null;\n'
            '  const setNote = () => {};\n'
            '  const toast = (t) => {\n'
            '    clearTimeout(toastTimer);\n'
            '    note.textContent = t || "";\n'
            '    note.hidden = !t;\n'
            '    if (t) toastTimer = setTimeout(() => { note.hidden = true; }, 6000);\n'
            '  };\n', "setNote")
dock = swap(dock, 'else if (reason && reason !== "done") { active = false; setNote(describeStop(reason)); }',
            'else if (reason && reason !== "done") { active = false; toast(describeStop(reason)); }', "stop toast")
dock = swap(dock, 'if (reason === "idle") { active = false; setNote("I did not hear anything. Tap the mic to continue."); }',
            'if (reason === "idle") { active = false; }', "idle note")
dock = swap(dock, 'if (!eng) { active = false; setNote(describeStop("unsupported")); return; }',
            'if (!eng) { active = false; toast(describeStop("unsupported")); return; }', "unsupported toast")
dock = swap(dock, "      alive = false;\n      clearTimeout(flowTimer);\n", "      alive = false;\n      clearTimeout(flowTimer);\n      clearTimeout(toastTimer);\n", "destroy")
dock = swap(dock, "timer = setTimeout(() => listen(turn.lang, id), 450);", "timer = setTimeout(() => listen(turn.lang, id, turn.silenceMs), 450);", "runTurn listen")
dock = swap(dock, "  function listen(lang, id) {", "  function listen(lang, id, silenceMs) {", "listen signature")
dock = swap(dock, "      once: true,\n      idleMs: 12000,\n", "      once: true,\n      idleMs: 12000,\n      silenceMs: silenceMs || 1500,\n", "engine options")
dock = swap(dock, "parse: parsePhone, words:", "parse: parsePhone, dictation: true, partial: phonePartial, words:", "checkout phone")
dock = swap(dock, "parse: parseEmail, words:", "parse: parseEmail, dictation: true, partial: emailPartial, words:", "checkout email")
dock = swap(dock, "parse: parseAddress, optional: true,", "parse: parseAddress, dictation: true, optional: true,", "checkout address")
a = dock.find("// getOpts() -> { fields, onValue(key, value), onDone() }\nexport function createFormGuide")
if a < 0:
    sys.exit("STOP: createFormGuide not found (nothing was changed)")
dock = dock[:a] + GUIDE

# ---- pageform.js ----
pf = swap(pf, 'import { parsePhone, parseEmail, parseName, parseCity, parseAddress, parseDigits } from "./voicecmd";',
          'import { parsePhone, parseEmail, parseName, parseCity, parseAddress, parseDigits, phonePartial, emailPartial, digitsPartial } from "./voicecmd";', "pageform import")
pf = swap(pf, "parse: parseEmail };", "parse: parseEmail, dictation: true, partial: emailPartial };", "pf email")
pf = swap(pf, "parse: phoneParser(el, label) };", "parse: phoneParser(el, label), dictation: true, partial: phonePartial };", "pf phone")
pf = swap(pf, "parse: (t) => parseDigits(t, 4, 8) };", "parse: (t) => parseDigits(t, 4, 8), dictation: true, partial: (t) => digitsPartial(t, 4) };", "pf otp")
pf = swap(pf, "parse: (t) => parseDigits(t, 5, 6) };", "parse: (t) => parseDigits(t, 5, 6), dictation: true, partial: (t) => digitsPartial(t, 6) };", "pf pin")
pf = swap(pf, "parse: parseAddress };", "parse: parseAddress, dictation: true };", "pf address")

css = css.rstrip("\n") + "\n" + CSS_ADD

open(CMD, "w", encoding="utf-8").write(cmd)
open(DOCK, "w", encoding="utf-8").write(dock)
open(PF, "w", encoding="utf-8").write(pf)
open(CSS, "w", encoding="utf-8").write(css)
print("OK: no bubble over the form, numbers and emails heard in full")