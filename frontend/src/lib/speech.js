// Turning a written reply into something that is pleasant to hear.
//
// A chat reply is written for the eyes: "₹6,000", "5 Nov", "**bold**", emoji, brackets, "24/7". Read out as it is, a voice
// stumbles over all of it, and that is a big part of why a computer voice sounds like a computer.
//   prepareSpeech()   rewrites the text the way a person would say it
//   splitForSpeech()  cuts it into sentences, so the voice can breathe between them and the first sentence can start early
// No imports on purpose: this file is tested on its own (test_voice_unit.mjs).

const MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const MONTHS_HI = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"];
const SHORT_MONTH = { jan: 0, feb: 1, mar: 2, apr: 3, jun: 5, jul: 6, aug: 7, sep: 8, sept: 8, oct: 9, nov: 10, dec: 11 };
const ACRONYMS = /\b(OTP|UPI|GST|PNR|KYC|ATM|SUV|CCTV|IRCTC|BHK|AC)\b/g;

const count = (t, rx) => (t.match(rx) || []).length;
const trimNum = (x) => String(Math.round(x * 100) / 100);

// 125000 -> "1.25 lakh", 20000000 -> "2 crore", 6000 -> "6000": the way Indians say money
function amountWords(raw, hindi) {
  const n = Number(raw);
  if (!Number.isFinite(n)) return raw;
  if (n >= 1e7) return `${trimNum(n / 1e7)} ${hindi ? "करोड़" : "crore"}`;
  if (n >= 1e5) return `${trimNum(n / 1e5)} ${hindi ? "लाख" : "lakh"}`;
  return String(raw);
}

