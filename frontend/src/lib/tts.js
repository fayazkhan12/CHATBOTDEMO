// Reading the assistant's words aloud.
//
// Two voices: a natural one (a speech model on the server, see neuralvoice.js) and the device's own (the browser's speechSynthesis).
// speak() tries the natural voice and falls back to the device voice sentence by sentence, so a quota, a slow network or a blocked
// sound never leaves the visitor in silence. The text is first rewritten the way a person would say it (speech.js).
//
// The reply follows the language of the visitor (Hindi in Devanagari, Tamil in Tamil script, English...). A device voice has to
// match that script: an English voice reading Tamil is silent or garbage. When the device has no voice for the language, nothing
// is spoken (speak() returns false) and the text stays on screen.
import { prepareSpeech, splitForSpeech } from "./speech.js";
import { naturalVoiceAvailable, fetchClip, cachedClip, playClip, stopPlayback, getVoiceGender } from "./neuralvoice.js";

export { unlockAudio, getVoiceGender, setVoiceGender, naturalVoiceAvailable } from "./neuralvoice.js";

const SCRIPTS = [
  ["hi", /[\u0900-\u097F]/g],   // Devanagari: Hindi, Marathi
  ["bn", /[\u0980-\u09FF]/g],
  ["pa", /[\u0A00-\u0A7F]/g],
  ["gu", /[\u0A80-\u0AFF]/g],
  ["or", /[\u0B00-\u0B7F]/g],
  ["ta", /[\u0B80-\u0BFF]/g],
  ["te", /[\u0C00-\u0C7F]/g],
  ["kn", /[\u0C80-\u0CFF]/g],
  ["ml", /[\u0D00-\u0D7F]/g],
];

const norm = (l) => String(l || "").replace("_", "-").toLowerCase();

// The language a reply is written in: { base: "hi", tag: "hi-IN" }. `preferred` is the visitor's voice language
// (for example "mr-IN"), used to tell Marathi from Hindi because both are written in Devanagari.
export function replyLanguage(text, preferred) {
  const t = String(text || "");
  const latin = (t.match(/[A-Za-z]/g) || []).length;
  let best = null;
  let bestCount = 0;
  for (const [base, rx] of SCRIPTS) {
    const n = (t.match(rx) || []).length;
    if (n > bestCount) { best = base; bestCount = n; }
  }
  if (!best || bestCount <= latin) return { base: "en", tag: "en-IN" };
  if (best === "hi" && norm(preferred).startsWith("mr")) return { base: "mr", tag: "mr-IN" };
  return { base: best, tag: `${best}-IN` };
}

// ---- which installed voice
// Newer "natural" / "online" / Google voices sound like a person; the old desktop ones (David, Zira, Heera...) and the
// novelty voices of Apple devices sound like a machine.
const OLD_DESKTOP = /microsoft (david|zira|mark|hazel|james|george|susan|richard|catherine|heera|hemant|kalpana|ravi|sean|linda)\b/i;
const NOVELTY = /espeak|compact|festival|mbrola|albert|bad news|bahh|bells|boing|bubbles|cellos|deranged|good news|hysterical|junior|pipe organ|trinoids|whisper|zarvox/i;

function score(v) {
  const n = `${v.name || ""} ${v.voiceURI || ""}`;
  let s = 0;
  if (/natural|neural/i.test(n)) s += 10;
  if (/online/i.test(n)) s += 6;
  if (/google/i.test(n)) s += 5;
  if (/premium|enhanced/i.test(n)) s += 4;
  if (v.localService === false) s += 2;
  if (OLD_DESKTOP.test(n) && !/natural|online/i.test(n)) s -= 4;
  if (NOVELTY.test(n)) s -= 10;
  return s;
}
const rank = (v) => -score(v);

// The best installed voice for a language tag, or null. Several tags can be given in order of preference (English).
export function pickVoice(voices, ...tags) {
  const list = Array.isArray(voices) ? voices : [];
  for (const tag of tags) {
    const want = norm(tag);
    const exact = list.filter((v) => norm(v.lang) === want);
    if (exact.length) return [...exact].sort((a, b) => rank(a) - rank(b))[0];
  }
  for (const tag of tags) {
    const base = norm(tag).split("-")[0];
    const family = list.filter((v) => norm(v.lang).split("-")[0] === base);
    if (family.length) return [...family].sort((a, b) => rank(a) - rank(b))[0];
  }
  return null;
}

