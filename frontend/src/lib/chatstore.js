// The chat's memory in the browser.
//
// The conversation used to live in the Home page's React state, so opening a hotel and pressing Back (or
// reloading) gave an empty chat, and a search that was still running when the visitor left was lost. Now the
// conversation lives here, outside any page:
//   - it survives navigation (this module is not unmounted) and reloads (it is saved in localStorage for 12 hours),
//   - a search or a reply that finishes while another page is open still lands in the right message,
//   - every message to the server carries what the app knows: the last search (trip), the cards on screen
//     (results) and the hotel the visitor opened or booked (selection), so "make it cheaper", "which one is
//     closest?" or "a cab to my hotel" have something to work with.
// A different person (another account, or logged out) never sees the previous person's chat.
import { useSyncExternalStore } from "react";
import { API, http } from "./api";
import { guardReply } from "./guard";
import { hasPickIntent, resolvePick } from "./voicecmd";
import { perNightLine } from "./format";

const STORE_KEY = "dw_chat_v1";
const KEEP_MS = 12 * 60 * 60 * 1000;      // a chat is kept for 12 hours after its last message
const MAX_MESSAGES = 80;                  // kept on screen and in storage
const SEND_MESSAGES = 30;                 // sent with every message
const STORAGE_BUDGET = 1_400_000;         // characters of result cards kept in storage (newest first)

export const GREETING = {
  id: "greet",
  role: "assistant",
  text: "Hi! I am DestinoWay, your travel concierge. Hotels, flights, buses, rides or groceries: what do you need? You can talk to me in any language.",
};

const fresh = (owner = "guest") => ({ owner, messages: [GREETING], trip: null, selection: null, updatedAt: 0, sending: false });

// ------------------------------------------------------------------ storage
function readStorage() {
  try {
    const raw = window.localStorage.getItem(STORE_KEY);
    if (!raw) return null;
    const o = JSON.parse(raw);
    if (!o || o.v !== 1 || !Array.isArray(o.messages) || !o.updatedAt) return null;
    if (Date.now() - o.updatedAt > KEEP_MS) return null;
    return o;
  } catch {
    return null;
  }
}

function forStorage(m) {
  const out = { ...m };
  delete out.loadingMore;
  if (out.streaming) delete out.streaming;
  if (out.searching) { out.interrupted = out.searching; delete out.searching; }   // a reload cut the search short
  return out;
}

function serialize(s) {
  const msgs = s.messages.slice(-MAX_MESSAGES).map(forStorage);
  let budget = STORAGE_BUDGET;
  for (let i = msgs.length - 1; i >= 0; i -= 1) {       // newest cards first; older ones keep their text only
    const m = msgs[i];
    if (!m.cards || !m.cards.length) continue;
    const size = JSON.stringify(m.cards).length;
    if (size > budget) msgs[i] = { ...m, cards: [], cardsDropped: true };
    else budget -= size;
  }
  return JSON.stringify({ v: 1, owner: s.owner, updatedAt: s.updatedAt, messages: msgs, trip: s.trip, selection: s.selection });
}

function hydrate() {
  const o = readStorage();
  if (!o) return fresh();
  const messages = o.messages
    .filter((m) => m && typeof m === "object" && typeof m.id === "string" && (m.role === "user" || m.role === "assistant"))
    .filter((m) => !(m.streaming && !m.text))            // an answer that never arrived
    .map((m) => { const x = { ...m }; delete x.streaming; delete x.loadingMore; if (x.searching) { x.interrupted = x.searching; delete x.searching; } return x; });
  if (!messages.length || messages[0].id !== "greet") messages.unshift(GREETING);
  return { owner: typeof o.owner === "string" ? o.owner : "guest", messages, trip: o.trip || null, selection: o.selection || null, updatedAt: o.updatedAt, sending: false };
}

let state = typeof window === "undefined" ? fresh() : hydrate();
const listeners = new Set();
let saveTimer = null;

function save() {
  saveTimer = null;
  try {
    if (state.messages.length <= 1 && !state.trip && !state.selection) window.localStorage.removeItem(STORE_KEY);
    else window.localStorage.setItem(STORE_KEY, serialize(state));
  } catch {
    try {   // storage full: keep the conversation without the result cards
      const slim = { ...state, messages: state.messages.slice(-30).map((m) => ({ ...forStorage(m), cards: [], cardsDropped: !!(m.cards && m.cards.length) })) };
      window.localStorage.setItem(STORE_KEY, serialize(slim));
    } catch { /* private mode: the chat simply stays in memory */ }
  }
}

