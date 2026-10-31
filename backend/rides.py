"""DestinoWay Rides: bike, auto and cab rides in the style of Rapido.

    GET  /api/rides/places       search places / suggestions near a point
    POST /api/rides/quote        fares for every vehicle (public, signed so the fare cannot be changed)
    POST /api/rides              book a ride (login needed)
    GET  /api/rides              my rides
    GET  /api/rides/active       my ride that is still going on
    GET  /api/rides/{id}         live state of one ride (owner only)
    POST /api/rides/{id}/cancel  cancel with a reason
    POST /api/rides/{id}/pay     choose cash / online, add a tip
    POST /api/rides/{id}/pay/confirm | /pay/verify
    POST /api/rides/{id}/rate    stars, tags, comment
    POST /api/rides/{id}/share   link to follow the ride (no login for the viewer)
    GET  /api/rides/share/{token}

These are DEMO rides: there is no real driver. The captain is generated, the stages are worked out from the
time that has passed (see ride_engine.py) and every response says so. Nothing is charged unless a Razorpay
TEST key is configured.

server.py hands over what it owns (database, login, rate limit, signing secret, payment keys) with setup().
"""
import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

try:
    import ride_engine as eng
    import ride_places as places
except ImportError:  # started as backend.server
    from backend import ride_engine as eng
    from backend import ride_places as places

logger = logging.getLogger("rides")
router = APIRouter(prefix="/api/rides")

DEMO_NOTE = "Demo ride: no real driver is sent and nothing is charged."
QUOTE_TTL = 15 * 60
MIN_LEAD = 15 * 60
MAX_LEAD = 30 * 24 * 3600
SHARE_TTL = 24 * 3600
OSRM_URL = "https://router.project-osrm.org"
CANCEL_REASONS = ["Changed my plans", "Booked by mistake", "Captain is too far", "Waiting for too long", "Found another ride", "Wrong pickup place"]

# filled in by setup()
D: Dict[str, Any] = {}
_now: Callable[[], float] = time.time     # tests replace this with a fake clock


def setup(*, db: Callable[[], Any], current_user: Callable, optional_user: Callable, rate_limit: Callable, client_ip: Callable,
          secret: str, lookup: Callable[[str], Awaitable[List[Dict[str, Any]]]], razorpay: Callable[[], Any],
          razorpay_key_id: Callable[[], str], razorpay_key_secret: Callable[[], str], osrm_url: str = OSRM_URL) -> None:
    D.update(db=db, current_user=current_user, optional_user=optional_user, rate_limit=rate_limit, client_ip=client_ip, secret=secret,
             lookup=lookup, razorpay=razorpay, key_id=razorpay_key_id, key_secret=razorpay_key_secret, osrm=osrm_url)


async def _user(request: Request) -> Dict[str, Any]:
    return await D["current_user"](request)


async def _maybe_user(request: Request) -> Optional[Dict[str, Any]]:
    return await D["optional_user"](request)


# ---------------------------------------------------------------- small helpers
_CTRL = re.compile(r"[\x00-\x1f\x7f<>]")


def _txt(x: Any, n: int = 80) -> str:
    return _CTRL.sub("", str(x or "")).strip()[:n]


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v and abs(v) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return _b64(raw) + "." + hmac.new(D["secret"].encode(), raw, hashlib.sha256).hexdigest()[:40]


def unsign(token: Any) -> Optional[Dict[str, Any]]:
    try:
        body, sig = str(token).split(".", 1)
        raw = _unb64(body)
        good = hmac.new(D["secret"].encode(), raw, hashlib.sha256).hexdigest()[:40]
        if not hmac.compare_digest(good, sig):
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) and data.get("exp", 0) >= _now() else None
    except Exception:
        return None


def _fail(status: int, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail=({"message": message, **extra} if extra else message))


def parse_when(when: Optional[str], now: float) -> float:
    """"now" or "YYYY-MM-DD HH:MM" (India time) -> seconds since 1970. A ride can be booked 15 minutes to 30 days ahead."""
    w = str(when or "").strip()
    if not w or w.lower() == "now":
        return now
    try:
        dt = datetime.strptime(w.replace("T", " ")[:16], "%Y-%m-%d %H:%M").replace(tzinfo=eng.IST)
    except ValueError:
        raise _fail(400, "I could not read that pickup time. Use a date and time like 2026-11-02 18:30.")
    ts = dt.timestamp()
    if ts < now + MIN_LEAD:
        raise _fail(400, "A scheduled ride must be at least 15 minutes from now.")
    if ts > now + MAX_LEAD:
        raise _fail(400, "You can schedule a ride up to 30 days ahead.")
    return ts


