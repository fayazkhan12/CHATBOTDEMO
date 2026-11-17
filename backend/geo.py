"""Where the visitor means: an Indian pincode ("302017 me hotel") or the visitor's own location ("mere paas"), as
{"city", "lat", "long", "label", "kind"}. The city is what the company's destination search knows; the point is where the
hotels are measured from.

Sources (both free, no key):
- India Post (api.postalpincode.in): pincode -> post offices, district, state
- OpenStreetMap Nominatim: coordinates -> address (reverse), pincode -> coordinates (fallback). Its rules: at most one
  request a second and a User-Agent that names the app, so every answer is cached and calls are spaced out.
A visitor's coordinates are rounded to about 100 m and never stored or logged."""
import asyncio
import logging
import os
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger("destinoway.geo")

POSTAL_API = os.environ.get("POSTAL_API", "https://api.postalpincode.in").rstrip("/")
NOMINATIM = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org").rstrip("/")
USER_AGENT = os.environ.get("GEO_USER_AGENT", "DestinoWayChatbot/1.0 (+https://destinoway-chatbot-web.onrender.com)")
CACHE_SECONDS = 7 * 24 * 3600

_cache: Dict[str, Tuple[float, Any]] = {}
_osm_lock = asyncio.Lock()
_osm_last = [0.0]

# A 6-digit Indian pincode ("302017", "302 017", "pin 302017"), not a price ("₹302017", "302017 rs") and not part of a longer number.
_PIN = re.compile(r"(?<![\d.,₹])(?<!rs)(?<!rs\.)(?<!rs\s)([1-9]\d{2})\s?(\d{3})(?![\d,]|\s*(?:rs\b|rupe|₹|k\b|/-))", re.I)


def pincode_in(text: str) -> Optional[str]:
    """The pincode the visitor typed, or None."""
    m = _PIN.search(str(text or ""))
    return (m.group(1) + m.group(2)) if m else None


def strip_pincodes(text: str) -> str:
    """The text without pincodes (so "302017" is never read as a price)."""
    return _PIN.sub(" ", str(text or ""))


# "mere paas", "near me", "nearby", "yahin aas-paas", "meri location", "मेरे पास"
NEAR_ME = re.compile(
    r"\bnear\s*(?:me|by|my\s*(?:location|place))\b|\bnearby\b|\bclosest\s*to\s*me\b|\baround\s*me\b|"
    r"\bmere?\s*(?:paas|pass|pas|aas\s*-?\s*paas|nazdeek|najdeek|kareeb|karib|nearby)\b|\bmujhse\s*(?:paas|nazdeek)\b|"
    r"\byahi?n?\s*(?:ke\s*)?(?:paas|aas\s*-?\s*paas|nazdeek)\b|\bmeri\s*(?:location|lokesan|jagah)\b|\bcurrent\s*location\b|"
    r"मेरे\s*पास|मेरे\s*नज़?दीक|यहीं?\s*(?:के\s*)?(?:पास|आसपास)|मेरी\s*लोकेशन", re.I)


def wants_near_me(text: str) -> bool:
    return bool(NEAR_ME.search(str(text or "")))


def round_point(lat: Any, lng: Any) -> Optional[Tuple[float, float]]:
    """Coordinates rounded to ~100 m, or None when they are not a point in or near India."""
    try:
        la, lo = round(float(lat), 3), round(float(lng), 3)
    except (TypeError, ValueError):
        return None
    if not (5.0 <= la <= 38.0 and 67.0 <= lo <= 98.0):
        return None
    return la, lo


def _cached(key: str) -> Tuple[bool, Any]:
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return True, hit[1]
    return False, None


def _store(key: str, value: Any) -> Any:
    if len(_cache) > 5000:
        _cache.clear()
    _cache[key] = (time.time(), value)
    return value


async def _osm(path: str, params: Dict[str, Any]) -> Any:
    """One Nominatim call, at most one a second (their usage policy)."""
    async with _osm_lock:
        wait = 1.1 - (time.monotonic() - _osm_last[0])
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=5.0), headers={"User-Agent": USER_AGENT, "Accept-Language": "en"}) as c:
                r = await c.get(f"{NOMINATIM}/{path}", params={**params, "format": "jsonv2", "addressdetails": 1})
            return r.json() if r.status_code == 200 else None
        except Exception as exc:
            logger.warning("Nominatim %s failed: %s", path, type(exc).__name__)
            return None
        finally:
            _osm_last[0] = time.monotonic()


def _city_of(address: Dict[str, Any]) -> List[str]:
    """The names a city may go by in an OSM address, best first."""
    out: List[str] = []
    for key in ("city", "town", "state_district", "county", "city_district", "village", "municipality"):
        v = str(address.get(key) or "").strip()
        v = re.sub(r"\s+(?:District|Tehsil|Taluka|Division|Urban|Rural)$", "", v, flags=re.I).strip()
        if v and v not in out:
            out.append(v)
    return out


def _spot_of(address: Dict[str, Any]) -> str:
    for key in ("suburb", "neighbourhood", "quarter", "residential", "city_district", "village", "town"):
        v = str(address.get(key) or "").strip()
        if v:
            return v
    return ""


