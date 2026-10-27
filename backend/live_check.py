"""Is the live hotel data still in the shape the chatbot expects?

Run from the backend folder (needs the same .env / venv as the server):

    python live_check.py                       # Jaipur, 14 days from now, 2 nights
    python live_check.py --json                # also print the cleaned result
    python live_check.py --location-id 227736 --lat 26.912428 --long 75.78727

It searches real hotels on the company API, opens the first available hotel, passes the answer
through the same cleaning code the website uses and tells you PASS or FAIL.
Nothing is booked, no login is needed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import date, timedelta
from typing import Any, Dict, Optional

import httpx

import hotel_live as hl


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        here = os.path.dirname(os.path.abspath(__file__))
        for p in (os.path.join(here, ".env"), os.path.join(here, "..", ".env")):
            if os.path.exists(p):
                load_dotenv(p)
    except ImportError:
        pass


def find_search_id(body: Any) -> str:
    """Node puts searchId under `message` (an object) today; accept `data` too, in case they fix it."""
    for key in ("message", "data"):
        v = body.get(key) if isinstance(body, dict) else None
        if isinstance(v, dict) and isinstance(v.get("searchId"), str):
            return v["searchId"]
    m = re.search(r'"searchId"\s*:\s*"([^"]+)"', json.dumps(body))
    return m.group(1) if m else ""


def pick_hotel(results: Any) -> Optional[Dict[str, Any]]:
    items = hl._dig(results, "data", "items") or []
    for it in items:
        if isinstance(it, dict) and it.get("supplierHotelId") and not it.get("isSoldOut"):
            return it
    return None


def run(client: httpx.Client, args: argparse.Namespace) -> int:
    api = args.api.rstrip("/") + "/api/v1"
    checkin = date.today() + timedelta(days=args.days_ahead)
    body = {
        "locationId": str(args.location_id),
        "geoCode": {"lat": str(args.lat), "long": str(args.long)},
        "checkIn": checkin.isoformat(),
        "checkOut": (checkin + timedelta(days=args.nights)).isoformat(),
        "rooms": [{"adults": 2, "children": 0, "childAges": []}],
        "nationality": "IN",
    }
    print(f"1. Searching hotels ({body['checkIn']} -> {body['checkOut']}) ...")
    r = client.post(f"{api}/hotelSearch/search", json=body)
    r.raise_for_status()
    sid = find_search_id(r.json())
    if not sid:
        print("FAIL: no searchId in the search response")
        return 1
    results: Any = {}
    for _ in range(args.polls):
        time.sleep(args.poll_wait)
        rr = client.get(f"{api}/hotelSearch/search/{sid}")
        rr.raise_for_status()
        results = rr.json()
        if hl._dig(results, "data", "status") == "completed":
            break
    hotel = pick_hotel(results)
    if not hotel:
        print("FAIL: search finished but no available hotel came back")
        return 1
    hid = str(hotel["supplierHotelId"])
    print(f"2. Opening hotel {hotel.get('name')} ({hid})")

    async def go() -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=30, transport=args._transport) as ac:
            return await hl.fetch_details(ac, f"{api}/hotelDetails/search", sid, hid, args.nights)

    data = asyncio.run(go())
    c = data["content"] or {}
    print(f"3. Hotel   : {c.get('name')}  {c.get('star_rating')}*  {c.get('city')}")
    print(f"   Photos  : {len(c.get('images', []))}   Amenities: {len(c.get('amenities', []))}   Nearby: {len(c.get('nearby', []))}")
    print(f"4. Rooms   : {len(data['rooms'])}  (cheapest Rs {data['from_price']})")
    for rm in data["rooms"]:
        print(f"   - {rm['name'][:34]:34} | {rm['board'] or '-':12} | {rm['cancellation'][:34]:34} | Rs {rm['price']['total']}")
    for w in data["warnings"]:
        print("   warning:", w)
    ok = bool(c.get("name")) and bool(data["rooms"]) and not data["warnings"]
    if args.json:
        print(json.dumps(data, indent=1, ensure_ascii=False))
    print("\nRESULT:", "PASS - live data matches what the chatbot expects" if ok else "FAIL - see warnings above")
    return 0 if ok else 1


def main() -> int:
    _load_env()
    try:  # hotel names can hold characters a Windows console cannot show; never crash on them
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default=os.environ.get("NODE_API_BASE") or os.environ.get("AKBAR_API_HOST") or "https://api-dev.destinoway.com")
    ap.add_argument("--location-id", default="227736")
    ap.add_argument("--lat", default="26.912428")
    ap.add_argument("--long", default="75.78727")
    ap.add_argument("--days-ahead", type=int, default=14)
    ap.add_argument("--nights", type=int, default=2)
    ap.add_argument("--polls", type=int, default=12)
    ap.add_argument("--poll-wait", type=float, default=4.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    args._transport = None
    try:
        with httpx.Client(timeout=40) as client:
            return run(client, args)
    except httpx.HTTPError as exc:
        print(f"FAIL: could not reach the API ({type(exc).__name__}: {exc})")
        return 2


if __name__ == "__main__":
    sys.exit(main())