# ---------------------------------------------------------------- places
class PlaceIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    lat: Optional[float] = None
    lng: Optional[float] = None
    query: Optional[str] = Field(default=None, max_length=120)


async def _supplier_place(q: str, prefer_city: str) -> Optional[Dict[str, Any]]:
    try:
        found = await D["lookup"](q)
    except Exception as exc:
        logger.warning("place lookup failed: %s", type(exc).__name__)
        return None
    want = set(places._tokens(q))
    best = None
    for d in found or []:
        c = d.get("coordinates") or {}
        lat, lng = _num(c.get("lat")), _num(c.get("long"))
        label = _txt(d.get("label"), 90)
        if lat is None or lng is None or not label or not eng.in_india(lat, lng):
            continue
        city = _txt(d.get("city"), 40)
        in_label = want & set(places._tokens(label))
        in_city = want & set(places._tokens(city))
        if want and not (in_label or in_city):
            continue
        # the result whose own name covers most of the words wins ("Pearl Palace Heritage Hotel" beats the city "Jaipur")
        score = len(in_label) * 2 + len(in_city) * 0.5 + (1 if prefer_city and city.lower() == prefer_city.lower() else 0)
        name = label if (not city or city.lower() in label.lower()) else f"{label}, {city}"
        if best is None or score > best[0]:
            best = (score, {"name": name, "lat": lat, "lng": lng, "city": city})
    return best[1] if best else None


async def resolve_place(p: PlaceIn, prefer_city: str = "") -> Dict[str, Any]:
    lat, lng = _num(p.lat), _num(p.lng)
    if lat is not None and lng is not None:
        if not eng.in_india(lat, lng):
            raise _fail(400, "Rides work inside India. That place is outside it.")
        near = places.near(lat, lng, 1, 3.0)
        return {"name": _txt(p.name) or "Pinned location", "lat": round(lat, 6), "lng": round(lng, 6), "city": near[0]["city"] if near else ""}
    q = _txt(p.query or p.name)
    if not q:
        raise _fail(400, "Tell me the pickup and drop places.")
    r = places.resolve(q, prefer_city)
    if r.get("place"):
        pl = r["place"]
        return {"name": pl["name"], "lat": pl["lat"], "lng": pl["lng"], "city": pl["city"]}
    if r.get("ambiguous"):
        raise _fail(422, "Which city is '%s' in? For example: %s." % (q, " or ".join(a["name"] + ", " + a["city"] for a in r["ambiguous"][:3])))
    s = await _supplier_place(q, prefer_city)
    if s:
        return s
    raise _fail(422, "I could not find '%s'. Try a landmark, station or area name with the city, like 'Hawa Mahal Jaipur'." % q)


# ---------------------------------------------------------------- routes (OSRM with an honest fallback)
_ROUTES: Dict[str, Tuple[float, Optional[Dict[str, Any]]]] = {}
_ROUTE_TTL = 6 * 3600
_ROUTE_FAIL_TTL = 120


def _rkey(a: Tuple[float, float], b: Tuple[float, float]) -> str:
    return "%.4f,%.4f|%.4f,%.4f" % (a[0], a[1], b[0], b[1])


