from fastapi.testclient import TestClient
import datetime
import os
import pytest
from sqlmodel import SQLModel, Session, select
from dotenv import load_dotenv

os.environ["POSTGRES_URI"] = "sqlite:///./test.db"
load_dotenv(".env")
assert os.environ["SECRET_KEY"]

from .app import app, get_current_user, get_password_hash
from .database import engine
from .models import User

client = TestClient(app)


def teardown_function():
    app.dependency_overrides = {}


@pytest.fixture(scope="session", autouse=True)
def reset_database():
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(scope="session", autouse=True)
def create_users(reset_database):
    with Session(engine) as session:
        user1 = User(
            username="johndoe",
            email="john@doe.com",
            hashed_password=get_password_hash("johnspass"),
        )
        user2 = User(
            username="janedoe",
            email="jane@doe.com",
            hashed_password=get_password_hash("janespass"),
        )
        session.add_all([user1, user2])
        session.commit()


def get_user_by_username(username: str):
    with Session(engine) as session:
        return session.exec(select(User).where(User.username == username)).first()


def mock_user():
    return get_user_by_username("johndoe")


def mock_other_user():
    return get_user_by_username("janedoe")


# @pytest.fixture(autouse=True)
# def set_test_database_url():
#     # Force using the in-memory SQLite database for tests
#     os.environ["POSTGRES_URI"] = "sqlite:///:memory:"


def test_login():
    # Insert test user
    with Session(engine) as session:
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password=get_password_hash("password"),
        )
        session.add(user)
        session.commit()

    # Test valid login
    response = client.post(
        "/token", data={"username": "testuser", "password": "password"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Test invalid login
    response = client.post(
        "/token", data={"username": "nonexistentuser", "password": "password"}
    )
    assert response.status_code == 401


# --------
# Inventory endpoints
# --------


def test_get_inventory_not_logged_in():
    response = client.get("/inventory")
    assert response.status_code == 401


def test_get_inventory_logged_in():
    app.dependency_overrides[get_current_user] = mock_user
    response = client.get("/inventory")
    assert response.status_code == 200


def test_post_inventory_not_logged_in():
    response = client.post("/inventory")
    assert response.status_code == 401


@pytest.mark.skip("RBAC not yet implemented")
def test_post_inventory_regular_user():
    app.dependency_overrides[get_current_user] = mock_user
    response = client.get("/inventory")
    assert response.status_code == 401


@pytest.mark.skip("RBAC not yet implemented")
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


@pytest.mark.skip("RBAC not yet implemented")
def test_put_inventory_regular_user():
    app.dependency_overrides[get_current_user] = mock_user

    response = client.put(
        "/inventory/1", json={"reference": "Updated", "category": "craft", "size": "M"}
    )
    assert response.status_code == 401


@pytest.mark.skip("RBAC not yet implemented")
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
    response = client.get("/bookings")
    assert response.status_code == 401


def test_get_booking_logged_in():
    app.dependency_overrides[get_current_user] = mock_user
    response = client.get("/bookings")
    assert response.status_code == 200


def test_post_booking_not_logged_in():
    response = client.post("/bookings", json=booking_payload)
    assert response.status_code == 401


@pytest.mark.skip("RBAC not yet implemented")
def test_post_booking_regular_user():
    app.dependency_overrides[get_current_user] = mock_user
    response = client.post("/bookings", json=booking_payload)
    assert response.status_code == 401


def test_put_booking_not_logged_in():
    app.dependency_overrides = {}
    response = client.put("/bookings/1", json=booking_payload)
    assert response.status_code == 403 or response.status_code == 401


@pytest.mark.skip("RBAC not yet implemented")
def test_put_booking_regular_user():
    app.dependency_overrides[get_current_user] = mock_user
    response = client.put("/bookings/1", json=booking_payload)
    assert response.status_code == 401


def test_user_cannot_delete_others_booking():

    # Create booking
    app.dependency_overrides[get_current_user] = mock_user
    current_user = mock_user()

    create_resp = client.post(
        "/bookings",
        json={
            "user_id": current_user.id,
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
    delete_resp = client.delete(f"/bookings/{booking_id}")
    assert delete_resp.status_code == 401


def test_owner_can_delete_own_booking():
    app.dependency_overrides[get_current_user] = mock_user
    create_resp = client.post(
        "/bookings",
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
    delete_resp = client.delete(f"/bookings/{booking_id}")
    assert delete_resp.status_code == 200


@pytest.mark.skip("RBAC not yet implemented")
def test_admin_can_delete_any_booking():
    # Create booking as user
    app.dependency_overrides[get_current_user] = mock_user
    create_resp = client.post(
        "/bookings",
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
    delete_resp = client.delete(f"/bookings/{booking_id}")
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

    resp1 = client.post("/bookings", json=booking1)
    assert resp1.status_code == 200

    # Attempt to create conflicting booking with overlapping time
    booking2 = {
        "user_id": 2,
        "item_id": 100,
        "start_time": (now + datetime.timedelta(minutes=30)).isoformat(),
        "end_time": (now + datetime.timedelta(hours=3)).isoformat(),
    }

    resp2 = client.post("/bookings", json=booking2)
    assert resp2.status_code == 409