async def _post_offices(pin: str) -> Optional[Dict[str, Any]]:
    """India Post: {"district", "state", "names": [post office names]} for a pincode, or None."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=5.0), headers={"User-Agent": USER_AGENT}) as c:
            r = await c.get(f"{POSTAL_API}/pincode/{pin}")
        data = r.json() if r.status_code == 200 else None
    except Exception as exc:
        logger.warning("India Post lookup failed: %s", type(exc).__name__)
        return None
    first = data[0] if isinstance(data, list) and data else {}
    offices = first.get("PostOffice") if isinstance(first, dict) and first.get("Status") == "Success" else None
    if not offices:
        return None
    district = str(offices[0].get("District") or "").strip()
    names = [str(o.get("Name") or "").strip() for o in offices if o.get("Name")]
    # the post office in the city itself ("Malviya Nagar S.O") is the best point; a branch office (B.O) is often a village
    names.sort(key=lambda n: 0 if re.search(r"\bS\.?O\b|\bH\.?O\b", n) else 1)
    names = [re.sub(r"\s+(?:S\.?O|B\.?O|H\.?O|P\.?O)\.?$", "", n, flags=re.I).strip() for n in names]
    return {"district": district, "state": str(offices[0].get("State") or "").strip(), "names": list(dict.fromkeys(n for n in names if n))}


Destinations = Callable[[str], Awaitable[List[Dict[str, Any]]]]


async def _company_city(names: List[str], destinations: Destinations) -> Optional[Dict[str, Any]]:
    """The first of these names that the company's destination search knows as a city: its own label and centre."""
    for name in names:
        if not name:
            continue
        words = set(re.split(r"[\W_]+", name.casefold()))
        for d in await destinations(name):
            city_name = str(d.get("city") or d.get("label") or "").split(",")[0].strip().casefold()
            if str(d.get("type") or "").lower() in ("city", "multicity") and city_name and (
                    city_name == name.casefold() or city_name in words or str(d.get("label") or "").casefold().startswith(name.casefold())):
                c = d.get("coordinates") or {}
                try:
                    return {"city": str(d.get("city") or d.get("label")), "lat": float(c["lat"]), "long": float(c["long"])}
                except (KeyError, TypeError, ValueError):
                    return {"city": str(d.get("city") or d.get("label")), "lat": None, "long": None}
    return None


async def place_from_pincode(pin: str, destinations: Destinations,
                             resolve_area: Callable[[str, str], Awaitable[Optional[Dict[str, Any]]]]) -> Optional[Dict[str, Any]]:
    """A pincode as {"city", "lat", "long", "label", "kind": "pincode", "pincode"}, or None when it cannot be placed."""
    if not re.fullmatch(r"[1-9]\d{5}", pin or ""):
        return None
    hit, val = _cached(f"pin:{pin}")
    if hit:
        return val
    po = await _post_offices(pin)
    osm = await _osm("search", {"postalcode": pin, "countrycodes": "in", "limit": 1})
    osm0 = osm[0] if isinstance(osm, list) and osm else {}
    addr = osm0.get("address") or {}
    names = ([po["district"]] if po else []) + _city_of(addr)
    city = await _company_city(names, destinations)
    if not city:
        return _store(f"pin:{pin}", None)
    point: Optional[Dict[str, Any]] = None
    for office in (po or {}).get("names", [])[:4]:         # a post office the company knows as an area of the city: its own point
        found = await resolve_area(city["city"], office)
        label = str((found or {}).get("label") or "").casefold()
        if found and (office.casefold() in label or label.split(",")[0].strip() in office.casefold()):   # the same place, not a loose match
            point = found
            break
    if not point and osm0.get("lat"):
        try:
            point = {"label": _spot_of(addr) or (po or {}).get("names", [""])[0], "lat": float(osm0["lat"]), "long": float(osm0["lon"])}
        except (TypeError, ValueError):
            point = None
    spot = (point or {}).get("label") or ((po or {}).get("names") or [""])[0]
    out = {"city": city["city"], "kind": "pincode", "pincode": pin,
           "label": f"{spot} ({pin})" if spot else pin,
           "lat": round(point["lat"], 4) if point else city["lat"], "long": round(point["long"], 4) if point else city["long"],
           "exact": bool(point)}
    if out["lat"] is None:
        return _store(f"pin:{pin}", None)
    return _store(f"pin:{pin}", out)


async def place_from_point(lat: Any, lng: Any, destinations: Destinations) -> Optional[Dict[str, Any]]:
    """The visitor's own location as {"city", "lat", "long", "label", "kind": "gps"}, or None (outside India, unknown city)."""
    pt = round_point(lat, lng)
    if not pt:
        return None
    key = f"pt:{pt[0]:.3f},{pt[1]:.3f}"
    hit, val = _cached(key)
    if hit:
        return val
    rev = await _osm("reverse", {"lat": pt[0], "lon": pt[1], "zoom": 14})
    addr = (rev or {}).get("address") or {}
    city = await _company_city(_city_of(addr), destinations) if addr else None
    if not city:
        return _store(key, None)
    return _store(key, {"city": city["city"], "kind": "gps", "label": _spot_of(addr) or city["city"], "lat": pt[0], "long": pt[1]})
