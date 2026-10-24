// A small floating mic for the Detail and Checkout pages.
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
