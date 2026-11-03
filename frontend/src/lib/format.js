// Small helpers that every page uses to show money, dates and counts the same way.

const RUPEE = "\u20b9";

// 1462.4 -> "\u20b91,462" (whole rupees; the same rounding the server uses for room prices)
export const money = (n) => RUPEE + Math.floor((Number(n) || 0) + 0.5).toLocaleString("en-IN");

// "2026-11-10" or "2026-11-10T06:20:00" -> "10 Nov"; anything else -> ""
export function shortDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  if (!m) return "";
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
}

// "2026-11-10T06:20:00" -> "06:20"; anything else -> ""
export function clockTime(iso) {
  const m = /T(\d{2}:\d{2})/.exec(String(iso || ""));
  return m ? m[1] : "";
}

// plural(2, "night") -> "2 nights"; plural(1, "bus", "buses") -> "1 bus"
export const plural = (n, one, many) => `${n} ${Number(n) === 1 ? one : many || `${one}s`}`;

// ("2026-11-10", "2026-11-12") -> "10 Nov - 12 Nov"; "" when a date is missing
export function dateRange(from, to) {
  const a = shortDate(from);
  const b = shortDate(to);
  return a && b ? `${a} - ${b}` : "";
}

// Who stays in a hotel offer: "2 guests", or "2 adults, 1 child, 2 rooms" when there are children or more than one room.
// Works for a search result, a saved offer and a booking item. Older items only know the guest count.
export function guestLine(item) {
  if (!item) return "";
  const adults = Number(item.adults) || 0;
  const kids = Number(item.children) || 0;
  const rooms = Number(item.rooms) || 1;
  if (!adults) {
    const n = Number(item.guests) || 0;
    return n > 0 ? plural(n, "guest") : "";
  }
  if (!kids && rooms <= 1) return plural(adults, "guest");
  const parts = [plural(adults, "adult")];
  if (kids) parts.push(plural(kids, "child", "children"));
  if (rooms > 1) parts.push(plural(rooms, "room"));
  return parts.join(", ");
}

// The rooms and guests of a hotel search, read from the page link (?travellers=2&rooms=1&children=2&child_ages=7,3).
// Anything that does not make sense falls back to the plain default, and there are never children without an age each.
export function readOccupancy(src = {}) {
  const whole = (v, lo, hi, fallback) => {
    const n = Math.floor(Number(v));
    return Number.isFinite(n) && n >= lo && n <= hi ? n : fallback;
  };
  const adults = whole(src.travellers, 1, 10, 2);
  const rooms = Math.min(whole(src.rooms, 1, 5, 1), adults);   // every room has an adult
  const kids = whole(src.children, 0, 6, 0);
  let ages = String(src.child_ages === undefined || src.child_ages === null ? "" : src.child_ages).split(",").map((s) => s.trim()).filter((s) => s !== "").map(Number);
  if (!kids || ages.length !== kids || ages.some((a) => !Number.isInteger(a) || a < 0 || a > 17)) ages = [];
  return { adults, rooms, children: ages.length, childAges: ages };
}

// One short line about what was booked, e.g. "10 Nov - 12 Nov \u00b7 2 nights \u00b7 2 guests".
// Works for a saved booking item as well as for a search result. Unknown parts are left out.
export function tripLine(item) {
  if (!item) return "";
  const parts = [];
  if ((item.type || "hotel") === "hotel") {
    const range = dateRange(item.check_in, item.check_out);
    if (range) parts.push(range);
    if (Number(item.nights) > 0) parts.push(plural(Number(item.nights), "night"));
    const who = guestLine(item);
    if (who) parts.push(who);
  } else {
    const day = shortDate(item.check_in || item.departure);
    if (day) parts.push(day);
    const dep = clockTime(item.departure);
    if (dep) parts.push(dep);
    if (Number(item.guests) > 0) parts.push(plural(Number(item.guests), "traveller"));
  }
  return parts.join(" \u00b7 ");
}

const two = (n) => String(n).padStart(2, "0");

// A Date -> "2026-11-10" in the visitor's own time zone (toISOString would give the UTC day,
// which is the wrong day in India before 5:30 in the morning).
export const isoDay = (d) => `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}`;

// dayFromNow(0) = today, dayFromNow(1) = tomorrow, as "YYYY-MM-DD"
export function dayFromNow(offset = 0) {
  const n = new Date();
  return isoDay(new Date(n.getFullYear(), n.getMonth(), n.getDate() + offset));
}

// addDays("2026-11-30", 1) -> "2026-12-01"; "" when the date is not valid
export function addDays(iso, n) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
  if (!m) return "";
  return isoDay(new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + n));
}

// The sentence that tells the visitor a booking is a demo. A hotel's room and price are live, but the reservation is not sent anywhere.
export function demoBookingNote(item) {
  const hotel = !!item && ((item.type || "") === "hotel" || String(item.id || "").startsWith("ak-"));
  return hotel
    ? "Demo booking. The room and price are live, but this reservation is not sent to the hotel and no real money is charged."
    : "Demo booking. Sample data only: no real ticket is issued and no real money is charged.";
}

// A hotel offer's price is for the whole stay. The per-night price of ONE room ("₹2,100 per night") is what budgets are about;
// "" when it would only repeat the total (one night, one room) or the offer is not a hotel stay.
export function perNightLine(item) {
  if (!item || item.type !== "hotel") return "";
  const nights = Number(item.nights) || 0;
  const rooms = Math.max(1, Number(item.rooms) || 1);
  const price = Number(item.price) || 0;
  if (nights < 1 || price <= 0 || (nights === 1 && rooms === 1)) return "";
  return `${money(price / nights / rooms)} per night${rooms > 1 ? " per room" : ""}`;
}
