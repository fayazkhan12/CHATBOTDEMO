// One set of checks for traveller details, used by the form and by voice.
import { isStateName } from "./voicecmd";

const EMAIL_RE = /^[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$/i;
const DOMAIN_TYPOS = {
  "gmial.com": "gmail.com", "gmai.com": "gmail.com", "gamil.com": "gmail.com", "gmail.con": "gmail.com",
  "gmail.co": "gmail.com", "gmaill.com": "gmail.com", "gmil.com": "gmail.com",
  "yahooo.com": "yahoo.com", "yaho.com": "yahoo.com", "hotmial.com": "hotmail.com", "outlok.com": "outlook.com",
};

export function validateName(v) {
  const t = String(v || "").replace(/\s+/g, " ").trim();
  if (!t) return "Please enter your full name.";
  if (t.length < 2 || t.length > 60) return "Name must be 2 to 60 letters.";
  if (!/^[\p{L}\p{M}'. \-]+$/u.test(t)) return "Name can have only letters and spaces.";
  if (t.replace(/[^\p{L}]/gu, "").length < 2) return "Please enter your full name.";
  return "";
}

export function validateEmail(v) {
  const t = String(v || "").trim().toLowerCase();
  if (!t) return "Please enter your email.";
  if (t.length > 120 || !EMAIL_RE.test(t) || t.includes("..")) return "Please enter a valid email, like name@gmail.com.";
  const domain = t.split("@")[1];
  if (DOMAIN_TYPOS[domain]) return `Did you mean ${t.split("@")[0]}@${DOMAIN_TYPOS[domain]}?`;
  return "";
}

export function validatePhone(v) {
  const d = String(v || "").replace(/[\s\-()]/g, "");
  if (!d) return "Please enter your mobile number.";
  const m = d.match(/^(?:\+91|0091|91|0)?(\d{10})$/);
  if (!m) return "Enter a 10 digit mobile number, like +91 9876543210.";
  if (!/^[6-9]/.test(m[1])) return "Indian mobile numbers start with 6, 7, 8 or 9.";
  if (/^(\d)\1{9}$/.test(m[1])) return "Please enter a real mobile number.";
  return "";
}

// City and address are optional, but when given they must make sense.
export function validateCity(v) {
  const t = String(v || "").replace(/\s+/g, " ").trim();
  if (!t) return "";
  if (t.length < 2 || t.length > 40 || /\d/.test(t) || !/^[\p{L}\p{M}'. \-]+$/u.test(t)) return "Please enter a valid city name.";
  if (isStateName(t)) return `${t} is a state. Please enter your city, for example Gurugram.`;
  return "";
}

export function validateAddress(v) {
  const t = String(v || "").replace(/\s+/g, " ").trim();
  if (!t) return "";
  if (isStateName(t)) return "That is a state. Please enter the full address, with house number, street and area.";
  if (t.length < 8) return "Please enter the full address, with house number, street and area.";
  if (t.length > 160) return "Address is too long. Please keep it under 160 characters.";
  if (t.split(" ").length < 2 && !/\d/.test(t)) return "Please enter the full address, with house number, street and area.";
  return "";
}

// Returns { name, email, phone, city, address } with a message for every field that is wrong.
export function validateTraveller(t) {
  const e = {
    name: validateName(t && t.name),
    email: validateEmail(t && t.email),
    phone: validatePhone(t && t.phone),
    city: validateCity(t && t.city),
    address: validateAddress(t && t.address),
  };
  Object.keys(e).forEach((k) => { if (!e[k]) delete e[k]; });
  return e;
}
