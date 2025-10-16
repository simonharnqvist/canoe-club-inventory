import reflex as rx

config = rx.Config(
    app_name="forth_bookings_app_frontend",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ]
)