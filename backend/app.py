import os
import datetime
import urllib.parse

import httpx
from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi_throttling import ThrottlingMiddleware
from jose import jwt
from jose.exceptions import JWTError
from sqlmodel import Session, select, SQLModel, create_engine

from models import Inventory, Booking


# --- Environment Config ---
ENGINE = create_engine(os.getenv("POSTGRES_URI"))
APP_PORT = os.getenv("APP_PORT", "8000")

KEYCLOAK_URL = os.getenv("KEYCLOAK_URI")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET")
KEYCLOAK_PUBLIC_KEY = os.getenv("KEYCLOAK_PUBLIC_KEY")
KEYCLOAK_ALGORITHM = os.getenv("KEYCLOAK_ALGORITHM", "RS256")
KEYCLOAK_ISSUER = os.getenv("KEYCLOAK_ISSUER")
FRONTEND_URI = os.getenv("FRONTEND_URI")

# Derived Keycloak URLs
KEYCLOAK_AUTH_URI = (
    f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/auth"
)
KEYCLOAK_TOKEN_URI = (
    f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
)


# --- FastAPI Init ---
app = FastAPI()
app.add_middleware(ThrottlingMiddleware, limit=100, window=60)
security = HTTPBearer()


@app.middleware("http")
async def bypass_reflex_routes(request: Request, call_next):
    # Let Reflex internal endpoints bypass validation
    path = request.url.path
    # Reflex uses _event for WebSocket events
    internal_prefixes = ["/_event", "/_rx", "/static", "/favicon.ico", "/"]
    # You might want to adjust these based on your setup
    for prefix in internal_prefixes:
        if path.startswith(prefix):
            return await call_next(request)
    return await call_next(request)


@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(ENGINE)


# --- Authentication & Authorization ---
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            KEYCLOAK_PUBLIC_KEY,
            algorithms=[KEYCLOAK_ALGORITHM],
            issuer=KEYCLOAK_ISSUER,
        )
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token. Are you logged in?")


def require_admin(user: dict = Depends(get_current_user)):
    groups = user.get("groups", [])
    if "admin" not in groups:
        raise HTTPException(status_code=403, detail="Admin access only")


@app.get("/")
def root():
    return {"status": "ok"}


# --- Keycloak Login Flow ---
@app.get("/login")
def login():
    params = {
        "client_id": KEYCLOAK_CLIENT_ID,
        "response_type": "code",
        "scope": "openid",
        "redirect_uri": FRONTEND_URI,
    }
    auth_url = f"{KEYCLOAK_AUTH_URI}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=auth_url)


@app.get("/callback")
async def callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return JSONResponse({"error": "Missing code"}, status_code=400)

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": FRONTEND_URI,
        "client_id": KEYCLOAK_CLIENT_ID,
        "client_secret": KEYCLOAK_CLIENT_SECRET,
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with httpx.AsyncClient() as client:
        response = await client.post(KEYCLOAK_TOKEN_URI, data=data, headers=headers)

    if response.status_code != 200:
        return JSONResponse(
            {"error": "Failed to exchange token", "details": response.text},
            status_code=400,
        )

    access_token = response.json().get("access_token")
    redirect_url = f"{FRONTEND_URI}?token={access_token}"
    return RedirectResponse(redirect_url)


# --- Inventory Routes ---
@app.post("/inventory", response_model=Inventory, dependencies=[Depends(require_admin)])
def create_item(item: Inventory):
    with Session(ENGINE) as session:
        session.add(item)
        session.commit()
        session.refresh(item)
        return item


@app.put(
    "/inventory/{id}", response_model=Inventory, dependencies=[Depends(require_admin)]
)
def update_item(id: int, updated_item: Inventory):
    with Session(ENGINE) as session:
        item = session.get(Inventory, id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        for key, value in updated_item.dict(exclude_unset=True).items():
            setattr(item, key, value)
        session.commit()
        session.refresh(item)
        return item


@app.delete("/inventory/{id}", dependencies=[Depends(require_admin)])
def delete_item(id: int):
    with Session(ENGINE) as session:
        item = session.get(Inventory, id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        session.delete(item)
        session.commit()
        return {"ok": True}


@app.get(
    "/inventory", response_model=list[Inventory], dependencies=[Depends(require_admin)]
)
def list_items(
    id: int | None = None,
    category: str | None = None,
    craft_type: str | None = None,
    size: str | None = None,
    num_seats: int | None = None,
):
    with Session(ENGINE) as session:
        return session.exec(select(Inventory)).all()


# --- Bookings Logic ---
def check_if_item_available(
    session: Session,
    item_id: int,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
):
    overlapping = session.exec(
        select(Booking)
        .where(Booking.item_id == item_id)
        .where(Booking.start_time <= end_time)
        .where(Booking.end_time >= start_time)
    ).all()

    if overlapping:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Item is already booked for the requested time.",
        )


# --- Booking Routes ---
@app.post("/bookings", response_model=Booking, dependencies=[Depends(get_current_user)])
def create_booking(booking: Booking):
    with Session(ENGINE) as session:
        check_if_item_available(
            session, booking.item_id, booking.start_time, booking.end_time
        )
        session.add(booking)
        session.commit()
        session.refresh(booking)
        return booking


@app.put(
    "/bookings/{id}", response_model=Booking, dependencies=[Depends(get_current_user)]
)
def update_booking(id: int, updated_booking: Booking):
    with Session(ENGINE) as session:
        booking = session.get(Booking, id)
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        for key, value in updated_booking.dict(exclude_unset=True).items():
            setattr(booking, key, value)
        session.commit()
        session.refresh(booking)
        return booking


@app.delete("/bookings/{id}", dependencies=[Depends(get_current_user)])
def delete_booking(id: int):
    with Session(ENGINE) as session:
        booking = session.get(Booking, id)
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        session.delete(booking)
        session.commit()
        return {"ok": True}


@app.get(
    "/bookings", response_model=list[Booking], dependencies=[Depends(get_current_user)]
)
def list_bookings(
    id: int | None = None,
    item_id: int | None = None,
    user_id: int | None = None,
    start_time: datetime.datetime | None = None,
    end_time: datetime.datetime | None = None,
):
    with Session(ENGINE) as session:
        return session.exec(select(Booking)).all()
