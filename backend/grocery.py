"""DestinoWay Grocery: a Blinkit-style quick-delivery store (DEMO).

    GET  /api/grocery/catalog          categories and every item (public)
    GET  /api/grocery/search?q=        items matching a word, in English, Hindi or Hinglish (public)
    POST /api/grocery/quote            the bill for a cart, worked out by the server (public)
    POST /api/grocery/match            "2 milk, bread, aloo" -> items with quantities (the chat uses it)
    POST /api/grocery/orders           place an order (login needed)
    GET  /api/grocery/orders           my orders
    GET  /api/grocery/orders/active    my order that is still on its way
    GET  /api/grocery/orders/{id}      live state of one order (owner only)
    POST /api/grocery/orders/{id}/cancel

These are DEMO orders: no shop packs anything and no rider comes. The stages are worked out from the time that has passed
(see stage_of) and every answer says so. Nothing is charged. Prices always come from the server's shelf, never from the browser.
"""
import hashlib
import hmac
import logging
import re
import secrets
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

try:
    import grocery_catalog as cat
except ImportError:  # started as backend.server
    from backend import grocery_catalog as cat

logger = logging.getLogger("grocery")
router = APIRouter(prefix="/api/grocery")

DEMO_NOTE = "Demo order: no shop packs anything, no rider comes and nothing is charged."
D: Dict[str, Any] = {}
_now: Callable[[], float] = time.time     # tests replace this with a fake clock


def setup(*, db: Callable[[], Any], current_user: Callable, optional_user: Callable, rate_limit: Callable, client_ip: Callable, secret: str) -> None:
    D.update(db=db, current_user=current_user, optional_user=optional_user, rate_limit=rate_limit, client_ip=client_ip, secret=secret)


async def _user(request: Request) -> Dict[str, Any]:
    return await D["current_user"](request)


def _fail(code: int, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=code, detail={"message": message, **extra} if extra else message)


_CTRL = re.compile(r"[\x00-\x1f\x7f<>]")


def _txt(x: Any, n: int = 80) -> str:
    return re.sub(r"\s+", " ", _CTRL.sub(" ", str(x if x is not None else ""))).strip()[:n]


# ---------------------------------------------------------------- search
_WORD = re.compile(r"[a-z0-9ऀ-ॿ]+")
# Hindi (Devanagari) words people say or type, mapped to the Roman words the shelf knows
_DEVANAGARI = {"दूध": "doodh", "दही": "dahi", "आलू": "aloo", "प्याज": "pyaaz", "टमाटर": "tamatar", "चावल": "chawal", "आटा": "atta",
               "दाल": "dal", "चीनी": "cheeni", "नमक": "namak", "तेल": "tel", "अंडे": "ande", "अंडा": "anda", "ब्रेड": "bread",
               "पनीर": "paneer", "मक्खन": "makhan", "घी": "ghee", "केला": "kela", "सेब": "seb", "पानी": "pani", "चाय": "chai",
               "बिस्कुट": "biscuit", "साबुन": "sabun", "मैगी": "maggi", "धनिया": "dhania", "अदरक": "adrak", "लहसुन": "lehsun",
               "नींबू": "nimbu", "पालक": "palak", "गाजर": "gajar", "मटर": "matar", "शहद": "shahad"}
