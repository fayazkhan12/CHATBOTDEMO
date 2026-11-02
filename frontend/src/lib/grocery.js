// Everything the grocery screens share: calls to the server, the cart (kept in this browser) and a few words.
import { useSyncExternalStore } from "react";
import { http } from "./api";
import { money } from "./format";

export const inr = money;

export const gApi = {
  catalog: () => http.get("/grocery/catalog").then((r) => r.data),
  search: (q) => http.get("/grocery/search", { params: { q } }).then((r) => r.data.results || []),
  quote: (items, coupon) => http.post("/grocery/quote", { items, ...(coupon ? { coupon } : {}) }).then((r) => r.data.bill),
  match: (items) => http.post("/grocery/match", { items }).then((r) => r.data),
  order: (body) => http.post("/grocery/orders", body).then((r) => r.data.order),
  get: (id) => http.get(`/grocery/orders/${id}`).then((r) => r.data.order),
  list: () => http.get("/grocery/orders").then((r) => r.data.orders),
  active: () => http.get("/grocery/orders/active").then((r) => r.data.order),
  cancel: (id, reason) => http.post(`/grocery/orders/${id}/cancel`, { reason }).then((r) => r.data.order),
};

export const errorText = (e, fallback = "Something went wrong. Please try again.") => {
  const d = e && e.response && e.response.data && e.response.data.detail;
  if (typeof d === "string") return d;
  if (d && typeof d.message === "string") return d.message;
  if (Array.isArray(d) && d[0] && d[0].msg) return "Please check the details and try again.";
  if (e && e.response && e.response.status === 429) return "Too many requests. Please wait a moment.";
  return fallback;
};

// ---- the cart: { itemId: qty }, shared by every screen, kept in localStorage
const KEY = "dw_cart";
export const MAX_QTY = 10;
let cart = {};
try { const raw = JSON.parse(window.localStorage.getItem(KEY) || "{}"); if (raw && typeof raw === "object") cart = raw; } catch (e) { cart = {}; }
const listeners = new Set();
const save = () => { try { window.localStorage.setItem(KEY, JSON.stringify(cart)); } catch (e) { /* private window */ } };
const emit = () => { cart = { ...cart }; save(); listeners.forEach((l) => l()); };

export function setQty(id, qty) {
  const n = Math.max(0, Math.min(MAX_QTY, Math.floor(Number(qty) || 0)));
  if (n === 0) delete cart[id]; else cart[id] = n;
  emit();
}
export const addOne = (id) => setQty(id, (cart[id] || 0) + 1);
export const removeOne = (id) => setQty(id, (cart[id] || 0) - 1);
export function addMany(list) { (list || []).forEach((l) => { cart[l.id] = Math.min(MAX_QTY, (cart[l.id] || 0) + (Number(l.qty) || 1)); }); emit(); }
export function clearCart() { cart = {}; emit(); }
export const cartLines = () => Object.entries(cart).map(([id, qty]) => ({ id, qty }));

export function useCart() {
  return useSyncExternalStore((cb) => { listeners.add(cb); return () => listeners.delete(cb); }, () => cart);
}

// the last address used, so the next order is one tap
const ADDR = "dw_gaddress";
export function savedAddress() { try { return JSON.parse(window.localStorage.getItem(ADDR) || "null") || {}; } catch (e) { return {}; } }
export function saveAddress(a) { try { window.localStorage.setItem(ADDR, JSON.stringify(a)); } catch (e) { /* ignore */ } }
