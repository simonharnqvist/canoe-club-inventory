# fastapi-club-inventory
Inventory/booking backend for a sports club, e.g. a canoe club.

One of my main hobbies is kayaking, and the clubs I am in sometimes discuss setting up a more formalised booking and inventory management system to keep track of where the kit has gone. This is a prototype backend for such an application.

## Data model
The data model looks something like this slightly sloppy ERD:

![alt text](erd.drawio.png "Logo Title Text 1")

This corresponds to three SQLModel/SQLAlchemy tables, unsurprisingly named 'Inventory', 'Bookings', and 'Users'.

## Stack

* **FastAPI** - main framework
* **SQLModel** - ORM
* **PostgresQL** - storage layer
* **Docker Compose** - database/application co-deployment

## Security
User authentication is done through OAuth2 with bearer tokens. See API docs.

## API docs
[Preview the HTML API docs](https://editor.swagger.io/?url=https://raw.githubusercontent.com/simonharnqvist/club-inventory/main/swagger.json)