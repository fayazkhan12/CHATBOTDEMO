// Reading the assistant's reply aloud, in the language it is written in.
//
// The reply follows the language of the visitor (Hindi in Devanagari, Tamil in Tamil script, English...).
// A voice has to match that script: an English voice reading Tamil is silent or garbage. When the device
// has no voice for the language, nothing is spoken (speak() returns false) and the text stays on screen.

const SCRIPTS = [
  ["hi", /[ऀ-ॿ]/g],   // Devanagari: Hindi, Marathi
  ["bn", /[ঀ-৿]/g],
  ["pa", /[਀-੿]/g],
  ["gu", /[઀-૿]/g],
  ["or", /[଀-୿]/g],
  ["ta", /[஀-௿]/g],
  ["te", /[ఀ-౿]/g],
  ["kn", /[ಀ-೿]/g],
  ["ml", /[ഀ-ൿ]/g],
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

const rank = (v) => (/google|neural|natural|online/i.test(v.name || "") ? 0 : 1);

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

// Speaks `text`. Returns false (and calls onEnd(false) at once) when nothing can be spoken: no speech support, empty text,
// or a language this device has no voice for. onEnd(spoken) is called once, even if the browser forgets to report the end.
export function speak(text, { onEnd, preferred } = {}) {
  let ended = false;
  let guard = null;
  const finish = (spoken) => {
    if (ended) return;
    ended = true;
    clearTimeout(guard);
    if (onEnd) onEnd(spoken !== false);
  };
  const body = String(text || "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  if (!canSpeak() || !body) { finish(false); return false; }
  const synth = window.speechSynthesis;
  const lang = replyLanguage(body, preferred);
  let voices = [];
  try { voices = synth.getVoices() || []; } catch (e) { voices = []; }
  const voice = lang.base === "en"
    ? pickVoice(voices, "en-IN", "en-GB", "en-US", "en")
    : pickVoice(voices, lang.tag, lang.base);
  if (lang.base !== "en" && voices.length && !voice) { finish(false); return false; }   // no voice for this language on this device
  try {
    synth.cancel();
    const u = new window.SpeechSynthesisUtterance(body);
    if (voice) u.voice = voice;
    u.lang = voice ? voice.lang : lang.tag;
    u.rate = 0.98;
    u.pitch = 1.02;
    u.volume = 1;
    u.onend = () => finish(true);
    u.onerror = () => finish(false);
    guard = setTimeout(() => finish(true), 3000 + body.length * 90);
    synth.speak(u);
    return true;
  } catch (e) {
    finish(false);
    return false;
  }
}

export function stopSpeaking() {
  try { if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) { /* ignore */ }
}
