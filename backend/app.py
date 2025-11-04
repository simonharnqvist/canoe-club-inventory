from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pwdlib import PasswordHash
from pydantic import BaseModel
import jwt
from jwt.exceptions import InvalidTokenError
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
import os
from sqlmodel import SQLModel
from typing import Optional

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


def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Canoe club inventory/bookings API",
    description="API to manage bookings, inventory, and users for a canoe club or similar sports club.",
    version="0.2.0",
)


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
    if not SECRET_KEY or SECRET_KEY == "":
        raise ValueError("SECRET_KEY is missing")
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


def is_admin(user: User):
    if not user.is_admin or not isinstance(user.is_admin, bool):
        raise HTTPException(status_code=401, detail="Admin only")
    else:
        return user.is_admin


def get_current_user(
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


@app.post(
    "/register",
    response_model=UserRead,
    summary="Register new user",
    response_description="User data",
    tags=["Users"],
)
def register_user(user: UserCreate, session: Session = Depends(get_session)):
    """
    Register new user.
    """
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


@app.post(
    "/token", summary="Log in", response_description="Bearer token", tags=["Users"]
)
def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Session = Depends(get_session),
) -> Token:
    """Obtain token for login"""
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


@app.get(
    "/users/me",
    response_model=UserRead,
    summary="Get current user",
    response_description="Current user data",
    tags=["Users"],
)
def read_users_me(current_user: Annotated[User, Depends(get_current_user)]):
    """Get current user data."""
    return current_user


# --- Inventory Management ---
@app.post(
    "/inventory",
    response_model=InventoryRead,
    dependencies=[Depends(get_current_user)],
    summary="Add new item to inventory",
    response_description="Item data",
    tags=["Inventory"],
)
def create_item(
    item: InventoryCreate,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """Add new item to inventory. Admin access only."""

    is_admin(current_user)
    db_item = Inventory(**item.model_dump())
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


@app.put(
    "/inventory/{id}",
    response_model=InventoryRead,
    dependencies=[Depends(get_current_user)],
    summary="Update item in inventory",
    response_description="Updated item data",
    tags=["Inventory"],
)
def update_item(
    id: int,
    updated_item: InventoryCreate,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """
    Update item in inventory by item_id. Admin access only.
    - **item_id**: Unique ID of item.
    """
    is_admin(current_user)
    item = session.get(Inventory, id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    for key, value in updated_item.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    session.commit()
    session.refresh(item)
    return item


@app.delete(
    "/inventory/{id}",
    dependencies=[Depends(get_current_user)],
    summary="Delete item in inventory",
    tags=["Inventory"],
)
def delete_item(
    id: int,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """
    Delete item in inventory by item_id. Admin access only
    - **item_id**: Unique ID of item.
    """
    is_admin(current_user)
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
    summary="List items in inventory",
    response_description="List of items",
    tags=["Inventory"],
)
def list_items(
    session: Session = Depends(get_session),
    reference: Optional[str] = Query(
        None,
        description="Filter by item reference",
        min_length=1,
        max_length=50,
        example="Green mamba kayak",
    ),
    category: Optional[str] = Query(
        None,
        description="Filter by item category",
        min_length=1,
        max_length=50,
        example="canoe",
    ),
    size: Optional[str] = Query(
        None,
        description="Filter by item size",
        min_length=1,
        max_length=10,
        example="Large",
    ),
):
    """
    List all items in inventory with optional filtering by reference, category, or size.

    - **reference**: Optional filter by item reference (partial match)
    - **category**: Optional filter by item category (partial match)
    - **size**: Optional filter by item size (partial match)
    """
    query = select(Inventory)

    if reference:
        query = query.where(Inventory.reference.contains(reference))
    if category:
        query = query.where(Inventory.category.contains(category))
    if size:
        query = query.where(Inventory.size.contains(size))

    db_items = session.exec(query).all()
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
    "/bookings",
    response_model=BookingRead,
    dependencies=[Depends(get_current_user)],
    summary="Create new booking",
    response_description="Booking data",
    tags=["Bookings"],
)
def create_booking(booking: BookingCreate, session: Session = Depends(get_session)):
    """Create new booking if item is available during requested time.
    - **item_id**: Item requested
    - **start_time**: Start time of booking (datetime)
    - **end_time**: End time of booking (datetime)
    """
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
    summary="Update existing booking",
    response_description="Updated booking data",
    tags=["Bookings"],
)
def update_booking(
    id: int,
    updated_booking: BookingCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Update an existing booking with a new request body (to change booking time or item)
    - **id**: Booking ID
    """
    db_booking = session.get(Booking, id)
    if not db_booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if db_booking.user_id != current_user.id and not is_admin(current_user):
        raise HTTPException(
            status_code=401, detail="Not authorised to change someone else's booking"
        )
    for key, value in updated_booking.model_dump(exclude_unset=True).items():
        setattr(db_booking, key, value)
    session.commit()
    session.refresh(db_booking)
    return db_booking


@app.delete(
    "/bookings/{id}",
    dependencies=[Depends(get_current_user)],
    summary="Delete booking",
    tags=["Bookings"],
)
def delete_booking(
    id: int,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    """
    Cancel existing booking. Use /bookings/put to update instead.
    -**id**: Booking ID.
    """
    db_booking = session.get(Booking, id)
    if not db_booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if db_booking.user_id != current_user.id and not is_admin(current_user):
        raise HTTPException(
            status_code=401, detail="Not authorised to delete someone else's booking"
        )
    session.delete(db_booking)
    session.commit()
    return {"ok": True}


@app.get(
    "/bookings",
    response_model=list[BookingRead],
    dependencies=[Depends(get_current_user)],
    summary="List all bookings",
    response_description="List of bookings",
    tags=["Bookings"],
)
def list_bookings(
    session: Session = Depends(get_session),
    datetime_from: Optional[datetime] = Query(
        datetime.now(), description="Select bookings from"
    ),
    datetime_until: Optional[datetime] = Query(
        datetime.now(), description="Select bookings until"
    ),
    item_id: Optional[int] = Query(None, description="Item ID to check bookings for"),
    user_id: Optional[int] = Query(None, description="Show only certain user"),
):
    """List all bookings with optional filter on start time/date, end time date, item, and user.
    - **datetime_from**: Optional filter for earliest bookings to show
    - **datetime_until**: Optional filter for latest bookings to show
    - **item_id**: Optional filter for which item to show bookings for
    - **user_id**: Optional filter for which user to show bookings for
    """

    query = select(Booking)

    if datetime_from:
        query = query.where(Booking.start_time >= datetime_from)
    if datetime_until:
        query = query.where(Booking.end_time <= datetime_until)
    if item_id:
        query = query.where(Booking.item_id == item_id)
    if user_id:
        query = query.where(Booking.user_id == user_id)

    return session.exec(query).all()
