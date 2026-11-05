"""The hotel page's server rules. No database or company API needed: run with `pytest tests/test_hotel_flow.py`."""
import os

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:1")
os.environ.setdefault("DB_NAME", "test")

import pytest
from fastapi.testclient import TestClient

import hotel_live as hl
import server


@pytest.fixture()
def api():
    server._MEM_ITEMS.clear()
    with TestClient(server.app) as c:
        yield c
    server.app.dependency_overrides.clear()


def offer(search_id, price, check_in):
    return {"id": "ak-44141027", "type": "hotel", "mode": "LIVE", "title": "Golden Leaf", "price": price,
            "search_id": search_id, "hotel_id": "44141027", "check_in": check_in}


def test_same_hotel_in_two_searches_keeps_its_own_dates_and_price(api):
    api.post("/api/travel/cache", json=[offer("search-a", 1421.72, "2026-11-05")])
    api.post("/api/travel/cache", json=[offer("search-b", 2100.5, "2026-12-24")])
    a = api.get("/api/travel/detail/ak-44141027", params={"sid": "search-a"}).json()
    b = api.get("/api/travel/detail/ak-44141027", params={"sid": "search-b"}).json()
    assert (a["price"], a["check_in"]) == (1421.72, "2026-11-05")
    assert (b["price"], b["check_in"]) == (2100.5, "2026-12-24")


def test_old_link_without_a_search_id_still_opens(api):
    api.post("/api/travel/cache", json=[offer("search-a", 1421.72, "2026-11-05")])
    assert api.get("/api/travel/detail/ak-44141027").json()["search_id"] == "search-a"


def test_me_never_sends_stored_login_tokens(api):
    user = {"user_id": "u1", "name": "A", "company": {"access": "sealed", "refresh": "sealed"}}
    server.app.dependency_overrides[server.current_user] = lambda: user
    body = api.get("/api/auth/me").json()
    assert "company" not in body
    assert body["company_linked"] is True
    assert user["company"]                  # the server's own copy is untouched


PRICE_CHECK = {"data": {"totalPayable": 1421.72, "couponDiscount": 168.25, "appliedCoupon": "06724", "currency": "INR",
                        "pricing": {"rooms": [{"roomCount": 1, "customerPrice": {"basePrice": 1346.01, "platform&servicetax": 75.71}}]}}}
ROOM_PRICE = {"totalPrice": 1421.72, "totalPriceBeforeCoupon": 1589.97, "currency": "INR"}


def test_dummy_coupon_is_left_out_of_every_price(monkeypatch):
    monkeypatch.setattr(hl, "COUPONS_ON", False)
    hl.set_signer(lambda booking_id, price: f"signed:{booking_id}:{price}")
    assert server._total_price({"price": ROOM_PRICE}) == 1589.97
    assert server._hotel_card({"supplierHotelId": "1", "price": ROOM_PRICE}, "Jaipur")["price"] == 1589.97
    room = hl._price(ROOM_PRICE, 1)
    assert room["payable"] == 1589.97 and "savings" not in room
    checked = hl.clean_price_check(PRICE_CHECK, "ak-1", "room-1")
    assert (checked["total"], checked["coupon"], checked["before_coupon"]) == (1589.97, None, None)
    assert checked["price_token"] == "signed:ak-1#room-1:1589.97"


def test_real_coupons_work_when_switched_on(monkeypatch):
    monkeypatch.setattr(hl, "COUPONS_ON", True)
    hl.set_signer(lambda booking_id, price: f"signed:{booking_id}:{price}")
    assert hl._price(ROOM_PRICE, 1)["savings"] == 168.25
    checked = hl.clean_price_check(PRICE_CHECK, "ak-1", "room-1")
    assert (checked["total"], checked["coupon"], checked["before_coupon"]) == (1421.72, "06724", 1589.97)


def test_price_check_without_a_total_is_not_a_price():
    assert hl.clean_price_check({"data": {"pricing": {}}}, "ak-1", "room-1") is None
