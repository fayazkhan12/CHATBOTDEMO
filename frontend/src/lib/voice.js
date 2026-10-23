// Hands-free voice input for DestinoWay.
// Wraps the browser SpeechRecognition API: stays on, restarts itself,
// sends a message after a short pause, pauses while the bot speaks.

export const VOICE_LANGS = [
  { code: "en-IN", label: "English" },
  { code: "hi-IN", label: "\u0939\u093f\u0928\u094d\u0926\u0940 \u00b7 Hindi" },
  { code: "pa-IN", label: "\u0a2a\u0a70\u0a1c\u0a3e\u0a2c\u0a40 \u00b7 Punjabi" },
  { code: "gu-IN", label: "\u0a97\u0ac1\u0a9c\u0ab0\u0abe\u0aa4\u0ac0 \u00b7 Gujarati" },
  { code: "mr-IN", label: "\u092e\u0930\u093e\u0920\u0940 \u00b7 Marathi" },
  { code: "bn-IN", label: "\u09ac\u09be\u0982\u09b2\u09be \u00b7 Bengali" },
  { code: "ta-IN", label: "\u0ba4\u0bae\u0bbf\u0bb4\u0bcd \u00b7 Tamil" },
  { code: "te-IN", label: "\u0c24\u0c46\u0c32\u0c41\u0c17\u0c41 \u00b7 Telugu" },
  { code: "kn-IN", label: "\u0c95\u0ca8\u0ccd\u0ca8\u0ca1 \u00b7 Kannada" },
  { code: "ml-IN", label: "\u0d2e\u0d32\u0d2f\u0d3e\u0d33\u0d02 \u00b7 Malayalam" },
];

const LANG_KEY = "dw_voice_lang";

export function pickDefaultLang() {
  try {
    const saved = window.localStorage.getItem(LANG_KEY);
    if (saved && VOICE_LANGS.some((l) => l.code === saved)) return saved;
  } catch (e) { /* storage unavailable */ }
  try {
    const prefix = String(window.navigator.language || "").slice(0, 2).toLowerCase();
    const hit = VOICE_LANGS.find((l) => l.code.slice(0, 2) === prefix);
    if (hit) return hit.code;
  } catch (e) { /* ignore */ }
  return "en-IN";
}

export function saveLang(code) {
  try { window.localStorage.setItem(LANG_KEY, code); } catch (e) { /* ignore */ }
}

