"""Ride maths and the ride's life story. Pure functions: no database, no network, no clock of their own
(the caller passes `now`), so every rule here can be tested by simply calling it.

A DEMO ride has no real driver. The "captain" is generated from the ride id and walks through the stages
(finding a captain, on the way, arrived, trip, completed) according to the time that has passed since the
ride started. Nothing is stored for the stages: the stage is always worked out from the start time, so it
cannot get stuck and a page reload shows the same truth.
"""
import hashlib
import math
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------- vehicles and fares
# base + per km + per minute, never below `minimum`; `max_km` is how far this vehicle takes you;
# cabs charge `per_km_long` for every km after the first LONG_AFTER_KM (outstation).
VEHICLES: Dict[str, Dict[str, Any]] = {
    "bike": {"name": "Bike", "group": "bike", "tagline": "Fastest through traffic", "seats": 1, "base": 20, "per_km": 6.5, "per_min": 0.6,
             "minimum": 30, "max_km": 45, "eta": (2, 7), "speed": 1.12, "cancel_fee": 10},
    "auto": {"name": "Auto", "group": "auto", "tagline": "Easy, affordable rides", "seats": 3, "base": 30, "per_km": 11.0, "per_min": 1.0,
             "minimum": 45, "max_km": 45, "eta": (3, 9), "speed": 0.92, "cancel_fee": 15},
    "mini": {"name": "Cab Economy", "group": "cab", "tagline": "Hatchback, AC", "seats": 4, "base": 45, "per_km": 12.5, "per_min": 1.2,
             "minimum": 80, "max_km": 600, "per_km_long": 11.0, "eta": (4, 11), "speed": 1.0, "cancel_fee": 25},
    "sedan": {"name": "Cab Premier", "group": "cab", "tagline": "Sedan, extra legroom", "seats": 4, "base": 55, "per_km": 15.0, "per_min": 1.5,
              "minimum": 110, "max_km": 600, "per_km_long": 13.5, "eta": (5, 13), "speed": 1.0, "cancel_fee": 30},
    "suv": {"name": "Cab XL", "group": "cab", "tagline": "SUV for 6, with luggage space", "seats": 6, "base": 80, "per_km": 19.0, "per_min": 1.9,
            "minimum": 170, "max_km": 600, "per_km_long": 17.0, "eta": (6, 14), "speed": 1.0, "cancel_fee": 40},
}
ORDER = ["bike", "auto", "mini", "sedan", "suv"]
LONG_AFTER_KM = 30.0
GST = 0.05
MIN_KM = 0.15
MAX_KM = 600.0
ROAD_FACTOR = 1.3


def group_of(vehicle: str) -> str:
    return VEHICLES.get(vehicle, {}).get("group", "")


def matches_wish(vehicle_key: str, wish: str) -> bool:
    """The chat asks for `bike`, `auto`, `cab` or `any`."""
    if wish in ("", "any", None):
        return True
    return VEHICLES[vehicle_key]["group"] == wish or vehicle_key == wish


# ---------------------------------------------------------------- distance and route
def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def in_india(lat: float, lng: float) -> bool:
    return 6.0 <= lat <= 37.5 and 67.5 <= lng <= 98.5


def fallback_route(a: Tuple[float, float], b: Tuple[float, float], steps: int = 24) -> Dict[str, Any]:
    """No routing service: a gently curved line and an honest road estimate (straight line x 1.3)."""
    straight = haversine_km(a, b)
    km = round(max(straight * ROAD_FACTOR, 0.1), 2)
    speed = 22.0 if km <= 15 else 32.0 if km <= 50 else 48.0
    minutes = max(3.0, km / speed * 60.0)
    (la1, lo1), (la2, lo2) = a, b
    # bend the line sideways by ~8% of its length so it does not look like a ruler on the map
    mx, my = (la1 + la2) / 2, (lo1 + lo2) / 2
    dx, dy = (la2 - la1), (lo2 - lo1)
    cx, cy = mx - dy * 0.08, my + dx * 0.08
    pts = []
    for i in range(steps + 1):
        t = i / steps
        pts.append([round((1 - t) ** 2 * la1 + 2 * (1 - t) * t * cx + t ** 2 * la2, 6), round((1 - t) ** 2 * lo1 + 2 * (1 - t) * t * cy + t ** 2 * lo2, 6)])
    return {"points": pts, "distance_km": km, "duration_min": round(minutes, 1), "source": "estimate"}


