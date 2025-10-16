from sqlmodel import SQLModel, Field
import datetime


class Inventory(SQLModel, table=True):
    reference: str
    category: str  # craft, paddle, BA, spraydeck, other
    size: str | None = None


class Booking(SQLModel, table=True):
    user_id: int
    item_id: int
    start_time: datetime.datetime
    end_time: datetime.datetime
