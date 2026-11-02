// The natural voice: asks the server for a spoken sentence (a WAV file made by a speech model) and plays it.
//
// A lot can go wrong here (no key on the server, no quota, a slow network, a browser that blocks sound until the visitor taps).
// Every failure ends the same way: the functions answer "no" and the caller speaks with the device's own voice instead.
// Nothing in this file throws to its caller. No imports on purpose: it is tested on its own (test_voice_unit.mjs).

const base = () => `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const state = { off: false, until: 0, blocked: false };       // off: not set up on the server; until: paused; blocked: needs a tap first
const GENDER_KEY = "dw_voice_gender";
const MODE_KEY = "dw_voice_mode";

export function getVoiceGender() {
  try { return window.localStorage.getItem(GENDER_KEY) === "male" ? "male" : "female"; } catch (e) { return "female"; }
}
export function setVoiceGender(g) {
  try { window.localStorage.setItem(GENDER_KEY, g === "male" ? "male" : "female"); } catch (e) { /* ignore */ }
}

// "natural": the speech model (the best sound, but a few seconds to make each sentence); "quick": the device's own voice at once.
export function getVoiceMode() {
  try { return window.localStorage.getItem(MODE_KEY) === "quick" ? "quick" : "natural"; } catch (e) { return "natural"; }
}
export function setVoiceMode(m) {
  try { window.localStorage.setItem(MODE_KEY, m === "quick" ? "quick" : "natural"); } catch (e) { /* ignore */ }
}

function pause(ms) { state.until = Math.max(state.until, Date.now() + ms); }

export function naturalVoiceAvailable() {
  if (typeof window === "undefined" || typeof window.Audio !== "function" || typeof window.fetch !== "function") return false;
  if (typeof window.URL === "undefined" || typeof window.URL.createObjectURL !== "function") return false;
  return !state.off && !state.blocked && Date.now() >= state.until && getVoiceMode() === "natural";
}

export function naturalVoiceState() { return { ...state }; }
export function resetNaturalVoice() { state.off = false; state.until = 0; state.blocked = false; clips.clear(); inflight.clear(); }

// ---- finished sentences are kept for a while, so a line that comes again (a retry, a prompt) is instant
const clips = new Map();
const clipKey = (text, lang, gender) => `${gender}|${lang}|${text}`;
function remember(key, blob) {
  clips.delete(key);
  clips.set(key, blob);
  while (clips.size > 24) clips.delete(clips.keys().next().value);
}
export function cachedClip(text, { lang = "", gender = "female" } = {}) {
  return clips.get(clipKey(text, lang, gender)) || null;
}

// Clips being made for a line that is not needed yet (see prefetchSpeech): whoever needs the same line next joins the request.
const inflight = new Map();

// A WAV file of the sentence, or null. `timeoutMs`: how long to wait before giving the device voice a turn.
// `shared`: the request may be joined by the next caller (for a line fetched ahead of time).
export function fetchClip(text, opts = {}) {
  const key = clipKey(text, opts.lang || "", opts.gender || "female");
  const hit = clips.get(key);
  if (hit) return Promise.resolve(hit);
  const pending = inflight.get(key);
  if (pending) return pending;
  const p = requestClip(text, key, opts);
  if (opts.shared) {
    inflight.set(key, p);
    p.then(() => { if (inflight.get(key) === p) inflight.delete(key); });
  }
  return p;
}

async function requestClip(text, key, { lang = "", gender = "female", timeoutMs = 10000, signal } = {}) {
  if (!naturalVoiceAvailable() || (signal && signal.aborted)) return null;
  const ctrl = new window.AbortController();
  const onAbort = () => ctrl.abort();
  if (signal) signal.addEventListener("abort", onAbort);
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const resp = await window.fetch(`${base()}/voice/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice: gender, lang }),
      signal: ctrl.signal,
    });
    if (resp.status === 200) {
      const blob = await resp.blob();
      if (blob && blob.size > 100) { remember(key, blob); return blob; }
      return null;
    }
    if (resp.status === 503) {
      let d = {};
      try { d = ((await resp.json()) || {}).detail || {}; } catch (e) { /* no details */ }
      if (d.why === "off") state.off = true;
      else pause(Math.min(900, Math.max(5, Number(d.retry) || 30)) * 1000);
    } else if (resp.status === 404 || resp.status === 405) {
      state.off = true;                    // an older server without this feature
    } else if (resp.status === 429) {
      pause(15000);
    } else if (resp.status !== 400 && resp.status !== 422) {
      pause(15000);                        // 5xx, a proxy waking up...
    }
    return null;
  } catch (e) {
    if (!(signal && signal.aborted)) pause(20000);      // slow or no network: the device voice for a while
    return null;
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onAbort);
  }
}

