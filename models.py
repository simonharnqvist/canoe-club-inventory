from sqlmodel import SQLModel, Field
import datetime


class Users(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    first_name: str
    surname: str
    email: str
    membership_no: int | None = None


class Inventory(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    reference: str
    category: str  # craft, paddle, BA, spraydeck, other
    craft_type: str  # kayak, canoe, SUP, not applicable
    size: str | None = None
    num_seats: int | None = None


class Bookings(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int
    item_id: int
    start_time: datetime.datetime
    end_time: datetime.datetime
