// Links into the DestinoWay website (the company's own Next.js site). Both use the same company hotel API, so a search id,
// a hotel id and a room (recommendation) id from the chatbot open the same hotel and room, at the same price, on the website.
export const COMPANY_SITE = (process.env.REACT_APP_COMPANY_SITE || "https://dev.destinoway.com").replace(/\/+$/, "");

// "Hotel Holiday Home" -> "hotel-holiday-home" (the website's own address style)
export const slug = (s) => String(s || "").toLowerCase().normalize("NFKD").replace(/[^\w\s-]/g, "").trim().replace(/[\s_-]+/g, "-").slice(0, 80) || "hotel";

// the hotel's page on the website, or "" when the offer is not a live hotel from the company API
export function companyHotelUrl(item, hotelId) {
  if (!item || item.mode !== "LIVE" || !item.search_id || !hotelId) return "";
  const city = slug(String(item.destination || item.origin || "").split(",")[0]);
  const q = new URLSearchParams({ searchId: item.search_id, hid: String(hotelId) });
  return `${COMPANY_SITE}/hotel-details/${city}/${slug(item.title)}?${q}`;
}

// the website's booking page for this exact room (same order of parameters as the website itself)
export function companyBookingUrl(item, hotelId, room) {
  if (!item || item.mode !== "LIVE" || !item.search_id || !hotelId || !room || !room.recommendation_id) return "";
  const q = new URLSearchParams({
    hotelDetailId: "", searchId: item.search_id, supplierHotelId: String(hotelId),
    recommendationId: room.recommendation_id, roomId: room.recommendation_id,
  });
  return `${COMPANY_SITE}/hotel-booking?${q}`;
}