async def get_route(a: Tuple[float, float], b: Tuple[float, float]) -> Dict[str, Any]:
    key = _rkey(a, b)
    now = _now()
    hit = _ROUTES.get(key)
    if hit and hit[0] > now:
        return hit[1] or eng.fallback_route(a, b)
    if len(_ROUTES) > 600:
        _ROUTES.clear()
    straight = eng.haversine_km(a, b)
    route = None
    if D.get("osrm"):
        try:
            url = "%s/route/v1/driving/%.6f,%.6f;%.6f,%.6f" % (D["osrm"].rstrip("/"), a[1], a[0], b[1], b[0])
            async with httpx.AsyncClient(timeout=3.5) as c:
                r = await c.get(url, params={"overview": "simplified", "geometries": "geojson", "alternatives": "false"})
            if r.status_code == 200:
                j = r.json()
                rt = (j.get("routes") or [None])[0]
                if j.get("code") == "Ok" and rt and rt.get("geometry", {}).get("coordinates"):
                    pts = [[round(lat, 6), round(lng, 6)] for lng, lat in rt["geometry"]["coordinates"] if _num(lat) is not None and _num(lng) is not None]
                    km = float(rt["distance"]) / 1000.0
                    mins = float(rt["duration"]) / 60.0
                    if len(pts) >= 2 and straight * 0.9 <= km <= max(straight * 3.5, straight + 8) and mins > 0:
                        route = {"points": eng.decimate(pts), "distance_km": round(km, 2), "duration_min": round(max(mins, 2.0), 1), "source": "road"}
        except Exception as exc:
            logger.info("routing service unavailable: %s", type(exc).__name__)
    _ROUTES[key] = (now + (_ROUTE_TTL if route else _ROUTE_FAIL_TTL), route)
    return route or eng.fallback_route(a, b)


# ---------------------------------------------------------------- quote
class QuoteIn(BaseModel):
    pickup: PlaceIn
    drop: PlaceIn
    when: Optional[str] = Field(default=None, max_length=24)


