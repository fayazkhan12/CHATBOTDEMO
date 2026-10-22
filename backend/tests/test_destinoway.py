"""Comprehensive backend tests for DestinoWay V2."""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

TEST_EMAIL = f"test_{uuid.uuid4().hex[:8]}@destinoway.com"
TEST_PASSWORD = "test1234"
TEST_NAME = "DW Tester"


@pytest.fixture(scope="module")
def auth():
    r = requests.post(
        f"{BASE_URL}/api/auth/signup",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "name": TEST_NAME},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data and "user" in data
    return data


# ---------- Health ----------
def test_root():
    r = requests.get(f"{BASE_URL}/api/")
    assert r.status_code == 200
    d = r.json()
    assert d.get("message") == "DestinoWay API"
    assert "razorpay_configured" in d


# ---------- Auth ----------
def test_signup_login_me(auth):
    token = auth["token"]
    # Login with seeded account
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert r.status_code == 200
    assert "token" in r.json()

    # /me with bearer
    me = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == TEST_EMAIL


def test_signup_duplicate():
    r = requests.post(
        f"{BASE_URL}/api/auth/signup",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "name": TEST_NAME},
    )
    assert r.status_code == 409


def test_login_bad_password():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": "wrong"},
    )
    assert r.status_code == 401


# ---------- Travel search ----------
@pytest.mark.parametrize("service", ["flights", "hotels", "buses", "cabs"])
def test_search_service(service):
    r = requests.post(f"{BASE_URL}/api/travel/search", json={"service": service, "destination": "Goa"})
    assert r.status_code == 200
    d = r.json()
    assert d["service"] == service
    assert d["mode"] == "DEMO"
    assert len(d["results"]) > 0
    for item in d["results"]:
        for k in ("id", "title", "price", "image"):
            assert k in item, f"missing {k} in {service}"


# ---------- Cache + detail ----------
def test_cache_and_detail():
    search = requests.post(f"{BASE_URL}/api/travel/search", json={"service": "hotels"}).json()
    items = search["results"][:3]
    r = requests.post(f"{BASE_URL}/api/travel/cache", json=items)
    assert r.status_code == 200 and r.json()["ok"] is True
    item_id = items[0]["id"]
    d = requests.get(f"{BASE_URL}/api/travel/detail/{item_id}")
    assert d.status_code == 200
    assert d.json()["id"] == item_id


def test_detail_404():
    r = requests.get(f"{BASE_URL}/api/travel/detail/nonexistent-xyz")
    assert r.status_code == 404


# ---------- Featured ----------
def test_featured_destinations():
    r = requests.get(f"{BASE_URL}/api/featured/destinations")
    assert r.status_code == 200
    d = r.json()
    assert len(d["destinations"]) > 0
    assert len(d["collections"]) > 0
    for item in d["destinations"]:
        for k in ("city", "image", "from_price"):
            assert k in item


# ---------- Trips ----------
def test_save_and_get_trip():
    r = requests.post(
        f"{BASE_URL}/api/trips",
        json={"title": "TEST trip", "origin": "DEL", "destination": "GOI", "items": [{"id": "a"}]},
    )
    assert r.status_code == 200
    share_id = r.json()["share_id"]
    g = requests.get(f"{BASE_URL}/api/trips/{share_id}")
    assert g.status_code == 200
    assert g.json()["title"] == "TEST trip"


# ---------- Bookings DEMO ----------
def test_bookings_demo_flow(auth):
    headers = {"Authorization": f"Bearer {auth['token']}"}
    search = requests.post(f"{BASE_URL}/api/travel/search", json={"service": "hotels"}).json()
    item = search["results"][0]
    r = requests.post(
        f"{BASE_URL}/api/bookings",
        headers=headers,
        json={
            "service": "hotels",
            "item": item,
            "traveller": {"name": "Test User", "email": TEST_EMAIL, "phone": "9999999999"},
            "amount_rupees": int(item["price"]),
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "DEMO"
    assert d["razorpay_order_id"] is None
    booking_id = d["booking_id"]

    # Demo-confirm
    c = requests.post(f"{BASE_URL}/api/bookings/demo-confirm", json={"booking_id": booking_id})
    assert c.status_code == 200
    assert c.json()["status"] == "confirmed_demo"

    # Fetch booking
    g = requests.get(f"{BASE_URL}/api/bookings/{booking_id}")
    assert g.status_code == 200
    assert g.json()["status"] == "confirmed_demo"


# ---------- Chat SSE ----------
def test_chat_stream_done_event():
    r = requests.post(
        f"{BASE_URL}/api/chat/stream",
        json={"message": "Plan a Goa trip for 2"},
        stream=True,
        timeout=60,
    )
    assert r.status_code == 200
    saw_done = False
    saw_token = False
    start = time.time()
    for line in r.iter_lines(decode_unicode=True):
        if line and line.startswith("data:"):
            if '"type": "done"' in line or '"type":"done"' in line:
                saw_done = True
                break
            if '"type": "token"' in line or '"type":"token"' in line:
                saw_token = True
        if time.time() - start > 45:
            break
    assert saw_done, "SSE stream should emit a done event"
    assert saw_token, "SSE stream should emit at least one token"
