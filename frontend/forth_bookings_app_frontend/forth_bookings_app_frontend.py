import reflex as rx
from dataclasses import dataclass
from datetime import datetime
import httpx
import os

from rxconfig import config

BACKEND_URL = os.getenv("BACKEND_URI")


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

    token: str | None = None
    bookings: list[Booking] = []
    backend_url = BACKEND_URL
    error: str | None = None

    def start_login(self):
        rx.redirect(f"{self.backend_url}/login")

    async def handle_callback(self, code: str):

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{BACKEND_URL}/callback?code={code}")
                response.raise_for_status()
                self.token = response.json().get("access_token")
        except Exception as e:
            self.error = str(e)

    async def get_bookings(self):
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self.backend_url)
                response.raise_for_status()
                self.bookings = [Booking(**b) for b in response.json()]
            except Exception as e:
                print(f"Failed to retrieve bookings: {e}")
                self.bookings = []

    async def add_booking(self, form_data: dict):
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.backend_url, json=form_data)
                response.raise_for_status()
                await self.get_bookings()
            except Exception as e:
                print(f"Failed to add booking: {e}")

    async def edit_booking(self, booking_id: int, form_data: dict):
        url = f"{self.backend_url}/{booking_id}"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(url, json=form_data)
                response.raise_for_status()
                await self.get_bookings()
            except Exception as e:
                print(f"Failed to update booking: {e}")

    async def delete_booking(self, booking_id: int):
        url = f"{self.backend_url}/{booking_id}"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.delete(url)
                response.raise_for_status()
                await self.get_bookings()
            except Exception as e:
                print(f"Failed to delete booking: {e}")


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


def login_button():
    return rx.button("Login", on_click=State.start_login)


def callback_page(code: str | None = None):
    if code:
        # Trigger the mutation directly from server-side
        State.handle_callback(code)

    return rx.fragment(
        rx.text("Handling login callback..."),
        rx.cond(State.error, rx.text(State.error)),
    )


def add_booking_button() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("plus", size=26), rx.text("Add booking", size="4"))
        ),
        rx.dialog.content(
            rx.dialog.title("Add new booking"),
            rx.form(
                rx.flex(
                    rx.input(
                        placeholder="Craft name/reference",
                        name="craft_id",
                        required=True,
                    ),
                    rx.text("Start date and time"),
                    rx.input(type="date", name="start_date", required=True),
                    rx.input(type="time", name="start_time", required=True),
                    rx.text("End date and time"),
                    rx.input(type="date", name="end_date", required=True),
                    rx.input(type="time", name="end_time", required=True),
                    rx.text("Booker"),
                    rx.input(placeholder="My Name", name="booker_name", required=True),
                    rx.input(
                        placeholder="email@gmail.com",
                        name="booker_email",
                        required=True,
                    ),
                    rx.select(
                        [
                            "Clubhouse card machine",
                            "Annual equipment hire",
                            "Volunteer/exempt",
                        ],
                        placeholder="Select payment method",
                        name="payment",
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


def index() -> rx.Component:
    return rx.vstack(
        rx.button("Login", on_click=State.start_login),
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
                    rx.table.column_header_cell("Payment method"),
                )
            ),
            rx.table.body(rx.foreach(State.bookings, show_booking)),
            variant="surface",
            size="3",
            width="100%",
        ),
    )


app = rx.App()
app.add_page(index)
