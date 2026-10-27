"""Live hotel details (content + rooms) from the company Node API, cleaned for the chatbot.

Why this file exists
--------------------
The Node API (`/api/v1/hotelDetails/search/:searchId/:hotelId/{content,rooms}`) returns a large,
internal-looking payload: supplier cost, markup, commission, supplier names, duplicated rooms,
HTML in text fields, repeated images. The chatbot must never forward that to a browser.

Everything the website shows goes through the two functions below, and ONLY fields listed here
are passed on (a whitelist). If Node renames or removes a field, the matching part of the page
simply disappears; it never crashes and never shows a wrong price.

    clean_content(payload) -> dict      hotel name, photos, amenities, nearby places, check-in notes
    clean_rooms(payload, nights) -> dict   room options with the final price the customer pays

`contract_problems(content, rooms)` lists what is missing, so an API change is noticed early
(see live_check.py).
"""
from __future__ import annotations

import asyncio
import html as _html
import logging
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Query, Request

log = logging.getLogger("destinoway.live")
router = APIRouter(prefix="/api")

IST = timezone(timedelta(hours=5, minutes=30))
ITEM_PREFIX = "ak-"  # the website's hotel ids look like ak-<supplierHotelId>

# server.py hands us its price-signing function (see set_signer). The signed token is what lets
# /bookings trust a room price without believing the browser.
_SIGN: Optional[Callable[[str, int], str]] = None


def set_signer(fn: Optional[Callable[[str, int], str]]) -> None:
    global _SIGN
    _SIGN = fn
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_RE = re.compile(r"(?i)<\s*(br\s*/?|/p|/li|/div|/h[1-6]|/ul|/ol)\s*>")
_BAD_FACILITY = re.compile(r"(?i)(^\s*(no|not)\b|[–-]\s*no\s*$|\bnot available\b)")


