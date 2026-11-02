// Reads the form on the current page and guides the user through it by voice.
import { parsePhone, parseEmail, parseName, parseCity, parseAddress, parseDigits, phonePartial, emailPartial, digitsPartial, explainCity, explainAddress } from "./voicecmd";
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
  const skip = optional ? " Or say skip." : "";
  const lower = label.toLowerCase();
  if (/pick ?up|from/.test(lower) && kind === "text") return { ask: "Where should we pick you up?" + skip, retry: "Sorry, where should we pick you up?" + skip, parse: textOf };
  if (/\bdrop|\bto\b|destination/.test(lower) && kind === "text") return { ask: "And where would you like to go?" + skip, retry: "Sorry, where would you like to go?" + skip, parse: textOf };
  switch (kind) {
    case "name": return { ask: `What's your ${lower}?`, retry: "Sorry, could you say that again?", parse: parseName };
    case "email": return { ask: "What's your email address? Say at the rate and dot where needed." + skip, retry: "I couldn't get a valid email. Could you try again? For example, name at the rate gmail dot com.", parse: parseEmail, dictation: true, partial: emailPartial };
    case "phone": return { ask: "And your mobile number? Take your time, digit by digit." + skip, retry: "Hmm, that doesn't look like a ten digit mobile number. Could you say it again, digit by digit?", parse: phoneParser(el, label), dictation: true, partial: phonePartial };
    case "otp": return { ask: "Please say the code, digit by digit.", retry: "I couldn't get the code. Could you say the digits again?", parse: (t) => parseDigits(t, 4, 8), dictation: true, partial: (t) => digitsPartial(t, 4) };
    case "pin": return { ask: "What's the PIN code? Digit by digit." + skip, retry: "Could you say the PIN code again, digit by digit?", parse: (t) => parseDigits(t, 5, 6), dictation: true, partial: (t) => digitsPartial(t, 6) };
    case "number": return { ask: `What's the ${lower}?` + skip, retry: "Sorry, could you say the number again?", parse: (t) => parseDigits(t, 1, 9) };
    case "city": return { ask: "Which city?" + skip, retry: "Sorry, which city?" + skip, parse: parseCity, explain: explainCity };
    case "address": return { ask: "And your address?" + skip, retry: "Could you say the address again?" + skip, parse: parseAddress, explain: explainAddress, dictation: true };
    default: return { ask: `What's the ${lower}?` + skip, retry: `Sorry, could you say the ${lower} again?` + skip, parse: textOf };
  }
}

const textOf = (t) => { const s = String(t || "").replace(/\s+/g, " ").trim(); return s.length >= 1 && s.length <= 120 ? s : null; };

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
    doneText: "That's everything. Please check the screen, and tap the button yourself when you're ready.",
    editText: "Everything's filled in. Say change, and the field name, to edit something, or tap the button when you're ready.",
  }));
}