_NUMBERS = {"one": 1, "ek": 1, "two": 2, "do": 2, "three": 3, "teen": 3, "tin": 3, "four": 4, "char": 4, "chaar": 4, "five": 5,
            "paanch": 5, "panch": 5, "six": 6, "chhe": 6, "seven": 7, "saat": 7, "eight": 8, "aath": 8, "nine": 9, "nau": 9, "ten": 10, "das": 10,
            "a": 1, "an": 1, "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10}
_FILLER = {"of", "packet", "packets", "pack", "pcs", "piece", "pieces", "kg", "g", "gm", "gram", "grams", "l", "litre", "liter", "ml", "dozen",
           "some", "the", "and", "aur", "please", "plz", "wala", "wali", "ka", "ki", "ke", "chahiye", "chahie", "do", "dena", "mangwao", "mangwa"}
_INDEX: List[Tuple[Dict[str, Any], set, set, set]] = []


def _tokens(s: str) -> List[str]:
    s = str(s or "").lower()
    for dv, ro in _DEVANAGARI.items():
        s = s.replace(dv, f" {ro} ")
    return _WORD.findall(s)


def _build_index() -> None:
    _INDEX.clear()
    for it in cat.ITEMS:
        name_tokens = set(_tokens(it["name"]))
        alias_tokens = set(_tokens(it["aliases"]))
        cat_tokens = set(_tokens(next((c["name"] for c in cat.CATEGORIES if c["id"] == it["category"]), "")))
        _INDEX.append((it, name_tokens, alias_tokens, cat_tokens))


_build_index()


def _score(q_tokens: List[str], name_tokens: set, alias_tokens: set, cat_tokens: set = frozenset()) -> float:
    total = 0.0
    for t in q_tokens:
        if t in name_tokens:
            total += 3
        elif t in alias_tokens:
            total += 3
        elif t in cat_tokens:
            total += 1          # "snacks", "dairy": the whole shelf
        elif len(t) >= 3 and any(w.startswith(t) for w in name_tokens):
            total += 1.5
        elif len(t) >= 4 and any(w.startswith(t) for w in alias_tokens):
            total += 1
        elif len(t) >= 4 and any(t.startswith(w) and len(w) >= 4 for w in name_tokens):
            total += 1          # "eggs" finds "egg", "tomatoes" finds "tomato"
        else:
            return 0.0          # every word of the search must mean something
    return total


def search(q: str, limit: int = 40) -> List[Dict[str, Any]]:
    toks = [t for t in _tokens(q) if t not in _FILLER]
    if not toks:
        return []
    scored = []
    for it, nt, at, ct in _INDEX:
        s = _score(toks, nt, at, ct)
        if s:
            scored.append((-s, len(it["name"]), it["name"], it))
    scored.sort(key=lambda x: x[:3])
    return [cat.public(x[3]) for x in scored[:limit]]


def parse_line(line: str) -> Tuple[int, str]:
    """'2 milk' -> (2, 'milk'); 'do packet doodh' -> (2, 'doodh packet'); 'bread' -> (1, 'bread'). A weight such as '1 kg aloo' is not a count."""
    words = _tokens(line)
    qty, rest, units = 1, [], {"kg", "g", "gm", "gram", "grams", "l", "litre", "liter", "ml"}
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else ""
        if w.isdigit() and nxt not in units and 1 <= int(w) <= cat.MAX_QTY and qty == 1 and not rest:
            qty = int(w)
        elif w in _NUMBERS and not rest and qty == 1 and nxt not in units and len(words) > 1 and w not in ("a", "an"):
            qty = _NUMBERS[w]
        elif w.isdigit() or w in units:
            continue
        else:
            rest.append(w)
    return qty, " ".join(rest)


def match(lines: List[str]) -> Dict[str, Any]:
    found: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []
    for raw in lines[:20]:
        qty, words = parse_line(_txt(raw, 80))
        hits = search(words, 1) if words else []
        if not hits:
            missing.append(_txt(raw, 40))
            continue
        h = hits[0]
        cur = found.get(h["id"])
        if cur:
            cur["qty"] = min(cat.MAX_QTY, cur["qty"] + qty)
        else:
            found[h["id"]] = {**h, "qty": qty}
    return {"items": list(found.values()), "missing": missing}


# ---------------------------------------------------------------- the bill
def bill_for(lines: List[Dict[str, Any]], coupon: str = "") -> Dict[str, Any]:
    """lines: [{id, qty}] -> everything the shopper sees, from the shelf's own prices."""
    if not isinstance(lines, list) or not lines:
        raise _fail(400, "Your cart is empty.")
    if len(lines) > cat.MAX_LINES:
        raise _fail(400, "That is too many different items for one order.")
    merged: Dict[str, int] = {}
    for ln in lines:
        iid = _txt(ln.get("id") if isinstance(ln, dict) else "", 60)
        try:
            qty = int(ln.get("qty"))
        except (TypeError, ValueError, AttributeError):
            raise _fail(400, "Please check the quantities.")
        if iid not in cat.BY_ID:
            raise _fail(400, "One of the items is not on our shelf any more.", item=iid)
        if not 1 <= qty <= cat.MAX_QTY:
            raise _fail(400, f"You can order up to {cat.MAX_QTY} of one item.")
        merged[iid] = min(cat.MAX_QTY, merged.get(iid, 0) + qty)
    out, items_total, mrp_total, count = [], 0, 0, 0
    for iid, qty in merged.items():
        it = cat.BY_ID[iid]
        out.append({**cat.public(it), "qty": qty, "line_total": it["price"] * qty})
        items_total += it["price"] * qty
        mrp_total += it["mrp"] * qty
        count += qty
    delivery = 0 if items_total >= cat.FREE_DELIVERY_FROM else cat.DELIVERY_FEE
    small = cat.SMALL_CART_FEE if items_total < 99 else 0
    code = _txt(coupon, 20).upper()
    discount, coupon_note = 0, ""
    if code:
        c = cat.COUPONS.get(code)
        if not c:
            coupon_note = "This coupon code is not valid."
            code = ""
        elif items_total < c["min"]:
            coupon_note = f"Add items worth Rs {c['min'] - items_total} more to use {code}."
            code = ""
        else:
            discount = c["off"]
            coupon_note = f"{code} applied: Rs {discount} off."
    total = items_total + delivery + small + cat.HANDLING_FEE - discount
    return {"lines": out, "count": count, "items_total": items_total, "savings": mrp_total - items_total + discount,
            "delivery_fee": delivery, "small_cart_fee": small, "handling_fee": cat.HANDLING_FEE, "discount": discount,
            "coupon": code, "coupon_note": coupon_note, "total": total, "min_order": cat.MIN_ORDER,
            "free_delivery_from": cat.FREE_DELIVERY_FROM, "currency": "INR", "demo": True, "note": DEMO_NOTE}


# ---------------------------------------------------------------- the order and its stages
STEPS = [("placed", "Order placed"), ("packing", "Packing your items"), ("picked", "Rider picked up your order"),
         ("on_the_way", "On the way"), ("delivered", "Delivered")]
_FIRST = ["Rohit", "Aman", "Imran", "Suresh", "Vikram", "Deepak", "Arjun", "Sandeep", "Rahul", "Manoj"]
_LAST = ["Sharma", "Khan", "Yadav", "Singh", "Verma", "Meena", "Gupta", "Joshi"]


def _h(order_id: str, salt: str) -> int:
    return int(hmac.new(D.get("secret", "demo").encode() if isinstance(D.get("secret"), str) else b"demo", f"{order_id}|{salt}".encode(), hashlib.sha256).hexdigest(), 16)


def eta_minutes(order_id: str) -> int:
    return 8 + _h(order_id, "eta") % 7          # 8 to 14 minutes


def rider_of(order_id: str) -> Dict[str, Any]:
    n = _h(order_id, "rider")
    return {"name": f"{_FIRST[n % len(_FIRST)]} {_LAST[(n // 7) % len(_LAST)]}", "vehicle": f"Bike RJ14 {1000 + n % 9000}",
            "phone": f"+91 9{n % 10}{(n // 10) % 10}** **{(n // 100) % 10}{(n // 1000) % 10}{(n // 10000) % 10}", "rating": round(4.5 + (n % 5) / 10, 1)}


def otp_of(order_id: str) -> str:
    return f"{_h(order_id, 'otp') % 10000:04d}"


def stage_of(order: Dict[str, Any], now: float) -> Dict[str, Any]:
    """What the order looks like now, from the time passed since it was placed."""
    total = float(order["eta_min"]) * 60
    t = max(0.0, now - float(order["created_at"]))
    if order.get("status") == "cancelled":
        return {"stage": "cancelled", "step": -1, "headline": "Order cancelled", "eta_left_min": 0, "progress": 0.0}
    cuts = [15.0, total * 0.38, total * 0.45, total]      # placed | packing | picked | on the way | delivered
    step = sum(1 for c in cuts if t >= c)
    stage = STEPS[step][0]
    left = max(0, int(-(-(total - t) // 60))) if t < total else 0
    heads = {"placed": "Order placed, finding a shop", "packing": "Your items are being packed",
             "picked": "Rider has your order", "on_the_way": f"Arriving in {max(1, left)} min", "delivered": "Delivered. Enjoy!"}
    progress = 1.0 if stage == "delivered" else round(min(0.97, t / total), 3)
    return {"stage": stage, "step": step, "headline": heads[stage], "eta_left_min": left, "progress": progress,
            "can_cancel": step < 2}


def view(order: Dict[str, Any], now: float, owner: bool = True) -> Dict[str, Any]:
    st = stage_of(order, now)
    out = {"order_id": order["order_id"], "state": st, "steps": [{"key": k, "label": lab, "done": st["step"] >= i} for i, (k, lab) in enumerate(STEPS)],
           "items": order["items"], "bill": order["bill"], "address": order["address"], "payment": order["payment"],
           "created_at": order["created_at"], "eta_min": order["eta_min"], "demo": True, "note": DEMO_NOTE}
    if st["step"] >= 2 and st["stage"] != "cancelled":
        out["rider"] = rider_of(order["order_id"])
    if owner and st["stage"] == "on_the_way":
        out["delivery_otp"] = otp_of(order["order_id"])
    if order.get("cancel"):
        out["cancel"] = order["cancel"]
    return out


# ---------------------------------------------------------------- routes
class Line(BaseModel):
    id: str = Field(..., max_length=60)
    qty: int = Field(..., ge=1, le=99)


class QuoteBody(BaseModel):
    items: List[Line] = Field(..., min_length=1, max_length=60)
    coupon: Optional[str] = Field(None, max_length=20)


class MatchBody(BaseModel):
    items: List[str] = Field(..., min_length=1, max_length=20)


class Address(BaseModel):
    name: str = Field(..., min_length=2, max_length=60)
    phone: str = Field(..., max_length=20)
    line: str = Field(..., min_length=5, max_length=160)
    landmark: Optional[str] = Field(None, max_length=80)
    pincode: str = Field(..., max_length=10)


class OrderBody(QuoteBody):
    address: Address
    payment: str = Field("cod", max_length=10)


@router.get("/catalog")
async def catalog():
    return {"categories": cat.CATEGORIES, "items": [cat.public(i) for i in cat.ITEMS], "delivery": {"eta": "8-14 min", "free_from": cat.FREE_DELIVERY_FROM,
            "fee": cat.DELIVERY_FEE, "handling": cat.HANDLING_FEE, "min_order": cat.MIN_ORDER}, "coupons": [{"code": k, "text": v["text"]} for k, v in cat.COUPONS.items()],
            "demo": True, "note": DEMO_NOTE}


@router.get("/search")
async def search_route(request: Request, q: str = ""):
    D["rate_limit"]("gs:" + D["client_ip"](request), 120, 60)
    return {"query": _txt(q, 60), "results": search(_txt(q, 60))}


@router.post("/quote")
async def quote(body: QuoteBody, request: Request):
    D["rate_limit"]("gq:" + D["client_ip"](request), 120, 60)
    return {"bill": bill_for([ln.model_dump() for ln in body.items], body.coupon or "")}


@router.post("/match")
async def match_route(body: MatchBody, request: Request):
    D["rate_limit"]("gm:" + D["client_ip"](request), 60, 60)
    return match(body.items)


@router.post("/orders")
async def place(body: OrderBody, request: Request, user=Depends(_user)):
    D["rate_limit"]("go:" + user["user_id"], 10, 600)
    bill = bill_for([ln.model_dump() for ln in body.items], body.coupon or "")
    if bill["items_total"] < cat.MIN_ORDER:
        raise _fail(400, f"The smallest order is Rs {cat.MIN_ORDER}. Add a little more.")
    a = body.address
    phone = re.sub(r"[\s\-]", "", a.phone)
    phone = re.sub(r"^(\+91|91|0)(?=\d{10}$)", "", phone)
    if not re.fullmatch(r"[6-9]\d{9}", phone):
        raise _fail(400, "Please enter a 10-digit mobile number.")
    if not re.fullmatch(r"\d{6}", a.pincode.strip()):
        raise _fail(400, "Please enter a 6-digit pincode.")
    pay = body.payment.lower()
    if pay not in ("cod", "upi"):
        raise _fail(400, "Please choose cash on delivery or UPI.")
    order_id = "GR" + secrets.token_hex(5).upper()
    now = _now()
    doc = {"order_id": order_id, "user_id": user["user_id"], "created_at": now, "eta_min": eta_minutes(order_id), "status": "active",
           "items": bill["lines"], "bill": {k: v for k, v in bill.items() if k != "lines"},
           "address": {"name": _txt(a.name, 60), "phone": phone, "line": _txt(a.line, 160), "landmark": _txt(a.landmark or "", 80), "pincode": a.pincode.strip()},
           "payment": {"method": pay, "status": "paid_demo" if pay == "upi" else "pay_on_delivery", "amount": bill["total"]}}
    await D["db"]().grocery_orders.insert_one(dict(doc))
    return {"order": view(doc, now)}


@router.get("/orders")
async def mine(user=Depends(_user)):
    now = _now()
    docs = await D["db"]().grocery_orders.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(30)
    return {"orders": [view(o, now) for o in docs]}


@router.get("/orders/active")
async def active(user=Depends(_user)):
    now = _now()
    docs = await D["db"]().grocery_orders.find({"user_id": user["user_id"], "status": "active"}, {"_id": 0}).sort("created_at", -1).to_list(5)
    for o in docs:
        if stage_of(o, now)["stage"] != "delivered":
            return {"order": view(o, now)}
    return {"order": None}


async def _own(order_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    o = await D["db"]().grocery_orders.find_one({"order_id": _txt(order_id, 20), "user_id": user["user_id"]}, {"_id": 0})
    if not o:
        raise _fail(404, "We could not find this order.")
    return o


@router.get("/orders/{order_id}")
async def one(order_id: str, user=Depends(_user)):
    return {"order": view(await _own(order_id, user), _now())}


class CancelBody(BaseModel):
    reason: Optional[str] = Field(None, max_length=80)


@router.post("/orders/{order_id}/cancel")
async def cancel(order_id: str, body: CancelBody, user=Depends(_user)):
    o = await _own(order_id, user)
    now = _now()
    st = stage_of(o, now)
    if st["stage"] == "cancelled":
        return {"order": view(o, now)}
    if not st.get("can_cancel"):
        raise _fail(409, "The rider has already picked up this order, so it cannot be cancelled now.")
    o["status"] = "cancelled"
    o["cancel"] = {"reason": _txt(body.reason or "Changed my mind", 80), "at": now,
                   "refund": "Nothing was charged." if o["payment"]["method"] == "cod" else "Demo payment: nothing was charged, so there is nothing to refund."}
    await D["db"]().grocery_orders.update_one({"order_id": o["order_id"]}, {"$set": {"status": "cancelled", "cancel": o["cancel"]}})
    return {"order": view(o, now)}