function set(patch, { touch = true } = {}) {
  state = { ...state, ...patch, ...(touch ? { updatedAt: Date.now() } : {}) };
  listeners.forEach((l) => l());
  if (!saveTimer && typeof window !== "undefined") saveTimer = setTimeout(save, 250);
}

if (typeof window !== "undefined") {
  const flush = () => { if (saveTimer) { clearTimeout(saveTimer); save(); } };
  window.addEventListener("pagehide", flush);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") flush(); });
}

export const subscribe = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };
export const getState = () => state;
export const useChat = () => useSyncExternalStore(subscribe, getState, getState);

export const setMessages = (fn) => set({ messages: fn(state.messages) });
const patchMessage = (id, patch) => setMessages((all) => all.map((m) => (m.id === id ? { ...m, ...(typeof patch === "function" ? patch(m) : patch) } : m)));

// ------------------------------------------------------------------ whose chat is this?
// guest -> account keeps the chat (same person logging in); anything else starts a clean chat.
export function setOwner(owner) {
  const next = owner || "guest";
  if (next === state.owner) return;
  if (state.owner === "guest") { set({ owner: next }, { touch: false }); return; }
  state = { ...fresh(next) };
  listeners.forEach((l) => l());
  save();
}

let undoSnapshot = null;
export function clearChat() {
  undoSnapshot = state.messages.length > 1 ? state : null;
  state = { ...fresh(state.owner) };
  listeners.forEach((l) => l());
  save();
  return !!undoSnapshot;
}
export function undoClear() {
  if (!undoSnapshot) return;
  state = { ...undoSnapshot, sending: false, updatedAt: Date.now() };
  undoSnapshot = null;
  listeners.forEach((l) => l());
  save();
}

// ------------------------------------------------------------------ what the app tells the server
export function extractSearchIntent(text) {
  const match = String(text || "").match(/<search>\s*([\s\S]*?)\s*<\/search>/i);
  if (!match) return { clean: String(text || "").replace(/<\s*\/?\s*(?:s(?:e(?:a(?:r(?:c(?:h)?)?)?)?)?)?\s*$/i, "").trim(), intent: null };
  try {
    return { clean: text.replace(match[0], "").trim(), intent: JSON.parse(match[1]) };
  } catch {
    return { clean: text.replace(match[0], "").trim(), intent: null };
  }
}

const KEEP_KEYS = ["service", "origin", "destination", "destination_id", "start_date", "end_date", "travellers", "rooms", "children", "child_ages", "budget_tier", "budget", "budget_min", "area", "pickup", "drop", "vehicle", "when", "items"];
const plainIntent = (intent) => Object.fromEntries(KEEP_KEYS.filter((k) => intent[k] !== undefined && intent[k] !== null && intent[k] !== "").map((k) => [k, intent[k]]));

function historyForServer(messages) {
  return messages
    .filter((m) => m.id !== "greet" && m.text && !m.streaming)
    .slice(-SEND_MESSAGES)
    .map((m) => ({ role: m.role, text: String(m.text).slice(0, 1000), ...(m.role === "assistant" && m.search ? { search: plainIntent(m.search) } : {}) }));
}

const hhmm = (iso) => (/T(\d{2}:\d{2})/.exec(String(iso || "")) || [])[1] || "";

function digestOf(card) {
  const nights = Number(card.nights) || 0;
  const bits = [];
  if (card.type === "hotel" && nights) bits.push(`${nights} night${nights === 1 ? "" : "s"} total`);
  if (perNightLine(card)) bits.push(perNightLine(card));
  if (card.departure) bits.push(`${hhmm(card.departure)}${card.arrival ? "-" + hhmm(card.arrival) : ""}`);
  if (card.duration) bits.push(card.duration);
  return {
    title: card.title, brand: card.brand, price: Number(card.price) || 0, rating: Number(card.rating) || undefined,
    location: card.location || undefined, extra: bits.join(", ") || undefined, meta: Array.isArray(card.meta) ? card.meta.slice(0, 3) : undefined,
  };
}

export function visibleCards(messages = state.messages) {
  const last = [...messages].reverse().find((m) => m.cards && m.cards.length);
  return last ? last.cards.slice(0, last.visible || 3) : [];
}

