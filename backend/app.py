from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi_throttling import ThrottlingMiddleware
from fastapi.templating import Jinja2Templates
from jose import jwt
from jose.exceptions import JWTError
from models import Inventory, Booking
from sqlmodel import Session, select, SQLModel, create_engine
import os
import datetime
from pathlib import Path

app = FastAPI()
app.add_middleware(ThrottlingMiddleware, limit=100, window=60)
security = HTTPBearer()
APP_PORT = "8000"

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "frontend"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def get_secret(path: str) -> str:
    return Path(path).read_text().strip()


KEYCLOAK_PORT = "8080"
KEYCLOAK_PUBLIC_KEY = "5TIliH0iyzf1Efc_Zjq297ZZzELM8Q_Ty7nZLba2Vv0"
KEYCLOAK_ISSUER = f"http://keycloak:{KEYCLOAK_PORT}/realms/testing"
ALGORITHM = "RS256"

POSTGRES_PASSWORD = get_secret("/run/secrets/postgres_password")
POSTGRES_URI = f"postgresql://{os.getenv('POSTGRES_USER')}:{POSTGRES_PASSWORD}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
engine = create_engine(POSTGRES_URI)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, KEYCLOAK_PUBLIC_KEY, algorithms=[ALGORITHM], issuer=KEYCLOAK_ISSUER
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token. Are you logged in?")


def require_admin(user: dict = Depends(get_current_user)):
    groups = user.get("groups", [])
    if "admin" not in groups:
        raise HTTPException(status_code=403, detail="Admin access only")


@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)


@app.get("/")
def login():
    return RedirectResponse(
        url=f"http://localhost:{KEYCLOAK_PORT}/realms/testing/protocol/openid-connect/auth"
        "?client_id=inventory-app"
        "&response_type=code"
        "&scope=openid"
        f"&redirect_uri=http://localhost:{APP_PORT}/dashboard"
    )


@app.get(
    "/dashboard", response_class=HTMLResponse, dependencies=[Depends(get_current_user)]
)
def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "items": {}})


@app.post("/inventory", response_model=Inventory, dependencies=[Depends(require_admin)])
def create_item(item: Inventory):
    with Session(engine) as session:
        session.add(item)
        session.commit()
        session.refresh(item)
        return item


@app.put(
    "/inventory/{id}", response_model=Inventory, dependencies=[Depends(require_admin)]
)
def update_item(id: int, updated_item: Inventory):
    with Session(engine) as session:
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
    with Session(engine) as session:
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
    with Session(engine) as session:
        return session.exec(select(Inventory)).all()


def check_if_item_available(
    session: Session,
    item_id: int,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
):

    overlapping_bookings = session.exec(
        select(Booking)
        .where(Booking.item_id == item_id)
        .where(Booking.start_time <= end_time)
        .where(Booking.end_time >= start_time)
    ).all()
    if len(overlapping_bookings) > 0:
        if overlapping_bookings:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Item is already booked for the requested time.",
            )


@app.post("/bookings", response_model=Booking, dependencies=[Depends(get_current_user)])
def create_booking(booking: Booking) -> Booking:
    with Session(engine) as session:
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
    with Session(engine) as session:
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
    with Session(engine) as session:
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
    with Session(engine) as session:
        return session.exec(select(Booking)).all()
