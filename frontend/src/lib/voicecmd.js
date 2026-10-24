// Plain-text helpers for voice commands. No React, no browser APIs.

const INDIC_DIGITS = [
  [0x0966, 0x096f], // Devanagari
  [0x0a66, 0x0a6f], // Gurmukhi
];

function asciiDigits(s) {
  let out = "";
  for (const ch of s) {
    const c = ch.codePointAt(0);
    let done = false;
    for (const [lo, hi] of INDIC_DIGITS) {
      if (c >= lo && c <= hi) { out += String(c - lo); done = true; break; }
    }
    if (!done) out += ch;
  }
  return out;
}

// lower case, no punctuation, single spaces. Keeps letters and marks of any script.
export function normalizeWords(text) {
  return asciiDigits(String(text || ""))
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[^\p{L}\p{M}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const DIGIT_WORDS = {
  zero: 0, oh: 0, o: 0, shunya: 0,
  one: 1, ek: 1, two: 2, to: 2, too: 2, do: 2, three: 3, teen: 3,
  four: 4, for: 4, char: 4, chaar: 4, five: 5, paanch: 5, panch: 5,
  six: 6, chhe: 6, chheh: 6, che: 6, seven: 7, saat: 7, sat: 7,
  eight: 8, aath: 8, ath: 8, nine: 9, nau: 9,
  "\u0936\u0942\u0928\u094d\u092f": 0,
  "\u091c\u0940\u0930\u094b": 0,
  "\u091c\u093c\u0940\u0930\u094b": 0,
  "\u090f\u0915": 1,
  "\u0935\u0928": 1,
  "\u0926\u094b": 2,
  "\u091f\u0942": 2,
  "\u0924\u0940\u0928": 3,
  "\u0925\u094d\u0930\u0940": 3,
  "\u091a\u093e\u0930": 4,
  "\u092b\u094b\u0930": 4,
  "\u092a\u093e\u0902\u091a": 5,
  "\u092a\u093e\u0901\u091a": 5,
  "\u092a\u0902\u091a": 5,
  "\u092b\u093e\u0907\u0935": 5,
  "\u091b\u0939": 6,
  "\u091b\u0903": 6,
  "\u091b\u0947": 6,
  "\u0938\u093f\u0915\u094d\u0938": 6,
  "\u0938\u093e\u0924": 7,
  "\u0938\u0947\u0935\u0928": 7,
  "\u0906\u0920": 8,
  "\u0928\u094c": 9,
  "\u0928\u093e\u0907\u0928": 9,
  "\u0a38\u0a3f\u0a2b\u0a30": 0,
  "\u0a07\u0a71\u0a15": 1,
  "\u0a26\u0a4b": 2,
  "\u0a24\u0a3f\u0a70\u0a28": 3,
  "\u0a1a\u0a3e\u0a30": 4,
  "\u0a2a\u0a70\u0a1c": 5,
  "\u0a1b\u0a47": 6,
  "\u0a38\u0a71\u0a24": 7,
  "\u0a05\u0a71\u0a20": 8,
  "\u0a28\u0a4c\u0a02": 9,
};

export function parsePhone(text) {
  const toks = normalizeWords(text).split(" ").filter(Boolean);
  let digits = "";
  let mult = 1;
  for (const w of toks) {
    if (w === "double" || w === "dabal" || w === "\u0921\u092c\u0932") { mult = 2; continue; }
    if (w === "triple" || w === "tripal" || w === "\u091f\u094d\u0930\u093f\u092a\u0932") { mult = 3; continue; }
    let d = null;
    if (/^\d+$/.test(w)) d = w;
    else if (Object.prototype.hasOwnProperty.call(DIGIT_WORDS, w)) d = String(DIGIT_WORDS[w]);
    if (d === null) { mult = 1; continue; }
    digits += d.length === 1 ? d.repeat(mult) : d;
    mult = 1;
  }
  if (digits.startsWith("0091")) digits = digits.slice(4);
  else if (digits.length === 12 && digits.startsWith("91")) digits = digits.slice(2);
  else if (digits.length === 11 && digits.startsWith("0")) digits = digits.slice(1);
  return /^[6-9]\d{9}$/.test(digits) ? `+91 ${digits}` : null;
}

const EMAIL_DIGITS = {
  zero: "0", one: "1", two: "2", three: "3", four: "4",
  five: "5", six: "6", seven: "7", eight: "8", nine: "9",
  "\u0936\u0942\u0928\u094d\u092f": "0",
  "\u090f\u0915": "1",
  "\u0926\u094b": "2",
  "\u0924\u0940\u0928": "3",
  "\u091a\u093e\u0930": "4",
  "\u092a\u093e\u0902\u091a": "5",
  "\u092a\u093e\u0901\u091a": "5",
  "\u091b\u0939": "6",
  "\u0938\u093e\u0924": "7",
  "\u0906\u0920": "8",
  "\u0928\u094c": "9",
};

export function parseEmail(text) {
  let t = String(text || "").toLowerCase().trim();
  t = t.replace(/(एट|ऐट) (द|दा|दी) रेट/g, " @ ").replace(/डॉट/g, " . ")
    .replace(/जी ?मेल/g, "gmail").replace(/कॉम/g, "com").replace(/याहू/g, "yahoo")
    .replace(/आउटलुक/g, "outlook").replace(/हॉटमेल/g, "hotmail")
    .replace(/अंडरस्कोर/g, " _ ").replace(/डैश/g, " - ");
  t = t.replace(/\bat the rate( of)?\b/g, " @ ").replace(/\bat rate\b/g, " @ ").replace(/\battherate\b/g, " @ ");
  t = t.replace(/\b(underscore|under score)\b/g, " _ ");
  t = t.replace(/\b(dash|hyphen|minus)\b/g, " - ");
  t = t.replace(/\b(dot|period|full stop)\b/g, " . ");
  if (!t.includes("@")) {
    const i = t.lastIndexOf(" at ");
    if (i >= 0) t = `${t.slice(0, i)} @ ${t.slice(i + 4)}`;
  }
  let e = t.split(/\s+/).filter(Boolean)
    .map((w) => (Object.prototype.hasOwnProperty.call(EMAIL_DIGITS, w) ? EMAIL_DIGITS[w] : w))
    .join("");
  e = e.replace(/[^a-z0-9@._+-]/g, "");
  const m = e.match(/^(.+@)(gmail|yahoo|outlook|hotmail|icloud|rediffmail)$/);
  if (m) e = `${m[1]}${m[2]}.com`;
  return /^[a-z0-9._+-]+@[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(e) ? e : null;
}

function titleCase(s) {
  return s.split(" ").map((w) => (w ? w[0].toUpperCase() + w.slice(1).toLowerCase() : w)).join(" ");
}

const NAME_FILLER = new Set(["my", "name", "is", "full", "the", "i", "am", "im", "this", "naam", "mera", "meraa", "poora", "pura", "hai", "ha", "me", "main", "hoon", "hu", "it", "its", "uh", "um", "ok", "okay"]);

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

// States and union territories are not cities. Goa, Delhi, Chandigarh and Puducherry are left out on purpose:
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

export function isSkip(normalized) {
  return /\b(skip|none|pass|nahi|nahin|no|chhodo|chodo)\b/.test(normalized);
}

// ---- yes / back / reserve ----

const RESERVE = new Set([
  "reserve", "book", "booking", "confirm", "yes", "yeah", "yep", "haan", "han",
  "ok", "okay", "sure", "proceed", "continue", "kar", "karo", "kardo", "bukk", "\u0915\u0928\u094d\u092b\u0930\u094d\u092e",
  "\u092c\u0941\u0915", "\u0930\u093f\u091c\u093c\u0930\u094d\u0935", "\u0930\u093f\u091c\u0930\u094d\u0935",
  "\u0939\u093e\u0901", "\u0939\u093e\u0902", "\u0920\u0940\u0915",
  "\u0a2c\u0a41\u0a71\u0a15", "\u0a30\u0a3f\u0a1c\u0a3c\u0a30\u0a35", "\u0a39\u0a3e\u0a02",
]);

const BACK = new Set([
  "back", "wapas", "vapas", "peeche", "previous", "cancel", "no", "nahi", "nahin",
  "other", "others", "hatao", "dont", "stop", "\u092c\u0948\u0915",
  "\u0935\u093e\u092a\u0938", "\u0928\u0939\u0940\u0902", "\u092a\u0940\u091b\u0947",
  "\u0a35\u0a3e\u0a2a\u0a38", "\u0a28\u0a39\u0a40\u0a02", "\u0a2a\u0a3f\u0a71\u0a1b\u0a47",
]);

export function isBackIntent(text) {
  return normalizeWords(text).split(" ").some((w) => BACK.has(w));
}

export function isReserveIntent(text) {
  const words = normalizeWords(text).split(" ");
  if (words.some((w) => BACK.has(w))) return false;
  return words.some((w) => RESERVE.has(w));
}

// ---- picking a result card by number or by name ----

const STRONG_ORD = [
  ["first", "1st", "\u092b\u0930\u094d\u0938\u094d\u091f", "\u092b\u093c\u0930\u094d\u0938\u094d\u091f", "\u092b\u0938\u094d\u091f", "pehla", "pehli", "pehle", "pahla", "pahli", "pahle",
    "\u092a\u0939\u0932\u093e", "\u092a\u0939\u0932\u0940", "\u092a\u0939\u0932\u0947",
    "\u0a2a\u0a39\u0a3f\u0a32\u0a3e", "\u0a2a\u0a39\u0a3f\u0a32\u0a40"],
  ["second", "2nd", "\u0938\u0947\u0915\u0902\u0921", "\u0938\u0947\u0915\u0947\u0902\u0921", "dusra", "dusri", "dusre", "doosra", "doosri", "doosre",
    "\u0926\u0942\u0938\u0930\u093e", "\u0926\u0942\u0938\u0930\u0940", "\u0926\u0942\u0938\u0930\u0947",
    "\u0a26\u0a42\u0a1c\u0a3e", "\u0a26\u0a42\u0a1c\u0a40"],
  ["third", "3rd", "\u0925\u0930\u094d\u0921", "teesra", "teesri", "tisra", "tisri",
    "\u0924\u0940\u0938\u0930\u093e", "\u0924\u0940\u0938\u0930\u0940",
    "\u0a24\u0a40\u0a1c\u0a3e", "\u0a24\u0a40\u0a1c\u0a40"],
  ["fourth", "4th", "\u092b\u094b\u0930\u094d\u0925", "chautha", "chauthi",
    "\u091a\u094c\u0925\u093e", "\u091a\u094c\u0925\u0940", "\u0a1a\u0a4c\u0a25\u0a3e"],
  ["fifth", "5th", "\u092b\u093f\u092b\u094d\u0925", "paanchva", "panchva", "paanchwa",
    "\u092a\u093e\u0902\u091a\u0935\u093e\u0902", "\u092a\u093e\u0901\u091a\u0935\u093e\u0902", "\u0a2a\u0a70\u0a1c\u0a35\u0a3e\u0a02"],
  ["sixth", "6th", "chhatha", "\u091b\u0920\u093e"],
];

const WEAK_ORD = [
  ["one", "ek", "\u0935\u0928", "1", "\u090f\u0915", "\u0a07\u0a71\u0a15", "\u0a07\u0a15"],
  ["two", "do", "\u091f\u0942", "2", "\u0926\u094b", "\u0a26\u0a4b"],
  ["three", "teen", "\u0925\u094d\u0930\u0940", "3", "\u0924\u0940\u0928", "\u0a24\u0a3f\u0a70\u0a28"],
  ["four", "char", "chaar", "\u092b\u094b\u0930", "4", "\u091a\u093e\u0930", "\u0a1a\u0a3e\u0a30"],
  ["five", "paanch", "panch", "\u092b\u093e\u0907\u0935", "5", "\u092a\u093e\u0902\u091a", "\u092a\u093e\u0901\u091a", "\u0a2a\u0a70\u0a1c"],
  ["six", "chhe", "\u0938\u093f\u0915\u094d\u0938", "6", "\u091b\u0939", "\u0a1b\u0a47"],
];

const NUMBER_WORDS = new Set([
  "number", "no", "nambar", "option", "hotel", "wala", "wali", "result",
  "\u0928\u0902\u092c\u0930", "\u0928\u092e\u094d\u092c\u0930", "\u0a28\u0a70\u0a2c\u0a30",
]);

const NEXT_OK = new Set(["wala", "wali", "number", "nambar", "option", "\u0935\u093e\u0932\u093e", "\u0a35\u0a3e\u0a32\u0a3e"]);

const LAST = new Set(["last", "\u0932\u093e\u0938\u094d\u091f", "akhri", "akhiri", "antim", "\u0906\u0916\u093f\u0930\u0940", "\u0a06\u0a16\u0a30\u0a40"]);
const CHEAP = new Set(["cheapest", "\u091a\u0940\u092a\u0947\u0938\u094d\u091f", "cheap", "sasta", "sasti", "\u0938\u0938\u094d\u0924\u093e", "\u0a38\u0a38\u0a24\u0a3e"]);
const COSTLY = new Set(["costliest", "expensive", "mehnga", "mahnga", "mehenga", "\u092e\u0939\u0902\u0917\u093e", "\u0a2e\u0a39\u0a3f\u0a70\u0a17\u0a3e"]);

const STOP_TITLE = new Set(["hotel", "hotels", "the", "resort", "resorts", "inn", "by", "and", "of", "in", "a", "an", "at", "suites", "suite", "stay", "stays"]);

function titleTokens(title) {
  return normalizeWords(title).split(" ").filter((w) => w.length >= 3 && !STOP_TITLE.has(w));
}

export function resolvePick(text, cards) {
  if (!cards || !cards.length) return null;
  const words = normalizeWords(text).split(" ").filter(Boolean);
  if (!words.length || words.length > 10) return null;

  // 1. by position
  for (let i = 0; i < words.length; i += 1) {
    const w = words[i];
    for (let k = 0; k < STRONG_ORD.length; k += 1) {
      if (STRONG_ORD[k].includes(w)) return cards[k] || null;
    }
    if (LAST.has(w)) return cards[cards.length - 1];
    for (let k = 0; k < WEAK_ORD.length; k += 1) {
      if (WEAK_ORD[k].includes(w)) {
        const prev = i > 0 ? words[i - 1] : "";
        const next = i + 1 < words.length ? words[i + 1] : "";
        if (words.length === 1 || NUMBER_WORDS.has(prev) || NEXT_OK.has(next)) return cards[k] || null;
      }
    }
  }

  // 2. cheapest / most expensive
  if (words.some((w) => CHEAP.has(w) || COSTLY.has(w))) {
    const wantCheap = words.some((w) => CHEAP.has(w));
    const priced = cards.filter((c) => Number(c.price) > 0);
    if (!priced.length) return null;
    return priced.reduce((a, b) => ((wantCheap ? Number(b.price) < Number(a.price) : Number(b.price) > Number(a.price)) ? b : a));
  }

  // 3. by name: use words that belong to exactly one visible card
  const spoken = new Set(words);
  const toks = cards.map((c) => titleTokens(c.title));
  const count = {};
  toks.forEach((list) => new Set(list).forEach((t) => { count[t] = (count[t] || 0) + 1; }));
  let best = -1;
  let bestScore = 0;
  let tie = false;
  toks.forEach((list, idx) => {
    if (!list.length) return;
    const own = list.filter((t) => count[t] === 1);
    const pool = cards.length === 1 ? list : own;
    if (!pool.length) return;
    const hit = pool.filter((t) => spoken.has(t)).length;
    if (!hit) return;
    const score = hit / pool.length;
    if (cards.length === 1 && score < 0.6) return;
    if (score > bestScore) { best = idx; bestScore = score; tie = false; }
    else if (score === bestScore) tie = true;
  });
  return best >= 0 && !tie ? cards[best] : null;
}

// "select the first one", "open number 2": the person is trying to pick a card.
const PICK_VERBS = new Set([
  "select", "selected", "choose", "chuno", "chunna", "chun", "open", "kholo", "khol",
  "\u0938\u0947\u0932\u0947\u0915\u094d\u091f", "\u091a\u0941\u0928\u094b", "\u0916\u094b\u0932\u094b",
]);

export function hasPickIntent(text) {
  const words = normalizeWords(text).split(" ").filter(Boolean);
  if (!words.length || words.length > 6) return false;
  return words.some((w) => PICK_VERBS.has(w) || NEXT_OK.has(w));
}

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

// Digits spoken one by one ("nine eight seven") or typed; used for OTP and PIN codes.
export function parseDigits(text, min, max) {
  const toks = normalizeWords(text).split(" ").filter(Boolean);
  let digits = "";
  let mult = 1;
  for (const w of toks) {
    if (w === "double" || w === "dabal" || w === "\u0921\u092c\u0932") { mult = 2; continue; }
    if (w === "triple" || w === "tripal" || w === "\u091f\u094d\u0930\u093f\u092a\u0932") { mult = 3; continue; }
    let d = null;
    if (/^\d+$/.test(w)) d = w;
    else if (Object.prototype.hasOwnProperty.call(DIGIT_WORDS, w)) d = String(DIGIT_WORDS[w]);
    if (d === null) { mult = 1; continue; }
    digits += d.length === 1 ? d.repeat(mult) : d;
    mult = 1;
  }
  return digits.length >= min && digits.length <= max ? digits : null;
}

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