def decimate(points: List[List[float]], limit: int = 140) -> List[List[float]]:
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    out = [points[int(round(i * step))] for i in range(limit)]
    out[-1] = points[-1]
    return out


def path_length_km(points: List[List[float]]) -> float:
    return sum(haversine_km((p[0], p[1]), (q[0], q[1])) for p, q in zip(points, points[1:]))


def point_along(points: List[List[float]], fraction: float) -> Tuple[float, float]:
    """The place `fraction` (0..1) of the way along a line."""
    if not points:
        return (0.0, 0.0)
    if len(points) == 1 or fraction <= 0:
        return (points[0][0], points[0][1])
    if fraction >= 1:
        return (points[-1][0], points[-1][1])
    legs = [haversine_km((p[0], p[1]), (q[0], q[1])) for p, q in zip(points, points[1:])]
    total = sum(legs) or 1e-9
    want = fraction * total
    done = 0.0
    for (p, q), leg in zip(zip(points, points[1:]), legs):
        if done + leg >= want:
            t = (want - done) / leg if leg else 0.0
            return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)
        done += leg
    return (points[-1][0], points[-1][1])


# ---------------------------------------------------------------- time of day and surge
def to_ist(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, IST)


def surge_at(ts: float) -> Dict[str, Any]:
    """Busy hours cost a little more. Decided by the time the ride is for, in India."""
    t = to_ist(ts)
    minutes = t.hour * 60 + t.minute
    if 8 * 60 <= minutes < 10 * 60 + 30 and t.weekday() < 5:
        return {"multiplier": 1.2, "label": "Morning rush: fares are 1.2x"}
    if 17 * 60 + 30 <= minutes < 21 * 60:
        return {"multiplier": 1.25 if t.weekday() < 5 else 1.15, "label": "Evening rush: fares are %sx" % ("1.25" if t.weekday() < 5 else "1.15")}
    if minutes >= 23 * 60 or minutes < 5 * 60:
        return {"multiplier": 1.15, "label": "Night ride: fares are 1.15x"}
    return {"multiplier": 1.0, "label": ""}


# ---------------------------------------------------------------- fares
def vehicle_minutes(vehicle: str, duration_min: float) -> int:
    return max(2, int(round(duration_min / VEHICLES[vehicle]["speed"])))


def fare(vehicle: str, km: float, minutes: float, surge: float = 1.0) -> Dict[str, Any]:
    v = VEHICLES[vehicle]
    near = min(km, LONG_AFTER_KM)
    far = max(0.0, km - LONG_AFTER_KM)
    distance_part = near * v["per_km"] + far * v.get("per_km_long", v["per_km"])
    raw = v["base"] + distance_part + minutes * v["per_min"]
    base_fare = max(raw, v["minimum"])
    subtotal = base_fare * surge
    gst = subtotal * GST
    total = int(round(subtotal + gst))
    return {
        "base": round(v["base"]), "distance": round(distance_part), "time": round(minutes * v["per_min"]),
        "minimum_applied": raw < v["minimum"], "surge_multiplier": surge,
        "surge_amount": round(subtotal - base_fare), "gst": round(gst), "total": total,
    }


def eta_minutes(vehicle: str, seed: str) -> int:
    lo, hi = VEHICLES[vehicle]["eta"]
    rnd = random.Random(int(hashlib.sha1(("eta|" + seed + "|" + vehicle).encode()).hexdigest()[:10], 16))
    return rnd.randint(lo, hi)