function resultsForServer(messages) {
  const last = [...messages].reverse().find((m) => (m.cards && m.cards.length) || m.ride || m.noResults);
  if (!last) return null;
  if (last.noResults && !(last.cards && last.cards.length)) {
    // the last search found nothing: the model must know, or a "yes" to "try a bigger budget?" makes no sense to it
    return { service: last.search?.service || last.searchService || "hotels", total: 0, shown: 0, items: [], note: last.note || "nothing found" };
  }
  if (last.ride && last.ride.options) {
    const items = last.ride.options.filter((o) => o.available).slice(0, 8).map((o) => ({
      title: o.name, price: o.fare, extra: `${o.eta_min} min away`, meta: [`${last.ride.distance_km} km`, `${last.ride.duration_min} min trip`],
    }));
    return items.length ? { service: "rides", total: items.length, shown: items.length, items } : null;
  }
  const shown = last.cards.slice(0, last.visible || 3);
  const service = last.search?.service || (shown[0]?.type === "hotel" ? "hotels" : shown[0]?.type === "flight" ? "flights" : shown[0]?.type === "bus" ? "buses" : "hotels");
  return {
    service, total: last.total || last.cards.length, shown: shown.length, ...(last.search?.area ? { area: last.search.area } : {}),
    ...(last.widened ? { widened: true, note: last.note || "" } : {}), items: shown.map(digestOf),
  };
}

// ------------------------------------------------------------------ the hotel the visitor opened or booked
export function selectionFromItem(item, status = "viewed", bookingId) {
  if (!item || (item.type || "hotel") !== "hotel") return null;
  const room = item.room_name || "";
  const name = room && item.title && item.title.endsWith(` - ${room}`) ? item.title.slice(0, -(room.length + 3)) : item.title;
  if (!name) return null;
  const sel = {
    kind: "hotel", name, city: item.destination || item.origin || "", address: item.location || "",
    check_in: item.check_in || "", check_out: item.check_out || "", guests: Number(item.guests) || undefined, status,
    lat: Number(item.lat) || undefined, lng: Number(item.lng) || undefined, id: item.id,
  };
  if (bookingId) sel.booking_id = bookingId;
  return sel;
}

export function noteSelection(sel) {
  if (!sel) return;
  const old = state.selection;
  if (old && old.name === sel.name && old.status === sel.status && old.booking_id === sel.booking_id && old.lat === sel.lat) return;
  // a hotel that was booked stays "booked" when the same hotel is only looked at again
  if (old && old.name === sel.name && old.status === "booked" && sel.status === "viewed") return;
  set({ selection: sel });
}

// ------------------------------------------------------------------ search
const HINGLISH = /\b(hai|hain|hoon|chahiye|chahie|chaiye|chhaiye|dikhao|dikha|dikhate|dikhata|mujhe|kya|nahi|nhi|karo|kro|batao|bataiye|mein|wala|wale|liye|kaise|kitna|kitne|kitni|aur|bhi|theek|thik|sahi|raha|rahe|rahi|dhoondh|dhundh|aap|aapka|aapke|kijiye|dijiye|bilkul|zaroor|sasta|madhyam|abhi|aaj|chaliye|accha|achha|acha|rukna|rukenge|honge|hoga|raat|kahan|kaunsi|kaunse)\b/i;

const uiLang = (text) => {
  const t = text || "";
  if (/[ऀ-ॿ]/.test(t)) return "hi";
  if (HINGLISH.test(t)) return "hinglish";
  return "en";
};

// The line under a reply while a search runs is in the language of the visitor. What they typed last may say nothing
// ("2", "ok", a single word), so the reply (which follows the visitor) and then their earlier messages are looked at too.
function chatLang(replyText) {
  const users = state.messages.filter((x) => x.role === "user").slice(-3).reverse();
  const last = uiLang(users[0]?.text);
  if (last !== "en") return last;
  const own = uiLang(replyText);
  if (own !== "en") return own;
  if (String(users[0]?.text || "").trim().split(/\s+/).length <= 2) {
    for (const m of users.slice(1)) {
      const l = uiLang(m.text);
      if (l !== "en") return l;
    }
  }
  return "en";
}

