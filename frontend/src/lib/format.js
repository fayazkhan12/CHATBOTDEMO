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

// One short line about what was booked, e.g. "10 Nov - 12 Nov \u00b7 2 nights \u00b7 2 guests".
// Works for a saved booking item as well as for a search result. Unknown parts are left out.
export function tripLine(item) {
  if (!item) return "";
  const parts = [];
  if ((item.type || "hotel") === "hotel") {
    const range = dateRange(item.check_in, item.check_out);
    if (range) parts.push(range);
    if (Number(item.nights) > 0) parts.push(plural(Number(item.nights), "night"));
    if (Number(item.guests) > 0) parts.push(plural(Number(item.guests), "guest"));
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
