from sqlmodel import create_engine, Session

import os

DATABASE_URL = os.getenv("POSTGRES_URI")
if not DATABASE_URL or DATABASE_URL == "":
    raise ValueError("DATABASE URL not set")

engine = create_engine(DATABASE_URL, echo=True)


def get_session():
    with Session(engine) as session:
        yield session