def options_for(km: float, duration_min: float, ts: float, seed: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Every vehicle with its fare and pickup time, for the ride that starts at `ts`."""
    s = surge_at(ts)
    out = []
    for key in ORDER:
        v = VEHICLES[key]
        mins = vehicle_minutes(key, duration_min)
        item = {"key": key, "name": v["name"], "group": v["group"], "tagline": v["tagline"], "seats": v["seats"],
                "eta_min": eta_minutes(key, seed), "duration_min": mins}
        if km > v["max_km"]:
            item.update({"available": False, "reason": "%s rides go up to %d km. Pick a cab for this distance." % (v["name"], v["max_km"]), "fare": 0})
        else:
            f = fare(key, km, mins, s["multiplier"])
            item.update({"available": True, "fare": f["total"], "breakdown": f})
        out.append(item)
    return out, s


# ---------------------------------------------------------------- the captain
_FIRST = ["Ramesh", "Suresh", "Mahesh", "Rajesh", "Dinesh", "Anil", "Sunil", "Vijay", "Ajay", "Sanjay", "Manoj", "Deepak", "Pradeep", "Rakesh",
          "Mukesh", "Naresh", "Imran", "Salman", "Farhan", "Arjun", "Karan", "Rohit", "Amit", "Sandeep", "Harish", "Gopal", "Mohan", "Kishan"]
_LAST = ["K", "S", "R", "M", "P", "D", "B", "G", "T", "V", "N", "Y"]
_MODELS = {
    "bike": ["Honda Shine", "Hero Splendor", "Bajaj Pulsar", "TVS Apache", "Honda Activa", "Suzuki Access"],
    "auto": ["Bajaj RE auto (CNG)", "Piaggio Ape auto (CNG)", "Mahindra Treo auto (electric)"],
    "mini": ["Maruti WagonR", "Hyundai Santro", "Tata Tiago", "Maruti Celerio"],
    "sedan": ["Maruti Dzire", "Honda Amaze", "Hyundai Aura", "Tata Tigor"],
    "suv": ["Toyota Innova", "Maruti Ertiga", "Kia Carens"],
}
_COLORS = ["White", "Black", "Silver", "Grey", "Red", "Blue"]


def captain_for(ride_id: str, vehicle: str, plate_prefix: str = "DL1C") -> Dict[str, Any]:
    rnd = random.Random(int(hashlib.sha1(("cap|" + ride_id).encode()).hexdigest()[:12], 16))
    color = "Yellow and green" if vehicle == "auto" else rnd.choice(_COLORS)
    return {
        "name": "%s %s." % (rnd.choice(_FIRST), rnd.choice(_LAST)),
        "rating": round(rnd.uniform(4.62, 4.96), 2),
        "trips": rnd.randint(850, 9400),
        "vehicle_model": rnd.choice(_MODELS[vehicle]),
        "vehicle_color": color,
        "plate": "%s %s%s %04d" % (plate_prefix, rnd.choice("ABCDEFGHJKLMNPRSTUVW"), rnd.choice("ABCDEFGHJKLMNPRSTUVW"), rnd.randint(1, 9999)),
        "photo_seed": rnd.randint(1, 99),
    }


def captain_start(pickup: Tuple[float, float], eta_min: int, ride_id: str) -> Tuple[float, float]:
    """Where the captain is when they accept: about the road a trip of `eta_min` minutes would cover, in some direction."""
    rnd = random.Random(int(hashlib.sha1(("pos|" + ride_id).encode()).hexdigest()[:12], 16))
    km = max(0.4, eta_min * 0.35)
    ang = rnd.uniform(0, 2 * math.pi)
    dlat = (km * math.cos(ang)) / 111.2
    dlng = (km * math.sin(ang)) / (111.2 * max(0.2, math.cos(math.radians(pickup[0]))))
    return (round(pickup[0] + dlat, 6), round(pickup[1] + dlng, 6))


# ---------------------------------------------------------------- the life of a ride
PHASE_SCALE = float(os.environ.get("RIDE_PHASE_SCALE", "1") or 1)


def timeline_for(ride_id: str, eta_min: int, duration_min: float) -> Dict[str, float]:
    """How many real seconds each stage takes. Short enough to watch a whole ride in a couple of minutes."""
    rnd = random.Random(int(hashlib.sha1(("time|" + ride_id).encode()).hexdigest()[:12], 16))
    scale = PHASE_SCALE
    return {
        "searching_s": round(rnd.uniform(5, 9) * scale, 1),
        "arriving_s": round(min(50.0, max(18.0, eta_min * 5.0 + rnd.uniform(-2, 4))) * scale, 1),
        "arrived_s": round(8.0 * scale, 1),
        "trip_s": round(min(150.0, max(40.0, duration_min * 6.0)) * scale, 1),
    }


FINAL = ("completed", "cancelled")
CANCELLABLE = ("scheduled", "searching", "arriving", "arrived")


def stage_at(ride: Dict[str, Any], now: float) -> Tuple[str, float]:
    """(stage, 0..1 progress through that stage). Stages: scheduled, searching, arriving, arrived, in_progress, completed, cancelled."""
    if ride.get("cancelled"):
        return "cancelled", 1.0
    tl = ride["timeline"]
    start = float(ride["start_ts"])
    if now < start:
        return "scheduled", 0.0
    t = now - start
    for name, key in (("searching", "searching_s"), ("arriving", "arriving_s"), ("arrived", "arrived_s"), ("in_progress", "trip_s")):
        length = float(tl[key])
        if t < length:
            return name, max(0.0, min(1.0, t / length if length else 1.0))
        t -= length
    return "completed", 1.0


def total_seconds(ride: Dict[str, Any]) -> float:
    tl = ride["timeline"]
    return float(tl["searching_s"] + tl["arriving_s"] + tl["arrived_s"] + tl["trip_s"])


def cancel_fee(ride: Dict[str, Any], stage: str, now: float) -> int:
    """Free while we are still finding a captain and just after one accepts; after that the
    captain's time costs a small fee. Demo rides never charge it."""
    if stage in ("scheduled", "searching"):
        return 0
    base = VEHICLES[ride["vehicle"]]["cancel_fee"]
    if stage == "arriving" and stage_at(ride, now)[1] <= 0.3:   # the first moments after a captain accepts
        return 0
    return base * 2 if stage == "arrived" else base


def state_of(ride: Dict[str, Any], now: float, for_owner: bool = True) -> Dict[str, Any]:
    """Everything a screen needs to draw the ride right now."""
    stage, progress = stage_at(ride, now)
    route = ride.get("route") or []
    pickup = (ride["pickup"]["lat"], ride["pickup"]["lng"])
    drop = (ride["drop"]["lat"], ride["drop"]["lng"])
    cap_start = tuple(ride.get("captain_start") or pickup)
    tl = ride["timeline"]
    vehicle_pos: Optional[Tuple[float, float]] = None
    eta_min: Optional[int] = None
    headline = ""
    if stage == "scheduled":
        headline = "Your ride is booked. We find a captain a few minutes before pickup."
        eta_min = max(0, int(math.ceil((float(ride["start_ts"]) - now) / 60)))
    elif stage == "searching":
        headline = "Finding a captain near you"
    elif stage == "arriving":
        vehicle_pos = (cap_start[0] + (pickup[0] - cap_start[0]) * progress, cap_start[1] + (pickup[1] - cap_start[1]) * progress)
        left = (1 - progress) * ride["eta_min"]
        eta_min = max(1, int(math.ceil(left))) if progress < 1 else 0
        headline = "Captain is on the way"
    elif stage == "arrived":
        vehicle_pos = pickup
        headline = "Captain has arrived. Share the OTP to start the ride."
    elif stage == "in_progress":
        vehicle_pos = point_along(route, progress) if route else (pickup[0] + (drop[0] - pickup[0]) * progress, pickup[1] + (drop[1] - pickup[1]) * progress)
        eta_min = max(1, int(math.ceil((1 - progress) * ride["duration_min"])))
        headline = "On the way to your drop"
    elif stage == "completed":
        vehicle_pos = drop
        headline = "You have reached your drop. Hope you had a smooth ride."
    elif stage == "cancelled":
        headline = "Ride cancelled"
    assigned = stage in ("arriving", "arrived", "in_progress", "completed") or (stage == "cancelled" and ride["cancelled"].get("had_captain"))
    out: Dict[str, Any] = {
        "stage": stage, "progress": round(progress, 3), "headline": headline, "eta_min": eta_min,
        "captain": ride["captain"] if assigned else None,
        "vehicle_pos": [round(vehicle_pos[0], 6), round(vehicle_pos[1], 6)] if vehicle_pos else None,
        "can_cancel": stage in CANCELLABLE, "final": stage in FINAL,
        "cancel_fee": cancel_fee(ride, stage, now) if stage in CANCELLABLE else 0,
        "seconds_left": max(0, int(math.ceil(float(ride["start_ts"]) + total_seconds(ride) - now))) if stage not in FINAL else 0,
    }
    if for_owner and stage in ("arriving", "arrived"):
        out["otp"] = ride["otp"]
    if stage == "in_progress" or stage == "completed":
        out["otp_verified"] = True
    return out