def _seed(lat: float, lng: float, ts: float) -> str:
    return "%.3f,%.3f|%d" % (lat, lng, int(ts // 300))


def _describe_options(options: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{k: v for k, v in o.items() if k != "breakdown"} for o in options]


@router.post("/quote")
async def quote(body: QuoteIn, request: Request):
    D["rate_limit"]("rq:" + D["client_ip"](request), 40, 60)
    now = _now()
    ts = parse_when(body.when, now)
    pickup = await resolve_place(body.pickup)
    drop = await resolve_place(body.drop, prefer_city=pickup.get("city", ""))
    a, b = (pickup["lat"], pickup["lng"]), (drop["lat"], drop["lng"])
    straight = eng.haversine_km(a, b)
    if straight < eng.MIN_KM:
        raise _fail(400, "Pickup and drop are the same place. Choose a different drop.")
    if straight > eng.MAX_KM:
        raise _fail(400, "That is too far for a ride. For long trips, look at buses or flights.")
    route = await get_route(a, b)
    km, mins = route["distance_km"], route["duration_min"]
    options, surge = eng.options_for(km, mins, ts, _seed(a[0], a[1], ts))
    token = sign({"v": 1, "p": [pickup["name"], pickup["lat"], pickup["lng"]], "d": [drop["name"], drop["lat"], drop["lng"]],
                  "km": km, "min": mins, "ts": ts, "exp": int(now + QUOTE_TTL), "src": route["source"]})
    return {
        "quote_token": token, "expires_in": QUOTE_TTL, "demo": True, "demo_note": DEMO_NOTE,
        "pickup": pickup, "drop": drop, "distance_km": km, "duration_min": int(round(mins)),
        "route": route["points"], "route_source": route["source"],
        "surge": surge if surge["multiplier"] > 1 else None,
        "when": "now" if ts == now else datetime.fromtimestamp(ts, eng.IST).strftime("%Y-%m-%d %H:%M"),
        "scheduled": ts != now,
        "options": _describe_options(options),
    }


# ---------------------------------------------------------------- places endpoint
@router.get("/places")
async def places_search(request: Request, q: str = "", lat: Optional[float] = None, lng: Optional[float] = None):
    D["rate_limit"]("rp:" + D["client_ip"](request), 90, 60)
    q = _txt(q, 60)
    out: List[Dict[str, Any]] = []
    near = _num(lat) is not None and _num(lng) is not None and eng.in_india(lat, lng)
    if not q:
        if near:
            out = [places.public(p) for p in places.near(lat, lng, 8, 40.0)]
        return {"results": out}
    prefer = ""
    if near:
        n = places.near(lat, lng, 1, 60.0)
        prefer = n[0]["city"] if n else ""
    out = [places.public(p) for p in places.search(q, 6, prefer)]
    if len(out) < 5 and len(q) >= 3:
        try:
            for d in (await D["lookup"](q))[:8]:
                c = d.get("coordinates") or {}
                la, ln = _num(c.get("lat")), _num(c.get("long"))
                label = _txt(d.get("label"), 90)
                if la is None or ln is None or not label or not eng.in_india(la, ln):
                    continue
                if any(abs(o["lat"] - la) < 0.0007 and abs(o["lng"] - ln) < 0.0007 for o in out):
                    continue
                city = _txt(d.get("city"), 40)
                out.append({"id": "s-" + str(d.get("id") or label)[:40], "name": label, "sub": ", ".join(x for x in (_txt(d.get("type"), 20).replace("pointOfInterest", "place"), city) if x),
                            "kind": "place", "city": city, "lat": la, "lng": ln})
                if len(out) >= 9:
                    break
        except Exception as exc:
            logger.info("place suggestions skipped: %s", type(exc).__name__)
    return {"results": out[:9]}


# ---------------------------------------------------------------- the ride document and what the screens get
def _payment_view(ride: Dict[str, Any], stage: str) -> Dict[str, Any]:
    pay = ride["payment"]
    tip = int(pay.get("tip") or 0)
    status = pay.get("status", "pending")
    if stage == "cancelled":
        status = "refund_demo" if pay.get("status") == "paid" else "none"
    elif pay["method"] == "cash":
        status = "paid" if stage == "completed" else "pay_on_trip"
    return {"method": pay["method"], "status": status, "tip": tip, "fare": ride["fare"], "amount_due": ride["fare"] + tip,
            "paid_at": pay.get("paid_at"), "needs_payment": pay["method"] == "online" and pay.get("status") != "paid" and stage != "cancelled"}


def view(ride: Dict[str, Any], now: float, owner: bool = True, with_route: bool = True) -> Dict[str, Any]:
    st = eng.state_of(ride, now, for_owner=owner)
    out = {
        "ride_id": ride["ride_id"], "mode": "DEMO", "demo_note": DEMO_NOTE,
        "vehicle": {"key": ride["vehicle"], "name": eng.VEHICLES[ride["vehicle"]]["name"], "group": eng.VEHICLES[ride["vehicle"]]["group"], "seats": eng.VEHICLES[ride["vehicle"]]["seats"]},
        "pickup": ride["pickup"], "drop": ride["drop"], "distance_km": ride["distance_km"], "duration_min": ride["duration_min"],
        "fare": ride["fare"], "breakdown": ride["breakdown"], "surge": ride.get("surge"),
        "created_at": ride["created_at"], "scheduled_for": ride.get("scheduled_for"),
        "state": st, "payment": _payment_view(ride, st["stage"]),
        "rating": ride.get("rating"), "cancelled": ride.get("cancelled"),
    }
    if with_route:
        out["route"] = ride.get("route") or []
    if owner:
        out["share_token"] = ride.get("share_token")
        out["can_rate"] = st["stage"] == "completed" and not ride.get("rating")
        out["cancel_reasons"] = CANCEL_REASONS
    return out


async def _own(ride_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    ride = await D["db"]().rides.find_one({"ride_id": _txt(ride_id, 24), "user_id": user["user_id"]}, {"_id": 0})
    if not ride:
        raise _fail(404, "Ride not found")
    return ride


async def _remember_end(ride: Dict[str, Any], now: float) -> None:
    """Write the final state down the first time somebody sees it (history queries then need no maths)."""
    st = eng.stage_at(ride, now)[0]
    if st in eng.FINAL and not ride.get("status_final"):
        try:
            await D["db"]().rides.update_one({"ride_id": ride["ride_id"], "status_final": {"$exists": False}}, {"$set": {"status_final": st}})
            ride["status_final"] = st
        except Exception as exc:
            logger.info("ride end not stored: %s", type(exc).__name__)


async def _active_for(user_id: str, now: float) -> Optional[Dict[str, Any]]:
    docs = await D["db"]().rides.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(8)
    for r in docs:
        if eng.stage_at(r, now)[0] not in eng.FINAL:
            return r
    return None


# ---------------------------------------------------------------- book
class CreateIn(BaseModel):
    quote_token: str = Field(max_length=1200)
    vehicle: str = Field(max_length=12)
    payment_method: str = Field(default="cash", max_length=8)


@router.post("")
async def create_ride(body: CreateIn, request: Request, user=Depends(_user)):
    D["rate_limit"]("rc:" + user["user_id"], 12, 60)
    now = _now()
    q = unsign(body.quote_token)
    if not q or q.get("v") != 1:
        raise _fail(409, "These fares have expired. Please check the fares again.", code="quote_expired")
    if body.vehicle not in eng.VEHICLES:
        raise _fail(400, "Choose a vehicle.")
    if body.payment_method not in ("cash", "online"):
        raise _fail(400, "Choose cash or online payment.")
    (pn, plat, plng), (dn, dlat, dlng) = q["p"], q["d"]
    ts = float(q["ts"])
    if ts < now - 60:                                  # a "now" ride quoted a few minutes ago starts now, at the quoted price
        start = now
    else:
        start = ts
    if start > now + 60 and start < now + MIN_LEAD - 60:
        raise _fail(400, "A scheduled ride must be at least 15 minutes from now.")
    options, surge = eng.options_for(float(q["km"]), float(q["min"]), ts, _seed(plat, plng, ts))
    option = next(o for o in options if o["key"] == body.vehicle)
    if not option["available"]:
        raise _fail(400, option["reason"])
    active = await _active_for(user["user_id"], now)
    if active:
        raise _fail(409, "You already have a ride going on. Finish or cancel it before booking another.", code="active_ride", ride_id=active["ride_id"])

    ride_id = "DWR" + uuid.uuid4().hex[:8].upper()
    route_data = await get_route((plat, plng), (dlat, dlng))
    eta = option["eta_min"]
    timeline = eng.timeline_for(ride_id, eta, option["duration_min"])
    doc = {
        "ride_id": ride_id, "user_id": user["user_id"], "mode": "DEMO",
        "vehicle": body.vehicle, "pickup": {"name": pn, "lat": plat, "lng": plng}, "drop": {"name": dn, "lat": dlat, "lng": dlng},
        "distance_km": float(q["km"]), "duration_min": option["duration_min"], "eta_min": eta,
        "fare": option["fare"], "breakdown": option["breakdown"], "surge": surge if surge["multiplier"] > 1 else None,
        "route": route_data["points"], "captain": eng.captain_for(ride_id, body.vehicle, places.plate_prefix_near(plat, plng)),
        "captain_start": eng.captain_start((plat, plng), eta, ride_id), "otp": "%04d" % secrets.randbelow(10000),
        "timeline": timeline, "start_ts": start,
        "scheduled_for": datetime.fromtimestamp(start, eng.IST).strftime("%Y-%m-%d %H:%M") if start > now + 60 else None,
        "payment": {"method": body.payment_method, "status": "pending", "tip": 0},
        "created_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
    }
    await D["db"]().rides.insert_one(dict(doc))
    return {"ride": view(doc, now)}


@router.get("")
async def my_rides(user=Depends(_user)):
    now = _now()
    docs = await D["db"]().rides.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"rides": [view(r, now, with_route=False) for r in docs]}


@router.get("/active")
async def active_ride(user=Depends(_user)):
    now = _now()
    r = await _active_for(user["user_id"], now)
    return {"ride": view(r, now, with_route=False) if r else None}


@router.get("/share/{token}")
async def shared(token: str, request: Request):
    D["rate_limit"]("rs:" + D["client_ip"](request), 90, 60)
    now = _now()
    ride = await D["db"]().rides.find_one({"share_token": _txt(token, 40)}, {"_id": 0})
    if not ride or now - float(ride["start_ts"]) > SHARE_TTL:
        raise _fail(404, "This ride link is not available any more.")
    st = eng.state_of(ride, now, for_owner=False)
    cap = st.get("captain")
    return {
        "mode": "DEMO", "demo_note": DEMO_NOTE,
        "vehicle": {"key": ride["vehicle"], "name": eng.VEHICLES[ride["vehicle"]]["name"]},
        "pickup": {"name": ride["pickup"]["name"], "lat": ride["pickup"]["lat"], "lng": ride["pickup"]["lng"]},
        "drop": {"name": ride["drop"]["name"], "lat": ride["drop"]["lat"], "lng": ride["drop"]["lng"]},
        "route": ride.get("route") or [],
        "state": {k: st.get(k) for k in ("stage", "headline", "eta_min", "vehicle_pos", "progress", "final")},
        "captain": {"first_name": cap["name"].split()[0], "vehicle_model": cap["vehicle_model"], "vehicle_color": cap["vehicle_color"], "plate": cap["plate"], "rating": cap["rating"]} if cap else None,
    }


@router.get("/{ride_id}")
async def get_ride(ride_id: str, request: Request, user=Depends(_user)):
    D["rate_limit"]("rg:" + user["user_id"], 240, 60)
    ride = await _own(ride_id, user)
    now = _now()
    await _remember_end(ride, now)
    return {"ride": view(ride, now)}


# ---------------------------------------------------------------- cancel
class CancelIn(BaseModel):
    reason: str = Field(default="", max_length=100)


@router.post("/{ride_id}/cancel")
async def cancel_ride(ride_id: str, body: CancelIn, user=Depends(_user)):
    ride = await _own(ride_id, user)
    now = _now()
    stage = eng.stage_at(ride, now)[0]
    if stage == "cancelled":
        return {"ride": view(ride, now), "already": True}
    if stage not in eng.CANCELLABLE:
        raise _fail(409, "This ride has already started or finished, so it cannot be cancelled." if stage != "completed" else "This ride is already completed.")
    fee = eng.cancel_fee(ride, stage, now)
    paid = ride["payment"].get("status") == "paid"
    info = {"at": datetime.fromtimestamp(now, timezone.utc).isoformat(), "by": "rider", "reason": _txt(body.reason, 100) or "No reason given",
            "fee": fee, "had_captain": stage in ("arriving", "arrived"), "stage": stage,
            "refund_demo": max(0, ride["fare"] + int(ride["payment"].get("tip") or 0) - fee) if paid else 0}
    res = await D["db"]().rides.update_one({"ride_id": ride["ride_id"], "cancelled": {"$exists": False}}, {"$set": {"cancelled": info, "status_final": "cancelled"}})
    ride["cancelled"] = info
    ride["status_final"] = "cancelled"
    if not getattr(res, "modified_count", 1):
        ride = await _own(ride_id, user)
    note = "Demo ride: no cancellation fee was charged." if fee else "Cancelled for free."
    return {"ride": view(ride, now), "fee_note": ("A fee of ₹%d would apply on a real ride. " % fee if fee else "") + note}


# ---------------------------------------------------------------- pay
class PayIn(BaseModel):
    method: str = Field(default="online", max_length=8)
    tip: int = Field(default=0, ge=0, le=500)
    start: bool = True          # false: only choose cash / online, do not start a payment yet


class VerifyIn(BaseModel):
    razorpay_order_id: str = Field(max_length=80)
    razorpay_payment_id: str = Field(max_length=80)
    razorpay_signature: str = Field(max_length=200)


def _razorpay_test_mode() -> bool:
    return D["razorpay"]() is not None and str(D["key_id"]()).startswith("rzp_test_")


@router.post("/{ride_id}/pay")
async def pay_ride(ride_id: str, body: PayIn, user=Depends(_user)):
    D["rate_limit"]("rpay:" + user["user_id"], 20, 60)
    ride = await _own(ride_id, user)
    now = _now()
    stage = eng.stage_at(ride, now)[0]
    if stage == "cancelled":
        raise _fail(409, "This ride was cancelled, so there is nothing to pay.")
    if body.method not in ("cash", "online"):
        raise _fail(400, "Choose cash or online payment.")
    if ride["payment"].get("status") == "paid":
        return {"mode": "paid", "ride": view(ride, now)}
    update: Dict[str, Any] = {"payment.method": body.method, "payment.tip": body.tip}
    out: Dict[str, Any] = {}
    if body.method == "cash":
        update["payment.status"] = "pending"
        out = {"mode": "cash"}
    elif not body.start:
        out = {"mode": "selected"}
    elif _razorpay_test_mode():
        import asyncio
        amount = ride["fare"] + body.tip
        try:
            order = await asyncio.to_thread(D["razorpay"]().order.create, {"amount": amount * 100, "currency": "INR", "receipt": ride["ride_id"],
                                                                         "notes": {"ride_id": ride["ride_id"], "service": "rides"}, "payment_capture": 1})
        except Exception as exc:
            logger.warning("ride payment order failed: %s", type(exc).__name__)
            raise _fail(502, "Payment could not be started. Please try again.")
        update["payment.order_id"] = order["id"]
        out = {"mode": "razorpay", "order_id": order["id"], "key_id": D["key_id"](), "amount_rupees": amount}
    else:
        out = {"mode": "demo", "amount_rupees": ride["fare"] + body.tip}
    await D["db"]().rides.update_one({"ride_id": ride["ride_id"]}, {"$set": update})
    ride["payment"].update({k.split(".", 1)[1]: v for k, v in update.items()})
    out["ride"] = view(ride, now)
    return out


@router.post("/{ride_id}/pay/confirm")
async def pay_confirm(ride_id: str, user=Depends(_user)):
    """Demo payment: nothing is charged. Not available when a real (test) payment order exists."""
    ride = await _own(ride_id, user)
    now = _now()
    if eng.stage_at(ride, now)[0] == "cancelled":
        raise _fail(409, "This ride was cancelled, so there is nothing to pay.")
    if ride["payment"].get("order_id"):
        raise _fail(409, "Complete the payment in the payment window.")
    if ride["payment"].get("method") != "online":
        raise _fail(409, "Choose online payment first.")
    if ride["payment"].get("status") != "paid":
        paid_at = datetime.fromtimestamp(now, timezone.utc).isoformat()
        await D["db"]().rides.update_one({"ride_id": ride["ride_id"]}, {"$set": {"payment.status": "paid", "payment.paid_at": paid_at, "payment.demo": True}})
        ride["payment"].update({"status": "paid", "paid_at": paid_at, "demo": True})
    return {"ride": view(ride, now)}


@router.post("/{ride_id}/pay/verify")
async def pay_verify(ride_id: str, body: VerifyIn, user=Depends(_user)):
    ride = await _own(ride_id, user)
    now = _now()
    secret = D["key_secret"]()
    if not secret:
        raise _fail(503, "Payments are not configured.")
    if ride["payment"].get("order_id") != body.razorpay_order_id:
        raise _fail(400, "Order mismatch")
    good = hmac.new(secret.encode(), f"{body.razorpay_order_id}|{body.razorpay_payment_id}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(good, body.razorpay_signature):
        raise _fail(400, "Invalid payment signature")
    paid_at = datetime.fromtimestamp(now, timezone.utc).isoformat()
    await D["db"]().rides.update_one({"ride_id": ride["ride_id"]}, {"$set": {"payment.status": "paid", "payment.paid_at": paid_at, "payment.payment_id": body.razorpay_payment_id}})
    ride["payment"].update({"status": "paid", "paid_at": paid_at})
    return {"ride": view(ride, now)}


# ---------------------------------------------------------------- rate and share
RATING_TAGS = ["Polite captain", "Smooth ride", "Safe driving", "On time", "Clean vehicle", "Good navigation", "Rash driving", "Late arrival", "Rude behaviour", "Vehicle not clean"]


class RateIn(BaseModel):
    stars: int = Field(ge=1, le=5)
    tags: List[str] = Field(default_factory=list, max_length=6)
    comment: str = Field(default="", max_length=300)


@router.post("/{ride_id}/rate")
async def rate_ride(ride_id: str, body: RateIn, user=Depends(_user)):
    ride = await _own(ride_id, user)
    now = _now()
    if eng.stage_at(ride, now)[0] != "completed":
        raise _fail(409, "You can rate a ride after it is completed.")
    if ride.get("rating"):
        raise _fail(409, "You have already rated this ride.")
    rating = {"stars": body.stars, "tags": [t for t in (_txt(x, 30) for x in body.tags) if t in RATING_TAGS][:5], "comment": _txt(body.comment, 300),
              "at": datetime.fromtimestamp(now, timezone.utc).isoformat()}
    await D["db"]().rides.update_one({"ride_id": ride["ride_id"], "rating": {"$exists": False}}, {"$set": {"rating": rating}})
    ride["rating"] = rating
    return {"ride": view(ride, now)}


@router.post("/{ride_id}/share")
async def share_ride(ride_id: str, user=Depends(_user)):
    ride = await _own(ride_id, user)
    now = _now()
    if eng.stage_at(ride, now)[0] in eng.FINAL:
        raise _fail(409, "Only a ride that is going on can be shared.")
    token = ride.get("share_token") or secrets.token_urlsafe(9)
    if not ride.get("share_token"):
        await D["db"]().rides.update_one({"ride_id": ride["ride_id"]}, {"$set": {"share_token": token}})
    return {"share_token": token}