function getSR() {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

export function voiceSupported() {
  return !!getSR();
}

const STOP_MESSAGES = {
  denied: "Microphone access is blocked. Allow the microphone in your browser settings, or type your message.",
  "no-device": "No microphone was found on this device.",
  network: "Voice recognition lost its connection. Check your internet and try again.",
  idle: "Voice mode paused after a few minutes of silence. Tap the mic to start again.",
  unstable: "Voice input keeps disconnecting on this device. Please type your message, or try Chrome.",
  lang: "This language is not available for voice in this browser. Pick another language.",
  unsupported: "Voice input is not supported in this browser. Please use Chrome or Edge, or type your message.",
};

export function describeStop(reason) {
  return STOP_MESSAGES[reason] || "Voice mode stopped.";
}

// ---- deciding whether a spoken sentence is worth sending ----

const FILLERS = new Set([
  "hmm", "hm", "mm", "um", "umm", "uh", "uhh", "ah", "oh", "er", "huh",
  "haan", "han", "hanji", "accha", "acha", "achha", "theek", "thik", "ok", "okay",
  "yes", "no", "nahi", "nahin", "na", "ha", "so", "and", "the", "a",
]);

// One-word replies that make sense only while a conversation is going on.
const REPLY_WORDS = new Set([
  "yes", "no", "haan", "han", "nahi", "nahin", "ok", "okay", "theek", "thik",
  "confirm", "cancel", "done", "stop", "first", "second", "third", "cheapest",
  "pehla", "dusra", "doosra", "teesra", "sasta", "sabse", "one", "two", "three",
  "ek", "do", "teen",
  "\u0939\u093e\u0901", "\u0939\u093e\u0902", "\u0928\u0939\u0940\u0902", "\u0920\u0940\u0915",
  "\u0913\u0915\u0947", "\u092a\u0939\u0932\u093e", "\u0926\u0942\u0938\u0930\u093e",
  "\u0924\u0940\u0938\u0930\u093e",
  "\u0a39\u0a3e\u0a02", "\u0a28\u0a39\u0a40\u0a02", "\u0a2a\u0a39\u0a3f\u0a32\u0a3e",
  "\u0a26\u0a42\u0a1c\u0a3e", "\u0a24\u0a40\u0a1c\u0a3e",
]);

const GREETINGS = new Set([
  "hello", "hi", "hey", "namaste", "namaskar",
  "\u0928\u092e\u0938\u094d\u0924\u0947",
]);

export function normalizeUtterance(text) {
  return String(text || "")
    .replace(/[\u0964\u0965.,!?;:"']+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// active = a real conversation is already going on (not just the greeting).
export function shouldSendUtterance(text, active) {
  const t = normalizeUtterance(text);
  if (t.length < 2 || t.length > 500) return false;
  const words = t.toLowerCase().split(" ");
  if (words.length === 1) {
    const w = words[0];
    if (GREETINGS.has(w)) return true;
    return !!active && REPLY_WORDS.has(w);
  }
  return !words.every((w) => FILLERS.has(w));
}

// ---- the engine ----

export function createVoiceEngine({
  lang,
  onInterim,
  onFinal,
  onStop,
  silenceMs = 1500,
  idleMs = 120000,
  resumeDelayMs = 600,
}) {
  const SR = getSR();
  if (!SR) return null;

  let curLang = lang || "en-IN";
  let wantOn = false;
  let destroyed = false;
  let pausedExt = false;
  let hidden = false;
  let paused = false;
  let rec = null;
  let seen = 0;
  let base = 0;
  let lastText = "";
  let quickEnds = 0;
  let netErrors = 0;
  let startedAt = 0;
  let silenceTimer = null;
  let idleTimer = null;
  let restartTimer = null;
  let resumeTimer = null;

  const emitInterim = (t) => { try { onInterim && onInterim(t); } catch (e) { /* ignore */ } };

  function clearAll() {
    clearTimeout(silenceTimer);
    clearTimeout(idleTimer);
    clearTimeout(restartTimer);
    clearTimeout(resumeTimer);
  }

  function armIdle() {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => finish("idle"), idleMs);
  }

  function flush() {
    clearTimeout(silenceTimer);
    const t = lastText.trim();
    lastText = "";
    base = seen;
    emitInterim("");
    if (t) {
      try { onFinal && onFinal(t); } catch (e) { /* ignore */ }
    }
  }

  function dropRec() {
    const r = rec;
    rec = null;
    if (r) {
      r.onresult = null; r.onerror = null; r.onend = null;
      try { r.abort(); } catch (e) { /* ignore */ }
    }
  }

  function teardown() {
    destroyed = true;
    wantOn = false;
    clearAll();
    dropRec();
    lastText = "";
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", onVisibility);
  }

  function finish(reason) {
    if (destroyed) return;
    teardown();
    emitInterim("");
    try { onStop && onStop(reason); } catch (e) { /* ignore */ }
  }

  function startRec() {
    if (destroyed || !wantOn || paused || rec) return;
    const r = new SR();
    rec = r;
    r.lang = curLang;
    r.continuous = true;
    r.interimResults = true;
    r.maxAlternatives = 1;
    seen = 0;
    base = 0;

    r.onresult = (e) => {
      if (r !== rec) return;
      netErrors = 0;
      armIdle();
      let text = "";
      for (let i = base; i < e.results.length; i += 1) {
        text += `${e.results[i][0].transcript} `;
      }
      seen = e.results.length;
      lastText = text.trim();
      emitInterim(lastText);
      clearTimeout(silenceTimer);
      if (lastText) silenceTimer = setTimeout(flush, silenceMs);
    };

    r.onerror = (e) => {
      if (r !== rec) return;
      const code = e && e.error;
      if (code === "not-allowed" || code === "service-not-allowed") finish("denied");
      else if (code === "audio-capture") finish("no-device");
      else if (code === "language-not-supported") finish("lang");
      else if (code === "network") {
        netErrors += 1;
        if (netErrors >= 3) finish("network");
      }
      // no-speech / aborted: onend restarts the session
    };

    r.onend = () => {
      if (r !== rec) return;
      rec = null;
      if (lastText) flush();
      if (destroyed || !wantOn || paused) return;
      const lived = Date.now() - startedAt;
      quickEnds = lived < 1000 ? quickEnds + 1 : 0;
      if (quickEnds >= 5) { finish("unstable"); return; }
      restartTimer = setTimeout(startRec, Math.min(250 * (quickEnds + 1), 1500));
    };

    startedAt = Date.now();
    try {
      r.start();
    } catch (e) {
      rec = null;
      restartTimer = setTimeout(startRec, 500);
    }
  }

  function applyPause() {
    if (destroyed) return;
    clearTimeout(resumeTimer);
    const want = pausedExt || hidden;
    if (want) {
      paused = true;
      clearTimeout(silenceTimer);
      lastText = "";
      emitInterim("");
      dropRec();
    } else if (paused) {
      resumeTimer = setTimeout(() => {
        paused = false;
        startRec();
      }, resumeDelayMs);
    }
  }

  function onVisibility() {
    hidden = typeof document !== "undefined" && document.hidden === true;
    applyPause();
  }

  return {
    start() {
      if (destroyed || wantOn) return;
      wantOn = true;
      hidden = typeof document !== "undefined" && document.hidden === true;
      if (typeof document !== "undefined") document.addEventListener("visibilitychange", onVisibility);
      armIdle();
      if (hidden) { paused = true; return; }
      startRec();
    },
    setPaused(p) {
      pausedExt = !!p;
      applyPause();
    },
    setLang(code) {
      if (destroyed || !code || code === curLang) return;
      curLang = code;
      if (rec) {
        if (lastText) flush();
        dropRec();
        quickEnds = 0;
        if (wantOn && !paused) startRec();
      }
    },
    destroy() {
      teardown();
      emitInterim("");
    },
  };
}