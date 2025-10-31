from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pwdlib import PasswordHash
from pydantic import BaseModel
import jwt
from jwt.exceptions import InvalidTokenError
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
import os
from sqlmodel import SQLModel
from contextlib import asynccontextmanager

from models import (
    User,
    Inventory,
    Booking,
    UserCreate,
    UserLogin,
    UserRead,
    InventoryCreate,
    InventoryRead,
    BookingCreate,
    BookingRead,
)
from database import engine, get_session

ENGINE = engine

SECRET_KEY = os.getenv("SECRET_KEY")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
ALGORITHM = os.getenv("ALGORITHM", "HS256")


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


password_hash = PasswordHash.recommended()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(lifespan=lifespan)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_user_by_username(session: Session, username: str):
    statement = select(User).where(User.username == username)
    return session.exec(statement).first()


def authenticate_user(session: Session, username: str, password: str):
    user = get_user_by_username(session, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Session = Depends(get_session),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except InvalidTokenError:
        raise credentials_exception
    user = get_user_by_username(session, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


@app.post("/register", response_model=UserRead)
def register_user(user: UserCreate, session: Session = Depends(get_session)):
    existing_user = session.exec(
        select(User).where(User.username == user.username)
    ).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already taken")

    hashed_password = get_password_hash(user.password)
    db_user = User(
        username=user.username, email=user.email, hashed_password=hashed_password
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


@app.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Session = Depends(get_session),
) -> Token:
    user = authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


@app.get("/users/me", response_model=UserRead)
async def read_users_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user


# --- Inventory Management (Admin Only) ---
@app.post(
    "/inventory",
    response_model=InventoryRead,
    dependencies=[Depends(get_current_user)],
)
def create_item(item: InventoryCreate, session: Session = Depends(get_session)):
    db_item = Inventory(**item.model_dump())
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


@app.put(
    "/inventory/{id}",
    response_model=InventoryRead,
    dependencies=[Depends(get_current_user)],
)
def update_item(
    id: int, updated_item: InventoryCreate, session: Session = Depends(get_session)
):
    item = session.get(Inventory, id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    for key, value in updated_item.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    session.commit()
    session.refresh(item)
    return item


@app.delete("/inventory/{id}", dependencies=[Depends(get_current_user)])
def delete_item(id: int, session: Session = Depends(get_session)):
    item = session.get(Inventory, id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    session.delete(item)
    session.commit()
    return {"ok": True}


@app.get(
    "/inventory",
    response_model=list[InventoryRead],
    dependencies=[Depends(get_current_user)],
)
def list_items(session: Session = Depends(get_session)):
    db_items = session.exec(select(Inventory)).all()
    return db_items


# --- Booking Logic ---
def check_if_item_available(
    item_id: int, start: datetime, end: datetime, session: Session
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
@app.post(
    "/bookings", response_model=BookingRead, dependencies=[Depends(get_current_user)]
)
def create_booking(booking: BookingCreate, session: Session = Depends(get_session)):
    check_if_item_available(
        booking.item_id, booking.start_time, booking.end_time, session
    )
    db_booking = Booking(**booking.model_dump())
    session.add(db_booking)
    session.commit()
    session.refresh(db_booking)
    return db_booking


@app.put(
    "/bookings/{id}",
    response_model=BookingRead,
    dependencies=[Depends(get_current_user)],
)
def update_booking(
    id: int, updated_booking: BookingCreate, session: Session = Depends(get_session)
):
    booking = session.get(Booking, id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    for key, value in updated_booking.model_dump(exclude_unset=True).items():
        setattr(booking, key, value)
    session.commit()
    session.refresh(booking)
    return booking


@app.delete("/bookings/{id}", dependencies=[Depends(get_current_user)])
def delete_booking(id: int, session: Session = Depends(get_session)):
    db_booking = session.get(Booking, id)
    if not db_booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    session.delete(db_booking)
    session.commit()
    return {"ok": True}


@app.get(
    "/bookings",
    response_model=list[BookingRead],
    dependencies=[Depends(get_current_user)],
)
def list_bookings(session: Session = Depends(get_session)):
    return session.exec(select(Booking)).all()