# ---------------------------------------------------------------- tiny safe helpers
def _d(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _l(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _dig(x: Any, *path: str) -> Any:
    for key in path:
        x = _d(x).get(key)
        if x is None:
            return None
    return x


def _first(*vals: Any) -> Any:
    for v in vals:
        if v not in (None, "", [], {}):
            return v
    return None


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def _rupees(v: float) -> int:
    """Whole rupees, rounded half up (same as JavaScript Math.round, so the page and the server agree)."""
    return int(math.floor(float(v) + 0.5))


def _money(v: Any) -> Optional[float]:
    n = _num(v)
    return round(n, 2) if n is not None and n >= 0 else None


def _text(v: Any, limit: int = 600) -> str:
    """HTML or plain text -> short, clean plain text (no tags, no entities)."""
    if not isinstance(v, str) or not v.strip():
        return ""
    s = _BLOCK_RE.sub("\n", v)
    s = _TAG_RE.sub("", s)
    s = _html.unescape(s)
    s = "\n".join(re.sub(r"[ \t ]+", " ", ln).strip() for ln in s.splitlines())
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    if len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return s


def _url(v: Any) -> Optional[str]:
    if isinstance(v, str) and v.startswith(("https://", "http://")) and len(v) < 600:
        return v.replace("http://", "https://", 1)
    return None


def _uniq(items: List[str], limit: int) -> List[str]:
    seen, out = set(), []
    for it in items:
        key = it.strip().lower()
        if it.strip() and key not in seen:
            seen.add(key)
            out.append(it.strip())
        if len(out) >= limit:
            break
    return out


def _ist_date(iso: Any) -> Optional[str]:
    """'2026-11-09T12:29:00Z' -> '2026-11-09' (India date)."""
    if not isinstance(iso, str):
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).date().isoformat()


def _pretty_date(iso_date: Optional[str]) -> Optional[str]:
    if not iso_date:
        return None
    try:
        d = datetime.strptime(iso_date, "%Y-%m-%d")
    except ValueError:
        return None
    return f"{d.day} {d.strftime('%b %Y')}"


# ---------------------------------------------------------------- hotel content
def _find_hotel(payload: Any) -> Dict[str, Any]:
    for path in (
        ("data", "content", "data", "hotel"),
        ("data", "content", "hotel"),
        ("data", "hotel"),
        ("hotel",),
    ):
        h = _dig(payload, *path)
        if isinstance(h, dict) and h:
            return h
    return {}


def _images(h: Dict[str, Any], limit: int = 12) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = set()
    hero = _url(h.get("heroImage"))
    cands: List[Tuple[Optional[str], str]] = []
    if hero:
        cands.append((hero, "Hotel"))
    for im in _l(h.get("images")):
        im = _d(im)
        cands.append((_url(im.get("url")), _text(im.get("caption"), 60) or "Photo"))
    for url, cap in cands:
        if url and url not in seen:
            seen.add(url)
            out.append({"url": url, "caption": cap})
        if len(out) >= limit:
            break
    return out


def _amenities(h: Dict[str, Any], limit: int = 24) -> List[str]:
    names = [str(_d(f).get("name") or "") for f in _l(h.get("facilities"))]
    if not names:  # fall back to the coarser groups
        names = [str(_d(f).get("name") or "") for f in _l(h.get("facilityGroups"))]
    names = [_text(n, 60) for n in names]
    return _uniq([n for n in names if n and not _BAD_FACILITY.search(n)], limit)


def _nearby(h: Dict[str, Any], limit: int = 8) -> List[Dict[str, Any]]:
    out = []
    for p in _l(h.get("nearByAttractions")):
        p = _d(p)
        name = _text(p.get("name"), 80)
        if not name:
            continue
        name = re.sub(r"(?i)^the nearest major airport is\s+", "Airport: ", name)
        dist = _num(p.get("distance"))
        unit = str(p.get("unit") or "km").lower()
        if dist is not None:
            if unit.startswith("m") and not unit.startswith("mi"):
                dist = dist / 1000.0
            elif unit.startswith("mi"):
                dist = dist * 1.609
        out.append({"name": name, "distance_km": round(dist, 1) if dist is not None else None})
    out.sort(key=lambda x: (x["distance_km"] is None, x["distance_km"] or 0))
    return out[:limit]


def clean_content(payload: Any) -> Optional[Dict[str, Any]]:
    h = _find_hotel(payload)
    name = _text(h.get("name"), 120)
    if not name:
        return None
    addr = _d(_dig(h, "contact", "address"))
    parts = [addr.get("line1"), addr.get("city"), addr.get("state"), addr.get("postalCode")]
    address_text = ", ".join(_text(p, 80) for p in parts if isinstance(p, str) and p.strip())

    desc_by_type = {}
    for dsc in _l(h.get("descriptions")):
        dsc = _d(dsc)
        t = str(dsc.get("type") or "").lower()
        if t and t not in desc_by_type:
            desc_by_type[t] = _text(dsc.get("text"), 500)
    bits = [desc_by_type.get(k, "") for k in ("headline", "location", "rooms")]
    description = " ".join(b.rstrip() if b.rstrip().endswith((".", "!", "?")) else b.rstrip() + "." for b in bits if b)

    geo = _d(h.get("geoCode"))
    lat, lng = _num(geo.get("lat")), _num(geo.get("long") if "long" in geo else geo.get("lng"))

    notes = _uniq(
        [_text(t, 300) for t in _l(_dig(h, "checkinInfo", "instructions"))]
        + [_text(t, 300) for t in _l(_dig(h, "checkinInfo", "specialInstructions"))],
        6,
    )
    rev = _d(_l(h.get("reviews"))[0]) if _l(h.get("reviews")) else {}
    rating = _num(rev.get("rating"))
    count = _num(rev.get("count"))

    star = _num(h.get("starRating"))
    return {
        "id": str(h.get("id") or ""),
        "name": name,
        "star_rating": int(star) if star and 0 < star <= 5 else None,
        "type": _text(h.get("type") or h.get("category"), 40) or None,
        "address": address_text or None,
        "city": _text(addr.get("city"), 60) or None,
        "location": {"lat": lat, "lng": lng} if lat is not None and lng is not None else None,
        "images": _images(h),
        "description": description or None,
        "amenities": _amenities(h),
        "nearby": _nearby(h),
        "check_in_from": _text(_dig(h, "checkinInfo", "beginTime"), 20) or None,
        "check_out_by": _text(_dig(h, "checkoutInfo", "time"), 20) or None,
        "notes": notes,
        "rating": {"value": rating, "count": int(count or 0)} if rating else None,
    }


# ---------------------------------------------------------------- rooms
def _find_recommendations(payload: Any) -> List[Any]:
    for path in (
        ("data", "rooms", "recommendations"),
        ("data", "recommendations"),
        ("rooms", "recommendations"),
        ("recommendations",),
    ):
        r = _dig(payload, *path)
        if isinstance(r, list):
            return r
    return []


def _bed_text(beds: Any) -> Optional[str]:
    out = []
    for b in _l(beds):
        b = _d(b)
        t = re.sub(r"(?<!^)(?=[A-Z])", " ", str(b.get("type") or "").strip())
        if not t:
            continue
        c = int(_num(b.get("count")) or 1)
        out.append(f"{c} {t}")
    return ", ".join(out) or None


def _free_cancel_until(group: Dict[str, Any]) -> Optional[str]:
    """Last date (India) up to which cancelling costs nothing. None = not free / unknown."""
    if group.get("refundable") is not True:
        return None
    for pol in _l(group.get("cancellationPolicies")):
        rules = [_d(r) for r in _l(_d(pol).get("rules"))]
        if rules and _num(rules[0].get("value")) == 0:
            d = _ist_date(rules[0].get("end"))
            if d and d >= datetime.now(IST).date().isoformat():
                return d
    return None


def _price(p: Any, nights: Optional[int]) -> Optional[Dict[str, Any]]:
    """Customer-facing price only. Supplier cost, markup, tax split and commission are NOT passed on."""
    p = _d(p)
    total = _money(p.get("totalPrice"))
    if not total:
        return None
    before = _money(p.get("totalPriceBeforeCoupon"))
    out: Dict[str, Any] = {"total": total, "payable": _rupees(total), "currency": str(p.get("currency") or "INR")[:3]}
    if before and before > total + 0.5:
        out["before_coupon"] = before
        out["savings"] = round(before - total, 2)
    if nights and nights > 0:
        out["per_night"] = round(total / nights, 2)
    return out


def clean_rooms(payload: Any, nights: Optional[int] = None, item_id: Optional[str] = None) -> Dict[str, Any]:
    rooms: List[Dict[str, Any]] = []
    seen = set()
    skipped = 0
    for rec in _find_recommendations(payload):
        rec = _d(rec)
        rid = rec.get("recommendationId")
        groups = _l(rec.get("roomGroup"))
        g = _d(groups[0]) if groups else {}
        room = _d(g.get("room"))
        price = _price(_first(rec.get("price"), g.get("price")), nights)
        if not isinstance(rid, str) or not rid or not price:
            skipped += 1
            continue
        name = _text(_first(room.get("name"), room.get("standardRoomName")), 120) or "Room"
        board = _text(_dig(g, "boardBasis", "description"), 60) or None
        board_type = str(_dig(g, "boardBasis", "type") or "")
        breakfast = "breakfast" in (board or "").lower() or "breakfast" in board_type.lower() or "bb" == board_type.lower()
        refundable = g.get("refundable") is True
        free_until = _free_cancel_until(g)

        key = (name.lower(), round(price["total"]), refundable, (board or "").lower(), free_until)
        if key in seen:  # Node often returns the same room twice
            continue
        seen.add(key)

        imgs = _uniq([u for u in (_url(_d(i).get("url")) for i in _l(room.get("images"))) if u], 5)
        facs = [_text(_d(f).get("name"), 60) for f in _l(room.get("facilities"))]
        facs = [f for f in facs if f and not re.match(r"(?i)^wifi speed", f)]
        amenities = _uniq([f for f in facs if not _BAD_FACILITY.search(f)] + [_text(i, 60) for i in _l(g.get("includes"))], 10)

        left = _num(g.get("availability"))
        if refundable and free_until:
            cancel_text = f"Free cancellation till {_pretty_date(free_until)}"
        elif refundable:
            cancel_text = "Refundable (cancellation charges may apply)"
        else:
            cancel_text = "Non-refundable"

        booking_id = f"{item_id}#{rid}" if item_id else None
        token = None
        if _SIGN and booking_id and len(booking_id) <= 100:
            try:
                token = _SIGN(booking_id, price["payable"])
            except Exception:  # never let signing break the page
                log.warning("could not sign room price", exc_info=True)
        rooms.append(
            {
                "recommendation_id": rid,
                "booking_id": booking_id,
                "price_token": token,
                "name": name,
                "description": (None if _text(room.get("description"), 300).lower() == name.lower() else _text(room.get("description"), 300)) or None,
                "beds": _bed_text(room.get("beds")),
                "images": imgs,
                "amenities": amenities,
                "board": board,
                "breakfast_included": bool(breakfast),
                "refundable": refundable,
                "free_cancellation_until": free_until,
                "cancellation": cancel_text,
                "pay_at_hotel": g.get("payAtHotel") is True,
                "rooms_left": int(left) if left is not None and 0 < left <= 3 else None,
                "price": price,
            }
        )
    rooms.sort(key=lambda r: r["price"]["total"])
    rooms = rooms[:12]
    return {
        "rooms": rooms,
        "from_price": rooms[0]["price"]["total"] if rooms else None,
        "currency": rooms[0]["price"]["currency"] if rooms else "INR",
        "skipped": skipped,
    }


# ---------------------------------------------------------------- "has the API changed?" check
def contract_problems(content_payload: Any, rooms_payload: Any) -> List[str]:
    probs: List[str] = []
    h = _find_hotel(content_payload)
    if not h:
        probs.append("content: hotel object not found (expected data.content.data.hotel)")
    else:
        if not _text(h.get("name")):
            probs.append("content: hotel.name missing")
        if not _l(h.get("images")) and not h.get("heroImage"):
            probs.append("content: no images")
        if not _l(h.get("facilities")) and not _l(h.get("facilityGroups")):
            probs.append("content: no facilities")
    recs = _find_recommendations(rooms_payload)
    if not recs:
        probs.append("rooms: no recommendations (expected data.rooms.recommendations)")
    for i, rec in enumerate(recs[:5]):
        rec = _d(rec)
        g = _d(_l(rec.get("roomGroup"))[0]) if _l(rec.get("roomGroup")) else {}
        if not rec.get("recommendationId"):
            probs.append(f"rooms[{i}]: recommendationId missing")
        if not _money(_dig(rec, "price", "totalPrice")):
            probs.append(f"rooms[{i}]: price.totalPrice missing")
        if not _text(_dig(g, "room", "name")):
            probs.append(f"rooms[{i}]: roomGroup[0].room.name missing")
        if "refundable" not in g:
            probs.append(f"rooms[{i}]: roomGroup[0].refundable missing")
    return probs


# ---------------------------------------------------------------- talking to the Node API
class NodeError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _base() -> str:
    host = (os.environ.get("NODE_API_BASE") or os.environ.get("AKBAR_API_HOST") or "").rstrip("/")
    if not host:
        raise HTTPException(status_code=503, detail="Live hotel service is not configured.")
    return f"{host}/api/v1/hotelDetails/search"


async def _get_json(client: httpx.AsyncClient, url: str) -> Any:
    try:
        r = await client.get(url, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise NodeError(0, f"network: {type(exc).__name__}") from exc
    if r.status_code >= 400:
        raise NodeError(r.status_code, f"http {r.status_code}")
    try:
        return r.json()
    except ValueError as exc:
        raise NodeError(502, "not json") from exc


async def fetch_details(
    client: httpx.AsyncClient, base: str, search_id: str, hotel_id: str, nights: Optional[int] = None
) -> Dict[str, Any]:
    """Fetch content + rooms in parallel. One of them failing still returns the other."""
    prefix = f"{base}/{search_id}/{hotel_id}"
    c_res, r_res = await asyncio.gather(
        _get_json(client, f"{prefix}/content"), _get_json(client, f"{prefix}/rooms"), return_exceptions=True
    )
    warnings: List[str] = []
    content = rooms = None
    raw_c = raw_r = None
    if isinstance(c_res, Exception):
        warnings.append(f"content unavailable ({c_res})")
    else:
        raw_c, content = c_res, clean_content(c_res)
    if isinstance(r_res, Exception):
        warnings.append(f"rooms unavailable ({r_res})")
    else:
        raw_r, rooms = r_res, clean_rooms(r_res, nights, f"{ITEM_PREFIX}{hotel_id}")

    if isinstance(c_res, NodeError) and isinstance(r_res, NodeError):
        statuses = {c_res.status, r_res.status}
        if statuses & {400, 404, 410}:
            raise NodeError(410, "search expired")
        raise NodeError(502, "node unavailable")

    if raw_c is not None and raw_r is not None:
        probs = contract_problems(raw_c, raw_r)
        if probs:
            log.warning("live hotel API shape changed? %s", "; ".join(probs[:6]))
            warnings.extend(probs[:3])
    return {
        "source": "live",
        "search_id": search_id,
        "hotel_id": hotel_id,
        "item_id": f"{ITEM_PREFIX}{hotel_id}",
        "nights": nights,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "content": content,
        "rooms": (rooms or {}).get("rooms", []),
        "from_price": (rooms or {}).get("from_price"),
        "currency": (rooms or {}).get("currency", "INR"),
        "warnings": warnings,
    }


# ---------------------------------------------------------------- the endpoint the website calls
_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_CACHE_TTL = 120
_HITS: Dict[str, List[float]] = {}


def _client_ip(request: Request) -> str:
    if os.environ.get("TRUST_PROXY") == "1":
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _limit(key: str, limit: int = 40, window: int = 60) -> None:
    now = time.time()
    if len(_HITS) > 5000:
        _HITS.clear()
    hits = [t for t in _HITS.get(key, []) if now - t < window]
    if len(hits) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    hits.append(now)
    _HITS[key] = hits


@router.get("/hotels/live/{search_id}/{hotel_id}")
async def hotel_live(search_id: str, hotel_id: str, request: Request, nights: Optional[int] = Query(None, ge=1, le=30)):
    if not _ID_RE.match(search_id) or not _ID_RE.match(hotel_id):
        raise HTTPException(status_code=400, detail="Invalid hotel reference.")
    _limit(f"live:{_client_ip(request)}")
    key = f"{search_id}|{hotel_id}|{nights}"
    now = time.time()
    hit = _CACHE.get(key)
    if hit and hit[0] > now:
        return hit[1]
    base = _base()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=8.0)) as client:
            data = await fetch_details(client, base, search_id, hotel_id, nights)
    except NodeError as exc:
        if exc.status == 410:
            raise HTTPException(status_code=410, detail="This search has expired. Please search again.")
        log.warning("live hotel fetch failed: %s", exc)
        raise HTTPException(status_code=502, detail="Live hotel details are not available right now. Please try again.")
    if len(_CACHE) > 300:
        for k in [k for k, v in _CACHE.items() if v[0] <= now]:
            _CACHE.pop(k, None)
        while len(_CACHE) > 200:
            _CACHE.pop(next(iter(_CACHE)), None)
    if data["content"] or data["rooms"]:
        _CACHE[key] = (now + _CACHE_TTL, data)
    return data
