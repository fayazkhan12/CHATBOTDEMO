// Small line icons for the ride vehicles (also used as HTML on the map, so they are plain strings).
const BODY = {
  bike: '<circle cx="5.5" cy="16.5" r="3"/><circle cx="18.5" cy="16.5" r="3"/><path d="M5.5 16.5 9 10h5l2 3 2.5 3.5M9 10 7.5 8H5M14 10l1-3h2.5M10 13h4"/>',
  auto: '<path d="M3 15V7a2 2 0 0 1 2-2h8l4 5h3v5"/><path d="M3 15h2M9 15h6M19 15h2"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/><path d="M13 5v5h4"/>',
  cab: '<path d="M5 17H3v-5l2-5h14l2 5v5h-2"/><path d="M3 12h18M9 17h6"/><circle cx="7.5" cy="17" r="1.8"/><circle cx="16.5" cy="17" r="1.8"/>',
};

export const kindOf = (key) => (key === "bike" ? "bike" : key === "auto" ? "auto" : "cab");

export function vehicleSvg(key, size = 24) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${BODY[kindOf(key)]}</svg>`;
}
