from sqlmodel import SQLModel, Field
import datetime
from typing import Optional


############
# USER MODEL
############


class UserBase(SQLModel):
    username: str = Field(index=True)
    email: str = Field(index=True)


class User(UserBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hashed_password: str


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int

    class Config:
        orm_mode = True


class UserLogin(SQLModel):
    username: str
    password: str


################
# INVENTORY MODEL
################


class InventoryBase(SQLModel):
    reference: str
    category: str
    size: str


class Inventory(InventoryBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)


class InventoryCreate(InventoryBase):
    pass


class InventoryRead(InventoryBase):
    id: int

    class Config:
        orm_mode = True


###############
# BOOKING MODEL
###############


class BookingBase(SQLModel):
    user_id: int
    item_id: int
    start_time: datetime.datetime
    end_time: datetime.datetime


class Booking(BookingBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)


class BookingCreate(BookingBase):
    pass


class BookingRead(BookingBase):
    id: int

    class Config:
        orm_mode = True
