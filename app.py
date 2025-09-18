from fastapi import FastAPI, HTTPException
from models import Inventory, Users, Bookings
from sqlmodel import Session, select, SQLModel, create_engine
import os
import datetime

app = FastAPI()

POSTGRES_URI: str = os.getenv("POSTGRES_URI")  # type:ignore
engine = create_engine(POSTGRES_URI)


@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)


@app.post("/inventory", response_model=Inventory)
def create_item(item: Inventory):
    with Session(engine) as session:
        session.add(item)
        session.commit()
        session.refresh(item)
        return item


@app.put("/inventory/{id}", response_model=Inventory)
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


@app.delete("/inventory/{id}")
def delete_item(id: int):
    with Session(engine) as session:
        item = session.get(Inventory, id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        session.delete(item)
        session.commit()
        return {"ok": True}


@app.get("/inventory", response_model=list[Inventory])
def list_items(
    id: int | None = None,
    category: str | None = None,
    craft_type: str | None = None,
    size: str | None = None,
    num_seats: int | None = None,
):
    with Session(engine) as session:
        return session.exec(select(Inventory)).all()


@app.post("/users", response_model=Users)
def create_user(user: Users):
    with Session(engine) as session:
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@app.put("/users/{id}", response_model=Users)
def update_user(id: int, updated_user: Users):
    with Session(engine) as session:
        user = session.get(Users, id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        for key, value in updated_user.dict(exclude_unset=True).items():
            setattr(user, key, value)
        session.commit()
        session.refresh(user)
        return user


@app.delete("/users/{id}")
def delete_user(id: int):
    with Session(engine) as session:
        user = session.get(Users, id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        session.delete(user)
        session.commit()
        return {"ok": True}


@app.get("/users", response_model=list[Users])
def list_users():
    with Session(engine) as session:
        return session.exec(select(Users)).all()


@app.post("/bookings", response_model=Bookings)
def create_booking(booking: Bookings):
    with Session(engine) as session:
        session.add(booking)
        session.commit()
        session.refresh(booking)
        return booking


@app.put("/bookings/{id}", response_model=Bookings)
def update_booking(id: int, updated_booking: Bookings):
    with Session(engine) as session:
        booking = session.get(Bookings, id)
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        for key, value in updated_booking.dict(exclude_unset=True).items():
            setattr(booking, key, value)
        session.commit()
        session.refresh(booking)
        return booking


@app.delete("/bookings/{id}")
def delete_booking(id: int):
    with Session(engine) as session:
        booking = session.get(Bookings, id)
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")
        session.delete(booking)
        session.commit()
        return {"ok": True}


@app.get("/bookings", response_model=list[Bookings])
def list_bookings(
    id: int | None = None,
    item_id: int | None = None,
    user_id: int | None = None,
    start_time: datetime.datetime | None = None,
    end_time: datetime.datetime | None = None,
):
    with Session(engine) as session:
        return session.exec(select(Bookings)).all()
