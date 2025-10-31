from fastapi.testclient import TestClient
import datetime
from .app_old import app, get_current_user, require_admin

client = TestClient(app)


def teardown_function():
    app.dependency_overrides = {}


# --------------
# Mocks
# --------------
def mock_user():
    return {"username": "johndoe", "groups": ["user"]}


def mock_admin():
    return {"username": "janeadmin", "groups": ["admin", "user"]}


def mock_other_user():
    return {"username": "jane_notadmin", "groups": ["user"]}


# --------
# Login
# --------


def test_login():
    response = client.get("/")
    assert response.status_code == 307


# --------
# Inventory endpoints
# --------


def test_get_inventory_not_logged_in():
    response = client.get("/inventory")
    assert response.status_code == 403


def test_get_inventory_logged_in():
    app.dependency_overrides[get_current_user] = mock_user
    response = client.get("/inventory")
    assert response.status_code == 200


def test_post_inventory_not_logged_in():
    response = client.post("/inventory")
    assert response.status_code == 403


def test_post_inventory_regular_user():
    app.dependency_overrides[get_current_user] = mock_user
    response = client.get("/inventory")
    assert response.status_code == 403


def test_post_inventory_admin():
    app.dependency_overrides[require_admin] = mock_admin
    response = client.post(
        "/inventory/", json={"reference": "Test Ref", "category": "craft", "size": "L"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reference"] == "Test Ref"
    assert data["category"] == "craft"
    assert data["size"] == "L"
    assert "id" in data


def test_put_inventory_not_logged_in():
    app.dependency_overrides = {}

    response = client.put(
        "/inventory/1", json={"reference": "Updated", "category": "craft", "size": "M"}
    )
    assert response.status_code == 403 or response.status_code == 401


def test_put_inventory_regular_user():
    app.dependency_overrides[get_current_user] = mock_user

    response = client.put(
        "/inventory/1", json={"reference": "Updated", "category": "craft", "size": "M"}
    )
    assert response.status_code == 403


def test_put_inventory_admin():
    app.dependency_overrides[require_admin] = mock_admin
    response = client.post(
        "/inventory/", json={"reference": "Test Ref", "category": "craft", "size": "L"}
    )
    assert response.status_code == 200
    created = response.json()
    inventory_id = created["id"]

    response = client.put(
        f"/inventory/{inventory_id}",
        json={"reference": "Test Ref", "category": "craft", "size": "M"},
    )
    data = response.json()
    assert data["reference"] == "Test Ref"
    assert data["category"] == "craft"
    assert data["size"] == "M"
    assert "id" in data


# -----------------
# Booking endpoints
# -----------------


booking_payload = {
    "user_id": 1,
    "item_id": 1,
    "start_time": datetime.datetime.utcnow().isoformat(),
    "end_time": (datetime.datetime.utcnow() + datetime.timedelta(hours=1)).isoformat(),
}


def test_get_booking_not_logged_in():
    response = client.get("/booking")
    assert response.status_code == 403


def test_get_booking_logged_in():
    app.dependency_overrides[get_current_user] = mock_user
    response = client.get("/booking")
    assert response.status_code == 200


def test_post_booking_not_logged_in():
    response = client.post("/booking", json=booking_payload)
    assert response.status_code == 403


def test_post_booking_regular_user():
    app.dependency_overrides[get_current_user] = mock_user
    response = client.post("/booking", json=booking_payload)
    assert response.status_code == 403


def test_put_booking_not_logged_in():
    app.dependency_overrides = {}
    response = client.put("/booking/1", json=booking_payload)
    assert response.status_code == 403 or response.status_code == 401


def test_put_booking_regular_user():
    app.dependency_overrides[get_current_user] = mock_user
    response = client.put("/booking/1", json=booking_payload)
    assert response.status_code == 403


def test_user_cannot_delete_others_booking():

    # Create booking
    app.dependency_overrides[get_current_user] = mock_user
    create_resp = client.post(
        "/booking",
        json={
            "user_id": 1,
            "item_id": 101,
            "start_time": datetime.datetime.now().isoformat(),
            "end_time": (
                datetime.datetime.now() + datetime.timedelta(hours=1)
            ).isoformat(),
        },
    )
    assert create_resp.status_code == 200
    booking_id = create_resp.json()["id"]

    app.dependency_overrides[get_current_user] = mock_other_user
    delete_resp = client.delete(f"/booking/{booking_id}")
    assert delete_resp.status_code == 403


def test_owner_can_delete_own_booking():
    app.dependency_overrides[get_current_user] = mock_user
    create_resp = client.post(
        "/booking",
        json={
            "user_id": 1,
            "item_id": 102,
            "start_time": datetime.datetime.now().isoformat(),
            "end_time": (
                datetime.datetime.now() + datetime.timedelta(hours=1)
            ).isoformat(),
        },
    )
    assert create_resp.status_code == 200
    booking_id = create_resp.json()["id"]

    # Delete as owner
    delete_resp = client.delete(f"/booking/{booking_id}")
    assert delete_resp.status_code == 204


def test_admin_can_delete_any_booking():
    # Create booking as user
    app.dependency_overrides[get_current_user] = mock_user
    create_resp = client.post(
        "/booking",
        json={
            "user_id": 1,
            "item_id": 103,
            "start_time": datetime.datetime.now().isoformat(),
            "end_time": (
                datetime.datetime.now() + datetime.timedelta(hours=1)
            ).isoformat(),
        },
    )
    assert create_resp.status_code == 200
    booking_id = create_resp.json()["id"]

    # Delete as admin
    app.dependency_overrides[get_current_user] = mock_admin
    delete_resp = client.delete(f"/booking/{booking_id}")
    assert delete_resp.status_code == 204


def test_cannot_book_already_booked_item():
    app.dependency_overrides[get_current_user] = mock_user

    now = datetime.datetime.now()

    # Create initial booking
    booking1 = {
        "user_id": 1,
        "item_id": 100,
        "start_time": now.isoformat(),
        "end_time": (now + datetime.timedelta(hours=2)).isoformat(),
    }

    resp1 = client.post("/booking", json=booking1)
    assert resp1.status_code == 200

    # Attempt to create conflicting booking with overlapping time
    booking2 = {
        "user_id": 2,
        "item_id": 100,
        "start_time": (now + datetime.timedelta(minutes=30)).isoformat(),
        "end_time": (now + datetime.timedelta(hours=3)).isoformat(),
    }

    resp2 = client.post("/booking", json=booking2)
    assert resp2.status_code == 409