export async function runSearch(intent, replyId) {
  const lang = chatLang(state.messages.find((m) => m.id === replyId)?.text);
  if (intent.service === "rides") return runRideQuote(intent, replyId, lang);
  if (intent.service === "grocery") return runGrocery(intent, replyId, lang);
  patchMessage(replyId, { searching: intent.service, noResults: false, note: "", widened: false, interrupted: undefined, lang });
  try {
    const body = {
      service: intent.service,
      origin: intent.origin || "Delhi",
      destination: intent.destination,
      ...(intent.destination_id ? { destination_id: intent.destination_id } : {}),
      start_date: intent.start_date,
      end_date: intent.end_date || intent.start_date,
      travellers: Number(intent.travellers || 2),
      ...(intent.service === "hotels" && Number(intent.rooms) > 1 ? { rooms: Number(intent.rooms) } : {}),
      ...(intent.service === "hotels" && Number(intent.children) > 0 && Array.isArray(intent.child_ages) && intent.child_ages.length === Number(intent.children)
        ? { children: Number(intent.children), child_ages: intent.child_ages.map(Number) } : {}),
      ...(intent.budget_tier ? { budget_tier: intent.budget_tier } : {}),
      ...(intent.budget ? { budget: Number(intent.budget) } : {}),
      ...(intent.budget_min ? { budget_min: Number(intent.budget_min) } : {}),
      ...(intent.area ? { area: intent.area } : {}),
      lang,                                      // the notes the server writes come in the chat's language
    };
    const { data } = await http.post("/travel/search", body);
    await http.post("/travel/cache", data.results).catch(() => {});
    const found = Array.isArray(data.results) ? data.results : [];
    patchMessage(replyId, {
      searching: false, cards: found, cardsDropped: false, visible: 3, total: data.total || 0,
      page: data.page || 1, hasMore: !!data.has_more, searchBody: body,
      noResults: found.length === 0, note: data.note || "", widened: !!data.widened, searchService: intent.service, lang,
    });
  } catch {
    setMessages((prev) => [
      ...prev.map((m) => (m.id === replyId ? { ...m, searching: false, interrupted: intent.service } : m)),
      { id: `err-${Date.now()}`, role: "assistant", text: "Search failed. Please try again in a moment." },
    ]);
  }
}

// A grocery list from the chat ("2 milk, bread"): the items found on the shelf, shown as a card that fills the cart.
async function runGrocery(intent, replyId, lang) {
  patchMessage(replyId, { searching: "grocery", noResults: false, interrupted: undefined, lang });
  try {
    const { data } = await http.post("/grocery/match", { items: (intent.items || []).slice(0, 15).map(String) });
    patchMessage(replyId, { searching: false, grocery: { items: data.items || [], missing: data.missing || [] }, cards: undefined, noResults: false, lang });
  } catch (e) {
    setMessages((prev) => [
      ...prev.map((m) => (m.id === replyId ? { ...m, searching: false } : m)),
      { id: `err-${Date.now()}`, role: "assistant", text: "I could not look that up right now. Please try again." },
    ]);
  }
}

// A ride request from the chat: the fares for every vehicle, shown as a card that opens the ride screen.
async function runRideQuote(intent, replyId, lang) {
  patchMessage(replyId, { searching: "rides", noResults: false, interrupted: undefined, lang });
  try {
    const place = async (text, geo) => {
      if (geo && Number.isFinite(geo.lat) && Number.isFinite(geo.lng)) return { name: text, lat: geo.lat, lng: geo.lng };
      if (/^(current location|my location|here)$/i.test(String(text).trim())) return await currentPlace();
      const sel = state.selection;
      if (sel && sel.lat && sel.lng && String(text).toLowerCase().includes(String(sel.name).toLowerCase().slice(0, 18))) return { name: sel.name, lat: sel.lat, lng: sel.lng };
      return { query: text };
    };
    const [pickup, drop] = [await place(intent.pickup, intent.pickup_geo), await place(intent.drop, intent.drop_geo)];
    const { data } = await http.post("/rides/quote", { pickup, drop, when: intent.when && intent.when !== "now" ? intent.when : undefined });
    patchMessage(replyId, {
      searching: false, ride: { ...data, vehicle: intent.vehicle || "any", when: intent.when || "now" },
      cards: undefined, noResults: false, lang,
    });
  } catch (e) {
    const detail = e && e.response && e.response.data && e.response.data.detail;
    const text = typeof detail === "string" ? detail : "I could not price that ride right now. Please try again.";
    setMessages((prev) => [
      ...prev.map((m) => (m.id === replyId ? { ...m, searching: false } : m)),
      { id: `err-${Date.now()}`, role: "assistant", text },
    ]);
  }
}

function currentPlace() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(Object.assign(new Error("no geolocation"), { response: { data: { detail: "Your browser cannot share your location. Tell me the pickup place instead." } } }));
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ name: "Current location", lat: p.coords.latitude, lng: p.coords.longitude }),
      () => reject(Object.assign(new Error("denied"), { response: { data: { detail: "I could not get your location. Allow location access, or tell me the pickup place." } } })),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 },
    );
  });
}