export function canSpeak() {
  return typeof window !== "undefined" && "speechSynthesis" in window && typeof window.SpeechSynthesisUtterance !== "undefined";
}

function deviceCancel() {
  try { if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) { /* ignore */ }
}

// ---- what is being said right now
let current = null;      // the speech in progress: { cancel(), ended }
let engine = "";         // "natural" | "device" | "" (nothing spoken yet)
const GAP_MS = 140;      // the breath between two sentences

export function voiceEngine() { return engine; }

// Speaks the sentences one after the other with the device's own voice. Returns false (after finish(false)) when it can not.
function runDevice(chunks, lang, preferred, me, finish, started) {
  if (!canSpeak()) { finish(false); return false; }
  const synth = window.speechSynthesis;
  let voices = [];
  try { voices = synth.getVoices() || []; } catch (e) { voices = []; }
  const voice = lang.base === "en"
    ? pickVoice(voices, "en-IN", "en-GB", "en-US", "en")
    : pickVoice(voices, lang.tag, lang.base);
  if (lang.base !== "en" && voices.length && !voice) { finish(false); return false; }   // no voice for this language on this device
  let i = 0;
  const next = () => {
    if (me.dead) return;
    if (i >= chunks.length) { finish(true); return; }
    const piece = chunks[i];
    let moved = false;
    const advance = (ok) => {
      if (moved || me.dead) return;
      moved = true;
      clearTimeout(me.guard);
      if (!ok) { finish(false); return; }
      i += 1;
      if (i < chunks.length) me.timer = setTimeout(next, GAP_MS); else next();
    };
    try {
      const u = new window.SpeechSynthesisUtterance(piece);
      if (voice) u.voice = voice;
      u.lang = voice ? voice.lang : lang.tag;
      u.rate = lang.base === "en" ? 1 : 0.95;
      u.pitch = 1;
      u.volume = 1;
      u.onend = () => advance(true);
      u.onerror = () => advance(false);
      me.guard = setTimeout(() => advance(true), 2500 + piece.length * 95);     // some browsers forget to say they are done
      if (i === 0) { synth.cancel(); started("device"); }
      synth.speak(u);
    } catch (e) {
      finish(false);
    }
  };
  next();
  return true;
}

// The same with the natural voice. All the sentences are asked for at once, so the next one is ready when the last ends.
// What can not be played is spoken by the device voice instead, from that sentence on.
function runNatural(chunks, lang, preferred, who, me, finish, started) {
  const jobs = [];
  const ensure = (k) => {
    if (k < chunks.length && !jobs[k]) {
      jobs[k] = fetchClip(chunks[k], { lang: preferred || lang.tag, gender: who, timeoutMs: k === 0 ? 10000 : 15000, signal: me.ctrl ? me.ctrl.signal : undefined });
    }
    return jobs[k];
  };
  let i = 0;
  const device = (from) => { if (!me.dead) runDevice(chunks.slice(from), lang, preferred, me, finish, started); };
  const step = async () => {
    if (me.dead) return;
    if (i >= chunks.length) { finish(true); return; }
    ensure(i + 1);
    ensure(i + 2);
    const clip = await ensure(i);
    if (me.dead) return;
    if (!clip) { device(i); return; }
    await waitForCue();
    if (me.dead) return;
    me.play = playClip(clip, {
      onStart: () => {
        started("natural");              // announced when the sound really begins: a browser may refuse it
        if (i === 0) setTimeout(() => prefetchCues({ preferred, gender: who }), 1200);      // the natural voice works: get the "hmm" clips ready
      },
      onEnd: (ok) => {
        me.play = null;
        if (me.dead) return;
        if (!ok) { device(i); return; }
        i += 1;
        step();
      },
    });
  };
  ensure(0);
  ensure(1);
  step();
}

