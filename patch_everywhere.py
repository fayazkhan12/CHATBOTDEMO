import os, re, sys, json

CMD_ADD = r'''
// ---- app-wide voice commands ----

const wordsOf = (text) => normalizeWords(text).split(" ").filter(Boolean);
const hasAny = (text, list) => { const w = wordsOf(text); return w.some((x) => list.includes(x)); };

// "reserve" said on purpose (not just "yes" or "ok")
export function isStrongReserve(text) {
  return hasAny(text, ["reserve", "book", "booking", "bukk", "confirm", "बुक", "रिज़र्व", "रिजर्व", "कन्फर्म"]);
}
export function isHomeIntent(text) {
  return hasAny(text, ["home", "ghar", "chat", "start", "shuru", "होम", "घर"]);
}
export function isBookingsIntent(text) {
  return hasAny(text, ["booking", "bookings", "trips", "trip", "बुकिंग"]);
}
export function isLoginIntent(text) {
  return hasAny(text, ["login", "signin", "sign", "log", "लॉगिन"]);
}
'''
VOICEDOCK = r'''// A small floating mic for the Detail and Checkout pages.
// Plain DOM so it needs no changes to the page markup.
import { createVoiceEngine, describeStop, pickDefaultLang } from "./voice";
import { normalizeWords, isSkip, parseName, parsePhone, parseEmail, parseCity, parseAddress } from "./voicecmd";

const FLOW_KEY = "dw_voice_flow";

// Set when the user got here by voice, so the next page starts listening by itself.
// markVoiceFlow("reserve") also tells the Detail page to reserve by itself.
export function markVoiceFlow(mode) {
  try {
    window.sessionStorage.setItem(FLOW_KEY, mode === "reserve" ? `reserve@${Date.now()}` : "1");
  } catch (e) { /* ignore */ }
}
function peekVoiceFlow() {
  try { return window.sessionStorage.getItem(FLOW_KEY) === "1"; } catch (e) { return false; }
}
// True once, and only if the reserve request is fresh (so an old one can never book by surprise).
export function takeReserveFlow() {
  try {
    const v = window.sessionStorage.getItem(FLOW_KEY) || "";
    if (v.indexOf("reserve@") !== 0) return false;
    window.sessionStorage.removeItem(FLOW_KEY);
    return Date.now() - Number(v.slice(8)) < 30000;
  } catch (e) { return false; }
}
function clearVoiceFlow() {
  try { window.sessionStorage.removeItem(FLOW_KEY); } catch (e) { /* ignore */ }
}

const MIC_SVG = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v4"/></svg>';

// getConfig() -> { onStart(), onText(text), maxTurns }
// A turn is { say?: string, listen?: boolean, lang?: string }.
function createDock(getConfig) {

  const root = document.createElement("div");
  root.className = "vdock";
  root.setAttribute("role", "region");
  root.setAttribute("aria-label", "Voice assistant");
  const note = document.createElement("div");
  note.className = "vdock-note";
  note.setAttribute("role", "status");
  note.hidden = true;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "vdock-btn";
  btn.setAttribute("aria-label", "Voice assistant: tap and speak");
  btn.setAttribute("aria-pressed", "false");
  btn.innerHTML = MIC_SVG;
  root.appendChild(note);
  root.appendChild(btn);
  document.body.appendChild(root);

  let alive = true;
  let active = false;
  let engine = null;
  let turns = 0;
  let runId = 0;
  let timer = null;
  let speakTimer = null;

  const setNote = (t) => { note.textContent = t || ""; note.hidden = !t; };
  const setListening = (on) => {
    btn.classList.toggle("listening", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  };

  function stopEngine() {
    if (engine) { const e = engine; engine = null; e.destroy(); }
    setListening(false);
  }

  function stopAll(msg) {
    runId += 1;
    active = false;
    clearTimeout(timer);
    clearTimeout(speakTimer);
    try { if (window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) { /* ignore */ }
    stopEngine();
    setNote(msg || "");
  }

  function say(text, cb, id) {
    let done = false;
    const fin = () => {
      if (done) return;
      done = true;
      clearTimeout(speakTimer);
      if (alive && id === runId) cb();
    };
    try {
      const synth = window.speechSynthesis;
      if (!synth || typeof window.SpeechSynthesisUtterance === "undefined") {
        speakTimer = setTimeout(fin, 900);
        return;
      }
      synth.cancel();
      const u = new window.SpeechSynthesisUtterance(text);
      u.lang = "en-IN";
      u.onend = fin;
      u.onerror = fin;
      speakTimer = setTimeout(fin, 2500 + text.length * 85);
      synth.speak(u);
    } catch (e) {
      speakTimer = setTimeout(fin, 900);
    }
  }

  function runTurn(turn, id) {
    if (!alive || id !== runId) return;
    if (!turn) { active = false; return; }
    const next = () => {
      if (turn.listen) timer = setTimeout(() => listen(turn.lang, id), 450);
      else active = false;
    };
    if (turn.say) { setNote(turn.say); say(turn.say, next, id); } else next();
  }

  function listen(lang, id) {
    if (!alive || id !== runId || engine) return;
    const cfg = getConfig() || {};
    if (turns >= (cfg.maxTurns || 14)) {
      active = false;
      setNote("Voice session ended. Tap the mic to continue.");
      return;
    }
    turns += 1;
    let eng = null;
    eng = createVoiceEngine({
      lang: lang || pickDefaultLang(),
      once: true,
      idleMs: 12000,
      onInterim: (t) => setNote(t ? `\u201c${t}\u201d` : "Listening..."),
      onFinal: (text) => {
        const c = getConfig() || {};
        let turn = null;
        try {
          turn = c.onText ? c.onText(text) : null;
        } catch (e) {
          turn = { say: "Something went wrong. Please try again.", listen: false };
        }
        runTurn(turn, id);
      },
      onStop: (reason) => {
        if (engine !== eng) return;
        engine = null;
        setListening(false);
        if (reason === "idle") { active = false; setNote("I did not hear anything. Tap the mic to continue."); }
        else if (reason && reason !== "done") { active = false; setNote(describeStop(reason)); }
      },
    });
    if (!eng) { active = false; setNote(describeStop("unsupported")); return; }
    engine = eng;
    setListening(true);
    setNote("Listening...");
    eng.start();
  }

  function start() {
    stopAll("");
    const id = runId;
    active = true;
    turns = 0;
    const cfg = getConfig() || {};
    let turn = { listen: true };
    try { if (cfg.onStart) turn = cfg.onStart(); } catch (e) { /* keep default */ }
    runTurn(turn, id);
  }

  btn.addEventListener("click", () => { if (active) stopAll(""); else start(); });

  let flowTimer = null;
  // Called whenever the page (or its voice owner) changes.
  function changed() {
    stopAll("");
    clearTimeout(flowTimer);
    if (peekVoiceFlow()) {
      flowTimer = setTimeout(() => { if (alive) { clearVoiceFlow(); start(); } }, 800);
    }
  }

  return {
    start,
    changed,
    destroy() {
      alive = false;
      clearTimeout(flowTimer);
      stopAll("");
      if (root.parentNode) root.parentNode.removeChild(root);
    },
  };
}

// One shared dock for the whole app. A page can register its own commands with a higher
// priority; the app-wide commands (priority 0) are used when no page has its own.
const owners = [];
let sharedDock = null;

function topConfig() {
  let best = null;
  for (const o of owners) if (!best || o.priority >= best.priority) best = o;
  return best ? best.getConfig() : null;
}

export function mountDock(getConfig, priority = 1) {
  if (typeof document === "undefined") return { destroy() {}, start() {} };
  const owner = { getConfig, priority };
  owners.push(owner);
  if (!sharedDock) sharedDock = createDock(topConfig);
  sharedDock.changed();
  return {
    start() { if (sharedDock) sharedDock.start(); },
    destroy() {
      const i = owners.indexOf(owner);
      if (i >= 0) owners.splice(i, 1);
      if (!sharedDock) return;
      if (!owners.length) { sharedDock.destroy(); sharedDock = null; } else sharedDock.changed();
    },
  };
}

export function routeChanged() {
  if (sharedDock) sharedDock.changed();
}

// ---- guided form filling ----

export const CHECKOUT_VOICE_FIELDS = [
  { key: "name", ask: "What is your full name?", retry: "Sorry, please say your full name again.", parse: parseName, words: ["name", "naam"] },
  { key: "phone", ask: "Your mobile number, digit by digit.", retry: "I could not get a valid 10 digit mobile number. Please say it again, digit by digit.", parse: parsePhone, words: ["phone", "mobile", "number", "contact"] },
  { key: "email", ask: "Your email address. Say at the rate and dot where needed.", retry: "I could not get a valid email. Please say it again, for example name at the rate gmail dot com.", parse: parseEmail, words: ["email", "mail"] },
  { key: "city", ask: "Which city? Say skip to skip.", retry: "Please say the city name, or say skip.", parse: parseCity, optional: true, words: ["city", "shehar"] },
  { key: "address", ask: "Your address? Say skip to skip.", retry: "Please say the address, or say skip.", parse: parseAddress, optional: true, words: ["address", "pata"] },
];

export function highlightPay() {
  try {
    const b = document.querySelector('[data-testid="pay-btn"]');
    if (!b) return;
    b.classList.add("pay-attn");
    if (b.scrollIntoView) b.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => b.classList.remove("pay-attn"), 9000);
  } catch (e) { /* ignore */ }
}

// getOpts() -> { fields, onValue(key, value), onDone() }
export function createFormGuide(getOpts) {
  let idx = 0;
  let fails = 0;
  const T = (say, listen) => ({ say, listen, lang: "en-IN" });
  const fields = () => getOpts().fields;

  function advance(got) {
    const f = fields();
    if (idx >= f.length) {
      const o = getOpts();
      if (o.onDone) o.onDone();
      return T("All details are filled. Please check the screen and tap Pay.", false);
    }
    return T(`${got ? "Got it. " : ""}${f[idx].ask}`, true);
  }

  return {
    start() {
      const f = fields();
      if (idx >= f.length) return T("All details are filled. Say change name, phone or email to edit, or tap Pay.", true);
      return T(`${idx === 0 ? "Let us fill your details. " : ""}${f[idx].ask}`, true);
    },
    handle(text) {
      const raw = String(text || "");
      const t = normalizeWords(raw);
      const f = fields();
      if (/\b(stop|cancel|exit|quit|band|ruko)\b/.test(t)) return T("Okay, I stopped. Tap the mic to continue.", false);
      if (/\b(pay|payment|paisa|bhugtan)\b/.test(t)) return T("Please tap the Pay button yourself when you are ready.", false);
      if (/\b(change|edit|correct|badlo|badal|galat|wrong)\b/.test(t)) {
        const j = f.findIndex((x) => x.words.some((w) => t.split(" ").includes(w)));
        if (j >= 0) { idx = j; fails = 0; return T(f[j].ask, true); }
      }
      if (/\b(repeat|again|dobara|once more)\b/.test(t) && idx < f.length) return T(f[idx].ask, true);
      if (idx >= f.length) return T("All details are filled. Say change name, phone or email to edit, or tap Pay.", false);
      const cur = f[idx];
      if (cur.optional && isSkip(t)) { idx += 1; fails = 0; return advance(false); }
      const v = cur.parse(raw);
      if (v == null) {
        fails += 1;
        if (fails >= 3) {
          fails = 0;
          idx += 1;
          if (idx >= f.length) return T("I could not hear that. Please type it, then tap Pay.", false);
          return T("I am having trouble hearing that. Please type this one, then tap the mic to continue.", false);
        }
        return T(cur.retry, true);
      }
      getOpts().onValue(cur.key, v);
      idx += 1;
      fails = 0;
      return advance(true);
    },
  };
}
'''
USEDOCK = r'''import { useEffect, useRef } from "react";
import { mountDock, createFormGuide } from "./voicedock";

export { CHECKOUT_VOICE_FIELDS, highlightPay, markVoiceFlow, takeReserveFlow, routeChanged } from "./voicedock";

// config: { onStart(), onText(text), maxTurns } - read fresh on every turn.
// priority: pages use the default (1); the app-wide dock uses 0.
export function useVoiceDock(config, priority = 1) {
  const ref = useRef(config);
  ref.current = config;
  useEffect(() => {
    const dock = mountDock(() => ref.current, priority);
    return () => dock.destroy();
  }, [priority]);
}

// options: { fields, onValue(key, value), onDone() }
export function useFormGuide(options) {
  const optsRef = useRef(options);
  optsRef.current = options;
  const guide = useRef(null);
  if (!guide.current) guide.current = createFormGuide(() => optsRef.current);
  return guide.current;
}
'''
GLOBAL = r'''import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useVoiceDock, routeChanged } from "./useVoiceDock";
import { isBackIntent, isHomeIntent, isBookingsIntent, isLoginIntent } from "./voicecmd";

// Paths found in App.js when this was installed.
const PATHS = __PATHS__;

function AppDock() {
  const navigate = useNavigate();
  const go = (path, msg) => {
    if (!path) return { say: "That page is not available here.", listen: true };
    navigate(path);
    return { say: msg, listen: false };
  };
  useVoiceDock({
    maxTurns: 4,
    onStart: () => ({ say: "Say home, my bookings, login or back. You can also just use the screen.", listen: true }),
    onText: (said) => {
      if (isBackIntent(said)) { navigate(-1); return { listen: false }; }
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

ROOT = "frontend/src"
LIB = ROOT + "/lib/"
APP = ROOT + "/App.js"
HOME = ROOT + "/pages/Home.jsx"
DETAIL = ROOT + "/pages/Detail.jsx"
CMD = LIB + "voicecmd.js"
DOCK = LIB + "voicedock.js"
for p in (APP, HOME, DETAIL, CMD, DOCK, LIB + "useVoiceDock.js"):
    if not os.path.exists(p):
        sys.exit("STOP: " + p + " is missing. Run this from the repo root (D:\\projects\\destinoway-chatbot-demo).")


def read(p):
    return open(p, encoding="utf-8").read()


app, home, detail, cmd, dock = read(APP), read(HOME), read(DETAIL), read(CMD), read(DOCK)
if "GlobalVoice" in app or "isStrongReserve" in cmd:
    sys.exit("Already applied. Nothing to do.")
if "export function mountDock" not in dock or "createFormGuide" not in dock:
    sys.exit("STOP: voicedock.js is not the expected version (nothing was changed)")


def swap(text, old, new, label):
    if text.count(old) != 1:
        sys.exit("STOP: " + label + " not found (nothing was changed)")
    return text.replace(old, new, 1)


# ---- App.js: find the routes and mount the app-wide mic inside the router ----
paths = re.findall(r'path=["\']([^"\']+)["\']', app)
home_path = "/"
m = re.search(r'path=["\']([^"\']+)["\'][^>]*element=\{\s*<Home\b', app)
if m:
    home_path = m.group(1)
bookings = next((p for p in paths if "booking" in p.lower() and ":" not in p and "*" not in p), None)
login = next((p for p in paths if "login" in p.lower() and ":" not in p), None)
found = {"home": home_path, "bookings": bookings, "login": login}

i = app.find("<Routes")
if i < 0:
    sys.exit("STOP: <Routes not found in App.js (nothing was changed)")
if "Router" not in app[:i]:
    sys.exit("STOP: no Router found before <Routes in App.js (nothing was changed)")
line_start = app.rfind("\n", 0, i) + 1
indent = app[line_start:i]
if indent.strip():
    indent = ""
app = app[:line_start] + indent + "<GlobalVoice />\n" + app[line_start:]
imports = list(re.finditer(r'^import .*$', app, re.M))
if not imports:
    sys.exit("STOP: no imports in App.js (nothing was changed)")
last = imports[-1]
app = app[:last.end()] + '\nimport GlobalVoice from "./lib/GlobalVoice";' + app[last.end():]

# ---- Home.jsx: "pehla wala reserve karo" opens the hotel and reserves it ----
home = swap(home, 'import { resolvePick, hasPickIntent } from "../lib/voicecmd";',
            'import { resolvePick, hasPickIntent, isStrongReserve } from "../lib/voicecmd";', "voicecmd import in Home.jsx")
home = swap(home, "    if (pick) {\n      markVoiceFlow();\n      openCardRef.current(pick);",
            '    if (pick) {\n      markVoiceFlow(isStrongReserve(said) ? "reserve" : undefined);\n      openCardRef.current(pick);', "pick block in Home.jsx")

# ---- Detail.jsx: reserve by itself when the user said "reserve" in chat ----
detail = swap(detail, 'import { useVoiceDock, markVoiceFlow } from "../lib/useVoiceDock";',
              'import { useVoiceDock, markVoiceFlow, takeReserveFlow } from "../lib/useVoiceDock";', "useVoiceDock import in Detail.jsx")
rm = re.search(r'import \{([^}]*)\} from "react";', detail)
if not rm:
    sys.exit("STOP: react import not found in Detail.jsx (nothing was changed)")
if "useEffect" not in rm.group(1):
    detail = detail.replace(rm.group(0), 'import {' + rm.group(1).rstrip() + ', useEffect } from "react";', 1)
effect = (
    "  useEffect(() => {\n"
    "    if (!item) return;\n"
    "    if (takeReserveFlow()) { markVoiceFlow(); book(); }\n"
    "    // eslint-disable-next-line react-hooks/exhaustive-deps\n"
    "  }, [item]);\n\n"
)
detail = swap(detail, "  useVoiceDock({", effect + "  useVoiceDock({", "useVoiceDock call in Detail.jsx")

# ---- voicecmd.js: new commands ----
cmd = cmd.rstrip("\n") + "\n" + CMD_ADD

# ---- write everything (only reached when every check passed) ----
open(LIB + "voicedock.js", "w", encoding="utf-8").write(VOICEDOCK)
open(LIB + "useVoiceDock.js", "w", encoding="utf-8").write(USEDOCK)
open(LIB + "GlobalVoice.jsx", "w", encoding="utf-8").write(GLOBAL.replace("__PATHS__", json.dumps(found)))
open(CMD, "w", encoding="utf-8").write(cmd)
open(HOME, "w", encoding="utf-8").write(home)
open(DETAIL, "w", encoding="utf-8").write(detail)
open(APP, "w", encoding="utf-8").write(app)
print("OK: voice on every page + reserve by voice from chat")
print("Pages found:", found)