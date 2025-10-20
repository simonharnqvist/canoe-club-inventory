import reflex as rx
from dataclasses import dataclass
from datetime import datetime
import httpx
import os
from urllib.parse import urljoin

from rxconfig import config

BACKEND_URL = os.getenv("BACKEND_URI")
LOGIN_URL = urljoin(BACKEND_URL, "/login")


@dataclass
class Booking:
    craft_id: int
    start_date: datetime
    start_time: datetime
    end_date: datetime
    end_time: datetime
    booker_name: str
    booker_email: str
    payment: str


class State(rx.State):
    is_authenticated: bool = False
    bookings: list[Booking] = []
    user: dict | None = None
    error: str | None = None

    async def on_load(self):
        await self.get_current_user()
        if self.is_authenticated:
            await self.get_bookings()

    async def get_current_user(self):
        async with httpx.AsyncClient(cookies=self.cookies) as client:
            try:
                response = await client.get(f"{BACKEND_URL}/me")
                response.raise_for_status()
                self.user = response.json()
                self.is_authenticated = True
            except Exception as e:
                self.is_authenticated = False
                self.error = str(e)

    async def get_bookings(self):
        async with httpx.AsyncClient(cookies=self.cookies) as client:
            try:
                response = await client.get(f"{BACKEND_URL}/bookings")
                response.raise_for_status()
                self.bookings = [Booking(**b) for b in response.json()]
            except Exception as e:
                self.error = str(e)
                self.bookings = []

    async def add_booking(self, form_data: dict):
        async with httpx.AsyncClient(cookies=self.cookies) as client:
            try:
                response = await client.post(f"{BACKEND_URL}/bookings", json=form_data)
                response.raise_for_status()
                await self.get_bookings()
            except Exception as e:
                self.error = str(e)

    async def edit_booking(self, booking_id: int, form_data: dict):
        async with httpx.AsyncClient(cookies=self.cookies) as client:
            try:
                response = await client.put(
                    f"{BACKEND_URL}/bookings/{booking_id}", json=form_data
                )
                response.raise_for_status()
                await self.get_bookings()
            except Exception as e:
                self.error = str(e)

    async def delete_booking(self, booking_id: int):
        async with httpx.AsyncClient(cookies=self.cookies) as client:
            try:
                response = await client.delete(f"{BACKEND_URL}/bookings/{booking_id}")
                response.raise_for_status()
                await self.get_bookings()
            except Exception as e:
                self.error = str(e)


# --- UI Components ---
def show_booking(booking: Booking):
    return rx.table.row(
        rx.table.cell(booking.craft_id),
        rx.table.cell(booking.start_date),
        rx.table.cell(booking.start_time),
        rx.table.cell(booking.end_date),
        rx.table.cell(booking.end_time),
        rx.table.cell(booking.booker_name),
        rx.table.cell(booking.booker_email),
        rx.table.cell(booking.payment),
    )


def login_redirect():
    return rx.fragment(
        rx.script(f"window.location.href = '{LOGIN_URL}';"),
        rx.link("Click here if not redirected", href=LOGIN_URL),
    )


def add_booking_button():
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=26), rx.text("Add booking", size="4"))
        ),
        rx.dialog.content(
            rx.dialog.title("Add new booking"),
            rx.form(
                rx.flex(
                    rx.input(placeholder="Craft ID", name="craft_id", required=True),
                    rx.text("Start"),
                    rx.input(type="date", name="start_date", required=True),
                    rx.input(type="time", name="start_time", required=True),
                    rx.text("End"),
                    rx.input(type="date", name="end_date", required=True),
                    rx.input(type="time", name="end_time", required=True),
                    rx.text("Booker"),
                    rx.input(
                        name="booker_name", placeholder="Your Name", required=True
                    ),
                    rx.input(
                        name="booker_email", placeholder="you@email.com", required=True
                    ),
                    rx.select(
                        [
                            "Clubhouse card machine",
                            "Annual equipment hire",
                            "Volunteer/exempt",
                        ],
                        placeholder="Payment method",
                        name="payment",
                        required=True,
                    ),
                    rx.flex(
                        rx.dialog.close(
                            rx.button("Cancel", variant="soft", color_scheme="gray")
                        ),
                        rx.dialog.close(rx.button("Submit", type="submit")),
                        spacing="3",
                        justify="end",
                    ),
                    direction="column",
                    spacing="4",
                ),
                on_submit=State.add_booking,
                reset_on_submit=False,
            ),
            max_width="450px",
        ),
    )


# --- Pages ---
def index() -> rx.Component:
    return rx.box(
        rx.cond(
            State.is_authenticated,
            rx.vstack(
                rx.text(
                    f"Welcome {State.user.get('username')}", weight="bold", size="5"
                ),
                add_booking_button(),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("Craft ID"),
                            rx.table.column_header_cell("Start date"),
                            rx.table.column_header_cell("Start time"),
                            rx.table.column_header_cell("End date"),
                            rx.table.column_header_cell("End time"),
                            rx.table.column_header_cell("Booker"),
                            rx.table.column_header_cell("Email"),
                            rx.table.column_header_cell("Payment"),
                        )
                    ),
                    rx.table.body(rx.foreach(State.bookings, show_booking)),
                    variant="surface",
                    size="3",
                    width="100%",
                ),
            ),
            login_redirect(),
        )
    )


# --- App Setup ---
app = rx.App()
app.add_page(index)
