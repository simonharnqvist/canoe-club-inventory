from sqlmodel import SQLModel, create_engine, Session
import os

DATABASE_URL = os.getenv("POSTGRES_URI")

engine = create_engine(DATABASE_URL, echo=True)


def get_session():
    with Session(engine) as session:
        yield session
