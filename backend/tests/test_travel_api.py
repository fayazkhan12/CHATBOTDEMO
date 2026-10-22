import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


def test_search_all_services_and_demo_mode():
    for service in ("flights", "hotels", "buses", "cabs"):
        response = requests.post(f"{BASE_URL}/api/travel/search", json={"service": service})
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "DEMO"
        assert data["service"] == service
        assert data["results"]
        assert all(item["mode"] == "DEMO" for item in data["results"])


def test_save_and_fetch_trip():
    payload = {"title": "TEST Goa trip", "origin": "New Delhi", "destination": "Goa", "items": []}
    response = requests.post(f"{BASE_URL}/api/trips", json=payload)
    assert response.status_code == 200
    share_id = response.json()["share_id"]
    fetched = requests.get(f"{BASE_URL}/api/trips/{share_id}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == payload["title"]


def test_chat_stream_has_fallback_or_assistant_text():
    response = requests.post(f"{BASE_URL}/api/chat/stream", json={"message": "Plan Goa"}, stream=True, timeout=30)
    assert response.status_code == 200
    body = response.content.decode()
    assert "data:" in body
    assert "type" in body
    assert "text" in body