// Speaks `text`. Returns false (and calls onEnd(false) at once) when nothing can be spoken: empty text, no speech support, or a
// language this device has no voice for. Otherwise true. onEnd(spoken) is called once, even if the browser forgets to report the end.
// onStart(engine) is called when the first sound begins (and again if the other voice has to take over). gender: "female" | "male" (the natural voice; default: the visitor's choice).
export function speak(text, { onEnd, onStart, preferred, gender } = {}) {
  if (current) current.cancel();
  const me = { dead: false, ended: false, play: null, timer: null, guard: null, ctrl: typeof window !== "undefined" && typeof window.AbortController === "function" ? new window.AbortController() : null };
  const finish = (spoken) => {
    if (me.ended) return;
    me.ended = true;
    me.dead = true;
    clearTimeout(me.timer);
    clearTimeout(me.guard);
    if (current === me) current = null;
    if (onEnd) onEnd(spoken !== false);
  };
  me.cancel = () => {
    if (me.ended) return;
    me.dead = true;
    if (me.ctrl) { try { me.ctrl.abort(); } catch (e) { /* ignore */ } }
    if (me.play) me.play.stop();
    deviceCancel();
    finish(false);
  };
  let announced = "";
  const started = (kind) => {
    if (announced === kind) return;     // said once per voice: natural, and device if it has to take over
    announced = kind;
    engine = kind;
    if (onStart) { try { onStart(kind); } catch (e) { /* ignore */ } }
  };

  const body = prepareSpeech(text);
  if (!body) { finish(false); return false; }
  const lang = replyLanguage(body, preferred);
  const chunks = splitForSpeech(body);
  current = me;
  if (naturalVoiceAvailable()) {
    runNatural(chunks, lang, preferred, gender || getVoiceGender(), me, finish, started);
    return true;
  }
  return runDevice(chunks, lang, preferred, me, finish, started);
}

export function stopSpeaking() {
  if (current) current.cancel();
  if (cue.playing) stopPlayback();
  deviceCancel();
}

// ---- a short "hmm, one second" while a slow answer is on its way ----
// People fill a pause with a word; a silent phone line makes you wonder if anyone is there. The cue is played only when the
// natural voice is on and the clip is ready (fetched after the first natural reply, so no quota is spent while the voice does not work),
// not on every slow answer, and never over speech.
const CUES = {
  en: ["Hmm, one second.", "Okay, let me check.", "Sure, just a moment."],
  hi: ["हम्म, एक सेकंड।", "ठीक है, बस एक मिनट।", "जी, बस एक पल।"],
};
const cueSet = (preferred) => (norm(preferred).startsWith("hi") ? "hi" : "en");
const cueLang = (set) => (set === "hi" ? "hi-IN" : "en-IN");
const cue = { playing: false, done: Promise.resolve(), release: () => {}, last: -1, cool: 0 };

function waitForCue() {
  if (!cue.playing) return Promise.resolve();
  return Promise.race([cue.done, new Promise((resolve) => setTimeout(resolve, 3500))]);
}

const cuesAsked = new Set();
export function prefetchCues({ preferred, gender } = {}) {
  if (!naturalVoiceAvailable()) return;
  const set = cueSet(preferred);
  const who = gender || getVoiceGender();
  CUES[set].forEach((text) => {
    const key = `${who}|${set}|${text}`;
    if (cuesAsked.has(key) || cachedClip(text, { lang: cueLang(set), gender: who })) return;
    cuesAsked.add(key);
    fetchClip(text, { lang: cueLang(set), gender: who, timeoutMs: 15000 }).then((blob) => { if (!blob) cuesAsked.delete(key); });
  });
}

export function playThinkingCue({ preferred, gender } = {}) {
  if (!naturalVoiceAvailable() || cue.playing || (current && !current.ended)) return false;
  if (cue.cool > 0) { cue.cool -= 1; return false; }
  const set = cueSet(preferred);
  const who = gender || getVoiceGender();
  const ready = CUES[set].map((text, i) => ({ i, blob: cachedClip(text, { lang: cueLang(set), gender: who }) })).filter((o) => o.blob && o.i !== cue.last);
  if (!ready.length) return false;
  const pick = ready[Math.floor(Math.random() * ready.length)];
  cue.last = pick.i;
  cue.cool = 2;
  cue.playing = true;
  cue.done = new Promise((resolve) => { cue.release = resolve; });
  playClip(pick.blob, { onEnd: () => { cue.playing = false; cue.release(); } });
  return true;
}