export function prepareSpeech(text) {
  let t = String(text == null ? "" : text);
  const hindi = count(t, /[\u0900-\u097F]/g) > count(t, /[A-Za-z]/g);

  t = t.replace(/<[^>]*>/g, " ");                                                   // tags
  t = t.replace(/https?:\/\/\S+|www\.\S+/gi, " ");                                  // web addresses
  t = t.replace(/[*_`#~|]+/g, " ");                                                 // markdown marks
  t = t.replace(/^[ \t]*[-\u2022\u00B7\u25AA\u25CF\u25CB\u25E6][ \t]+/gm, "");                                    // list bullets
  t = t.replace(/[\u{1F000}-\u{1FAFF}\u{2190}-\u{21FF}\u{2300}-\u{23FF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE00}-\u{FE0F}\u{200D}\u{20E3}]/gu, " ");   // emoji
  t = t.replace(/[\u2022\u00B7]/g, ", ");
  t = t.replace(/([^.!?\u0964\u0965:;,\u2026\s])[ \t]*\n+/g, "$1. ").replace(/\n+/g, " ");        // a line break is a pause

  // numbers: 1,25,000 -> 125000
  t = t.replace(/\b\d{1,3}(?:,\d{2,3})+(?!\d)/g, (m) => m.replace(/,/g, ""));

  // money
  const rupees = hindi ? "रुपये" : "rupees";
  const UNIT = { k: hindi ? "हज़ार" : "thousand", thousand: hindi ? "हज़ार" : "thousand", hundred: hindi ? "सौ" : "hundred", l: hindi ? "लाख" : "lakh", lakh: hindi ? "लाख" : "lakh", lakhs: hindi ? "लाख" : "lakh", cr: hindi ? "करोड़" : "crore", crore: hindi ? "करोड़" : "crore", crores: hindi ? "करोड़" : "crore" };
  const say = (n, u) => (u ? `${n} ${UNIT[u.toLowerCase()]}` : amountWords(n, hindi));
  const MONEY = "(?:₹|\\bRs\\.?|\\bINR)\\s*";
  const NUM = "(\\d+(?:\\.\\d+)?)(?:\\s*(lakhs?|crores?|thousand|hundred|k|L|Cr)\\b)?";
  t = t.replace(new RegExp(`${MONEY}${NUM}\\s*[-–—]\\s*(?:₹\\s*)?${NUM}(?:\\s*\\/-)?`, "gi"), (_, a, ua, b, ub) => `${say(a, ua)} ${hindi ? "से" : "to"} ${say(b, ub)} ${rupees}`);
  t = t.replace(new RegExp(`${MONEY}${NUM}(?:\\s*\\/-)?`, "gi"), (_, a, u) => `${say(a, u)} ${rupees}`);
  t = t.replace(/(\d+(?:\.\d+)?)\s*₹/g, (_, a) => `${amountWords(a, hindi)} ${rupees}`);
  t = t.replace(/₹/g, ` ${rupees} `);
  t = t.replace(/\/\s*(night|day|person|head|room|km|hour|adult|guest)\b/gi, " per $1");

  // dates and times
  t = t.replace(/\b(20\d\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b/g, (_, y, m, d) => `${Number(d)} ${(hindi ? MONTHS_HI : MONTHS_EN)[Number(m) - 1]}`);
  t = t.replace(/\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)\b\.?/gi, (_, d, m) => `${Number(d)} ${MONTHS_EN[SHORT_MONTH[m.toLowerCase()]]}`);
  t = t.replace(/\b(1[3-9]|2[0-3]|0?0):([0-5]\d)\b(?!\s*[ap]\.?m)/gi, (_, h, m) => {
    const hh = Number(h);
    const h12 = hh % 12 === 0 ? 12 : hh % 12;
    return `${h12}${m === "00" ? "" : ":" + m} ${hh >= 12 ? "PM" : "AM"}`;
  });

  // units and short forms
  t = t.replace(/\b1\s*km\b/gi, hindi ? "1 किलोमीटर" : "1 kilometre").replace(/(\d)\s*kms?\b/gi, `$1 ${hindi ? "किलोमीटर" : "kilometres"}`);
  t = t.replace(/\b1\s*(?:hrs?|hour)\b/gi, hindi ? "1 घंटा" : "1 hour").replace(/(\d)\s*(?:hrs?)\b/gi, `$1 ${hindi ? "घंटे" : "hours"}`);
  t = t.replace(/\b1\s*min\b/gi, hindi ? "1 मिनट" : "1 minute").replace(/(\d)\s*mins?\b/gi, `$1 ${hindi ? "मिनट" : "minutes"}`);
  t = t.replace(/(\d)\s*%/g, `$1 ${hindi ? "प्रतिशत" : "percent"}`);
  t = t.replace(/\bA\/C\b/gi, "A C").replace(/\bw\/o\b/gi, "without");
  t = t.replace(/\be\.g\./gi, "for example").replace(/\bi\.e\./gi, "that is").replace(/\betc\.?/gi, "and so on").replace(/\bapprox\.?/gi, "approximately").replace(/\bvs\.?(?=\s)/gi, "versus");
  t = t.replace(ACRONYMS, (a) => a.split("").join(" "));
  t = t.replace(/&/g, " and ");
  t = t.replace(/([A-Za-z])\/([A-Za-z])/g, "$1 or $2");

  // pauses and brackets
  t = t.replace(/\s[-–—]+\s|[–—]/g, ", ");
  t = t.replace(/\.{2,}|\u2026/g, ". ");
  t = t.replace(/[()[\]{}]/g, ", ");

  // tidy
  t = t.replace(/\s+/g, " ").replace(/\s+([,.!?;:\u0964])/g, "$1").replace(/([,;:])\s*(?=[.!?\u0964])/g, "").replace(/([.!?\u0964])(?:\s*[.,;:])+/g, "$1").replace(/^[\s,.;:]+/, "").trim();
  return /[A-Za-z0-9\u0900-\u0DFF]/.test(t) ? t : "";
}

const ENDS = ".!?\u0964\u0965\u2026";
const CLOSERS = "\"')]\u201D\u2019";

// "Sure. Which city?" -> ["Sure.", "Which city?"]. A full stop inside a number ("1.25") or a short form is not an end.
export function sentences(text) {
  const t = String(text || "");
  const out = [];
  let cur = "";
  for (let i = 0; i < t.length; i += 1) {
    cur += t[i];
    if (ENDS.includes(t[i])) {
      while (i + 1 < t.length && (ENDS.includes(t[i + 1]) || CLOSERS.includes(t[i + 1]))) { i += 1; cur += t[i]; }
      if (i + 1 >= t.length || /\s/.test(t[i + 1])) { out.push(cur.trim()); cur = ""; }
    }
  }
  if (cur.trim()) out.push(cur.trim());
  return out.filter(Boolean);
}

const CONJ = /^(?:(?:and|but|or|aur|lekin|toh|ya)\b|(?:\u0914\u0930|\u0932\u0947\u0915\u093F\u0928|\u092F\u093E)(?=\s))/i;

function breakLong(s, max) {
  if (s.length <= max) return [s];
  const mid = Math.floor(s.length / 2);
  let at = -1;
  for (let d = 0; d < mid && at < 0; d += 1) {          // the comma, "and", "aur"... closest to the middle
    for (const i of [mid - d, mid + d]) {
      if (i > 12 && i < s.length - 12 && (/[,;:]/.test(s[i]) || (s[i] === " " && CONJ.test(s.slice(i + 1))))) { at = i; break; }
    }
  }
  if (at < 0) at = s.lastIndexOf(" ", mid) > 12 ? s.lastIndexOf(" ", mid) : s.indexOf(" ", mid);
  if (at < 0) return [s];
  return [...breakLong(s.slice(0, at + 1).trim(), max), ...breakLong(s.slice(at + 1).trim(), max)].filter(Boolean);
}

// Pieces to speak one after the other. A short reply stays whole (one breath sounds better than three); a long one
// starts with a short piece so the voice can begin early.
export function splitForSpeech(text, { whole = 170, first = 130, max = 240 } = {}) {
  const t = String(text || "").trim();
  if (!t) return [];
  if (t.length <= whole) return [t];
  let parts = [];
  for (const s of sentences(t)) parts.push(...breakLong(s, max));
  const merged = [];                                      // "Dr." or "Okay." alone is too short to be a piece of its own
  for (const p of parts) {
    if (merged.length && merged[merged.length - 1].length < 24) merged[merged.length - 1] += ` ${p}`;
    else merged.push(p);
  }
  parts = merged;
  const out = [];
  let cur = "";
  for (const p of parts) {
    const limit = out.length === 0 ? first : max;
    if (cur && cur.length + 1 + p.length > limit) { out.push(cur); cur = p; } else cur = cur ? `${cur} ${p}` : p;
  }
  if (cur) out.push(cur);
  return out;
}
