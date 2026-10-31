// Everything the ride screens share: links, calls to the server and the words for each stage.
import { http } from "./api";
import { money } from "./format";

export const fmtINR = money;

// A ride screen link keeps the whole choice in the address, so reload and Back always come back to the same ride.
//   /rides?pn=Jaipur Airport&plat=26.82&plng=75.81&dn=Hawa Mahal&dlat=..&dlng=..&v=bike&when=2026-11-04 09:00
const has = (v) => v !== null && v !== undefined && v !== "" && Number.isFinite(Number(v));
export const hasPoint = (p) => !!p && has(p.lat) && has(p.lng);

export function rideUrl({ pickup, drop, vehicle, when } = {}) {
  const q = new URLSearchParams();
  const put = (p, pre) => {
    if (!p) return;
    if (p.name) q.set(pre + "n", p.name);
    if (hasPoint(p)) {
      q.set(pre + "lat", Number(p.lat).toFixed(6));
      q.set(pre + "lng", Number(p.lng).toFixed(6));
    }
  };
  put(pickup, "p");
  put(drop, "d");
  if (vehicle) q.set("v", vehicle);
  if (when && when !== "now") q.set("when", when);
  const s = q.toString();
  return s ? `/rides?${s}` : "/rides";
}

export function readRideParams(params) {
  const place = (pre) => {
    const name = params.get(pre + "n") || "";
    const lat = Number(params.get(pre + "lat"));
    const lng = Number(params.get(pre + "lng"));
    const ok = params.get(pre + "lat") !== null && params.get(pre + "lng") !== null && Number.isFinite(lat) && Number.isFinite(lng);
    if (!name && !ok) return null;
    return ok ? { name: name || "Pinned location", lat, lng } : { name, query: name };
  };
  return { pickup: place("p"), drop: place("d"), vehicle: params.get("v") || "", when: params.get("when") || "now" };
}

// what the server wants for a place
export const placeBody = (p) => (hasPoint(p)
  ? { name: p.name, lat: Number(p.lat), lng: Number(p.lng) }
  : { query: (p && (p.query || p.name)) || "" });

export const errorText = (e, fallback = "Something went wrong. Please try again.") => {
  const d = e && e.response && e.response.data && e.response.data.detail;
  if (typeof d === "string") return d;
  if (d && typeof d.message === "string") return d.message;
  if (Array.isArray(d) && d[0] && d[0].msg) return "Please check the details and try again.";
  if (e && e.response && e.response.status === 429) return "Too many requests. Please wait a moment.";
  return fallback;
};
export const errorCode = (e) => {
  const d = e && e.response && e.response.data && e.response.data.detail;
  return d && typeof d === "object" ? d : {};
};

export const rideApi = {
  quote: (pickup, drop, when) => http.post("/rides/quote", { pickup: placeBody(pickup), drop: placeBody(drop), ...(when && when !== "now" ? { when } : {}) }).then((r) => r.data),
  places: (q, near) => http.get("/rides/places", { params: { q, ...(near ? { lat: near.lat, lng: near.lng } : {}) } }).then((r) => r.data.results || []),
  book: (quote_token, vehicle, payment_method) => http.post("/rides", { quote_token, vehicle, payment_method }).then((r) => r.data.ride),
  get: (id) => http.get(`/rides/${id}`).then((r) => r.data.ride),
  list: () => http.get("/rides").then((r) => r.data.rides),
  active: () => http.get("/rides/active").then((r) => r.data.ride),
  cancel: (id, reason) => http.post(`/rides/${id}/cancel`, { reason }).then((r) => r.data),
  pay: (id, method, tip, start = true) => http.post(`/rides/${id}/pay`, { method, tip, start }).then((r) => r.data),
  payConfirm: (id) => http.post(`/rides/${id}/pay/confirm`, {}).then((r) => r.data.ride),
  payVerify: (id, body) => http.post(`/rides/${id}/pay/verify`, body).then((r) => r.data.ride),
  rate: (id, body) => http.post(`/rides/${id}/rate`, body).then((r) => r.data.ride),
  share: (id) => http.post(`/rides/${id}/share`, {}).then((r) => r.data.share_token),
  shared: (token) => http.get(`/rides/share/${token}`).then((r) => r.data),
};

export const STAGE_TITLE = {
  scheduled: "Ride scheduled",
  searching: "Finding your captain",
  arriving: "Captain is on the way",
  arrived: "Captain has arrived",
  in_progress: "On your way",
  completed: "You have arrived",
  cancelled: "Ride cancelled",
};

export const isActiveStage = (stage) => !!stage && stage !== "completed" && stage !== "cancelled";

// "2026-11-04 09:00" (India time) -> "4 Nov, 9:00 am"
export function whenText(when) {
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(String(when || ""));
  if (!m) return "Now";
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]));
  const day = d.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
  const time = d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: "UTC" });
  return `${day}, ${time}`;
}

// the browser's date-time box wants "YYYY-MM-DDTHH:MM" in the visitor's time; the server wants India time.
// Visitors are in India for this product, so the box value is sent as it is.
export const boxToWhen = (v) => (v ? String(v).replace("T", " ").slice(0, 16) : "now");
export const whenToBox = (w) => (w && w !== "now" ? String(w).replace(" ", "T").slice(0, 16) : "");

const pad = (n) => String(n).padStart(2, "0");
export function boxLimits() {
  const f = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const now = Date.now();
  return { min: f(new Date(now + 20 * 60000)), max: f(new Date(now + 29 * 24 * 3600 * 1000)) };
}

export const initials = (name) => String(name || "?").split(/\s+/).map((p) => p[0]).join("").slice(0, 2).toUpperCase();