// ---- one audio element for everything: once a tap has let it play, it may play again without a tap (iOS, Safari)
let el = null;
let playing = null;
let unlocked = false;

function audioEl() {
  if (el) return el;
  if (typeof window === "undefined" || typeof window.Audio !== "function") return null;
  try { el = new window.Audio(); el.preload = "auto"; } catch (e) { el = null; }
  return el;
}

function silentWav() {
  const n = 400;
  const buf = new ArrayBuffer(44 + n);
  const v = new DataView(buf);
  const w = (o, s) => { for (let i = 0; i < s.length; i += 1) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + n, true); w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, 8000, true); v.setUint32(28, 8000, true); v.setUint16(32, 1, true); v.setUint16(34, 8, true);
  w(36, "data"); v.setUint32(40, n, true);
  for (let i = 0; i < n; i += 1) v.setUint8(44 + i, 128);
  return new window.Blob([buf], { type: "audio/wav" });
}

// Call this from a tap (the mic button): the browser then lets the voice talk later, when nobody is tapping.
export function unlockAudio() {
  state.blocked = false;
  const a = audioEl();
  if (!a || unlocked || playing) return;
  try {
    const url = window.URL.createObjectURL(silentWav());
    const free = () => { try { window.URL.revokeObjectURL(url); } catch (e) { /* ignore */ } };
    a.src = url;
    const p = a.play();
    if (p && typeof p.then === "function") p.then(() => { unlocked = true; free(); }, free);
    else { unlocked = true; free(); }
  } catch (e) { /* ignore */ }
}

export function stopPlayback() {
  if (playing) playing.stop();
}

// Plays a WAV. onStart() when the sound really begins (a browser may refuse it), onEnd(true) when it finished, onEnd(false) when it
// was cut short or could not play. Returns { stop() } or null.
export function playClip(blob, { onEnd, onStart } = {}) {
  const a = audioEl();
  if (!a || !blob) { if (onEnd) onEnd(false); return null; }
  stopPlayback();
  let url = null;
  let done = false;
  let guard = null;
  const handle = { stop() { finish(false); } };
  function finish(ok) {
    if (done) return;
    done = true;
    clearTimeout(guard);
    a.onended = null; a.onerror = null; a.onloadedmetadata = null;
    try { a.pause(); } catch (e) { /* ignore */ }
    if (url) { try { window.URL.revokeObjectURL(url); } catch (e) { /* ignore */ } }
    if (playing === handle) playing = null;
    if (onEnd) onEnd(ok);
  }
  playing = handle;
  try {
    url = window.URL.createObjectURL(blob);
    a.onended = () => finish(true);
    a.onerror = () => finish(false);
    a.onloadedmetadata = () => {
      if (Number.isFinite(a.duration)) { clearTimeout(guard); guard = setTimeout(() => finish(true), a.duration * 1000 + 2500); }
    };
    a.src = url;
    guard = setTimeout(() => finish(false), 20000);       // it never started
    const began = () => {
      if (done || !onStart) return;
      try { onStart(); } catch (e) { /* the caller's problem */ }
    };
    const refused = (e) => {
      if (e && e.name === "NotAllowedError") state.blocked = true;        // the browser wants a tap first
      finish(false);
    };
    const p = a.play();
    if (p && typeof p.then === "function") p.then(began, refused);
    else began();
  } catch (e) {
    finish(false);
  }
  return handle;
}
