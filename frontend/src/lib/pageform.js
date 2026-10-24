// Reads the form on the current page and guides the user through it by voice.
import { parsePhone, parseEmail, parseName, parseCity, parseAddress, parseDigits, phonePartial, emailPartial, digitsPartial } from "./voicecmd";
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
  const skip = optional ? " Say skip to skip." : "";
  const lower = label.toLowerCase();
  switch (kind) {
    case "name": return { ask: `What is your ${lower}?`, retry: "Sorry, please say it again.", parse: parseName };
    case "email": return { ask: "Your email address. Say at the rate and dot where needed." + skip, retry: "I could not get a valid email. Please say it again, for example name at the rate gmail dot com.", parse: parseEmail, dictation: true, partial: emailPartial };
    case "phone": return { ask: "Your mobile number, digit by digit." + skip, retry: "I could not get a valid 10 digit mobile number. Please say it again, digit by digit.", parse: phoneParser(el, label), dictation: true, partial: phonePartial };
    case "otp": return { ask: "Say the code, digit by digit.", retry: "I could not get the code. Please say the digits again.", parse: (t) => parseDigits(t, 4, 8), dictation: true, partial: (t) => digitsPartial(t, 4) };
    case "pin": return { ask: "Say the PIN code, digit by digit." + skip, retry: "Please say the PIN code again, digit by digit.", parse: (t) => parseDigits(t, 5, 6), dictation: true, partial: (t) => digitsPartial(t, 6) };
    case "number": return { ask: `Say the ${lower}.` + skip, retry: "Please say the number again.", parse: (t) => parseDigits(t, 1, 9) };
    case "city": return { ask: "Which city?" + skip, retry: "Please say the city name." + skip, parse: parseCity };
    case "address": return { ask: "Your address?" + skip, retry: "Please say the address." + skip, parse: parseAddress, dictation: true };
    default: return { ask: `Please say ${lower}.` + skip, retry: `Please say ${lower} again.` + skip, parse: (t) => { const s = String(t || "").replace(/\s+/g, " ").trim(); return s.length >= 1 && s.length <= 120 ? s : null; } };
  }
}

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
    doneText: "All fields are filled. Please check the screen and tap the button yourself to continue.",
    editText: "All fields are filled. Say change and the field name to edit, or tap the button to continue.",
  }));
}
