import os
import datetime
import urllib.parse

import httpx
from fastapi import FastAPI, HTTPException, Depends, status, Request, Cookie
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi_throttling import ThrottlingMiddleware
from jose import jwt
from jose.exceptions import JWTError
from sqlmodel import Session, select, SQLModel, create_engine
from urllib.parse import urljoin
import logging

from models import Inventory, Booking

# --- Environment Config ---
ENGINE = create_engine(os.getenv("POSTGRES_URI"))
APP_URI = os.getenv("BACKEND_URI")
FRONTEND_URI = os.getenv("FRONTEND_URI")

KEYCLOAK_URL = os.getenv("KEYCLOAK_URI")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET")
KEYCLOAK_PUBLIC_KEY = os.getenv("KEYCLOAK_PUBLIC_KEY")
KEYCLOAK_ALGORITHM = os.getenv("KEYCLOAK_ALGORITHM", "RS256")
KEYCLOAK_ISSUER = os.getenv("KEYCLOAK_ISSUER")

KEYCLOAK_AUTH_URI = (
    f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/auth"
)
KEYCLOAK_TOKEN_URI = (
    f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
)

logger = logging.getLogger("uvicorn.error")

# --- FastAPI Init ---
app = FastAPI()
app.add_middleware(ThrottlingMiddleware, limit=100, window=60)


@app.middleware("http")
async def bypass_reflex_routes(request: Request, call_next):
    # Allow Reflex system routes through (no auth)
    internal_prefixes = ["/_event", "/_rx", "/static", "/favicon.ico", "/"]
    if any(request.url.path.startswith(p) for p in internal_prefixes):
        return await call_next(request)
    return await call_next(request)


@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(ENGINE)


# --- Auth ---
def get_current_user(token: str = Cookie(None)) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(
            token,
            KEYCLOAK_PUBLIC_KEY,
            algorithms=[KEYCLOAK_ALGORITHM],
            issuer=KEYCLOAK_ISSUER,
        )
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_admin(user: dict = Depends(get_current_user)):
    if "admin" not in user.get("groups", []):
        raise HTTPException(status_code=403, detail="Admin access only")


# --- Auth Endpoints ---
@app.get("/login")
def login():
    params = {
        "client_id": KEYCLOAK_CLIENT_ID,
        "response_type": "code",
        "scope": "openid",
        "redirect_uri": urljoin(APP_URI, "/callback"),
    }
    auth_url = f"{KEYCLOAK_AUTH_URI}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=auth_url)


@app.get("/callback")
async def callback(request: Request):
    """
    OAuth2 callback endpoint to exchange authorization code for access token.
    """
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code in callback.",
        )

    # Prepare token request payload
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": FRONTEND_URI,
        "client_id": KEYCLOAK_CLIENT_ID,
        "client_secret": KEYCLOAK_CLIENT_SECRET,
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                KEYCLOAK_TOKEN_URI, data=data, headers=headers, timeout=10.0
            )
            response.raise_for_status()
        except httpx.RequestError as e:
            logger.error(f"Network error while requesting token from Keycloak: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to connect to Keycloak for token exchange.",
            )
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Keycloak responded with error status {e.response.status_code}: {e.response.text}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Keycloak token endpoint returned error: {e.response.text}",
            )
        except Exception as e:
            logger.error(f"Unexpected error during token exchange: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unexpected error during token exchange.",
            )

    token_response = response.json()

    access_token = token_response.get("access_token")
    if not access_token:
        logger.error(f"No access token found in Keycloak response: {token_response}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No access token returned from Keycloak.",
        )

    # Optionally: store token in a secure way, create session, etc.

    return {
        "access_token": access_token,
        "token_type": token_response.get("token_type"),
        "expires_in": token_response.get("expires_in"),
        "refresh_token": token_response.get("refresh_token"),
        # Add other fields as needed
    }


@app.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    return {
        "username": user.get("preferred_username"),
        "email": user.get("email"),
        "groups": user.get("groups", []),
    }


# --- Inventory Management (Admin Only) ---
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
def list_items():
    with Session(ENGINE) as session:
        return session.exec(select(Inventory)).all()


# --- Booking Logic ---
def check_if_item_available(
    session: Session, item_id: int, start: datetime.datetime, end: datetime.datetime
):
    overlapping = session.exec(
        select(Booking)
        .where(Booking.item_id == item_id)
        .where(Booking.start_time <= end)
        .where(Booking.end_time >= start)
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
def list_bookings():
    with Session(ENGINE) as session:
        return session.exec(select(Booking)).all()