export async function loadMore(msgId) {
  const msg = state.messages.find((m) => m.id === msgId);
  if (!msg || msg.loadingMore) return;
  const hidden = (msg.cards?.length || 0) - (msg.visible || 3);
  if (hidden > 0) { patchMessage(msgId, (m) => ({ visible: (m.visible || 3) + 6 })); return; }
  if (!msg.hasMore || !msg.searchBody) return;
  patchMessage(msgId, { loadingMore: true });
  try {
    const { data } = await http.post("/travel/search", { ...msg.searchBody, page: (msg.page || 1) + 1 });
    await http.post("/travel/cache", data.results).catch(() => {});
    patchMessage(msgId, (m) => {
      const seen = new Set(m.cards.map((c) => c.id));
      const fresh2 = data.results.filter((c) => !seen.has(c.id));
      const all = [...m.cards, ...fresh2];
      return { cards: all, visible: all.length, page: data.page || (m.page || 1) + 1, hasMore: !!data.has_more && fresh2.length > 0, loadingMore: false };
    });
  } catch {
    patchMessage(msgId, { loadingMore: false });
  }
}

export function retrySearch(msgId) {
  const msg = state.messages.find((m) => m.id === msgId);
  if (msg && msg.search && !msg.searching) runSearch(msg.search, msgId);
}

// ------------------------------------------------------------------ sending a message
export async function sendMessage(text, { userName = null, voice = null, onReply = null } = {}) {
  const t = String(text || "").trim();
  if (!t || state.sending) return null;

  // "open the second one": the visitor is picking a card, no need to ask the model
  const shown = visibleCards();
  if (shown.length && hasPickIntent(t)) {
    const pick = resolvePick(t, shown);
    if (pick) {
      setMessages((old) => [...old,
        { id: `u-${Date.now()}`, role: "user", text: t },
        { id: `a-${Date.now() + 1}`, role: "assistant", text: `Opening ${pick.title}.` },
      ]);
      return { pick };
    }
  }

  const history = historyForServer(state.messages);
  const results = resultsForServer(state.messages);
  const userId = `u-${Date.now()}`;
  const replyId = `a-${Date.now() + 1}`;
  set({ sending: true });
  setMessages((old) => [...old, { id: userId, role: "user", text: t }, { id: replyId, role: "assistant", text: "", streaming: true }]);

  let answer = "";
  try {
    const resp = await fetch(`${API}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: t,
        language: "auto",
        history,
        context: {
          user: userName || null,
          ...(voice ? { voice } : {}),          // "female" | "male": the visitor is talking, so the reply is written to be heard
          ...(state.trip ? { trip: state.trip } : {}),
          ...(state.selection ? { selection: state.selection } : {}),
          ...(results ? { results } : {}),
        },
      }),
    });
    if (resp.status === 429) throw new Error("slow down");
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop();
      for (const chunk of chunks) {
        const line = chunk.split("\n").find((x) => x.startsWith("data: "));
        if (!line) continue;
        try {
          const ev = JSON.parse(line.slice(6));
          if (ev.text) {
            answer += ev.text;
            patchMessage(replyId, { text: guardReply(extractSearchIntent(answer).clean) });
          }
        } catch { /* ignore */ }
      }
    }
  } catch (e) {
    answer = e && e.message === "slow down"
      ? "You are sending messages very fast. Please wait a few seconds."
      : "Cannot reach the concierge right now. Please try again shortly.";
    patchMessage(replyId, { text: answer });
  }

  const { clean: rawClean, intent } = extractSearchIntent(answer);
  const clean = guardReply(rawClean);
  const grocery = !!(intent && intent.service === "grocery" && Array.isArray(intent.items) && intent.items.length);
  const searchable = grocery || !!(intent && intent.service && (intent.destination || (intent.service === "rides" && intent.pickup && intent.drop)));
  patchMessage(replyId, { text: clean, streaming: false, ...(searchable && !grocery ? { search: plainIntent(intent) } : {}) });
  if (searchable && !grocery) set({ trip: plainIntent(intent) });         // a grocery list does not replace the trip being planned
  set({ sending: false });
  if (onReply) { try { onReply(clean, searchable ? intent : null); } catch { /* the caller's problem */ } }     // spoken now, not after the hotel search
  if (searchable) await runSearch(intent, replyId);
  return { clean, intent: searchable ? intent : null };
}
