from sqlmodel import SQLModel, Field
import datetime
from typing import Optional


class Inventory(SQLModel, table=True):
    reference: Optional[str] = Field(default=None, primary_key=True)
    category: str  # craft, paddle, BA, spraydeck, other
    size: str | None = None


class Booking(SQLModel, table=True):
    user_id: int = Field(default=None, primary_key=True)
    item_id: int
    start_time: datetime.datetime
    end_time: datetime.datetime
