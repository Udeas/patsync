from sqlmodel import SQLModel, create_engine, Session
import os
from dotenv import load_dotenv

load_dotenv()

sqlite_url = os.getenv("DATABASE_URL")
engine = create_engine(sqlite_url, echo=True)

def get_session():
    with Session(engine) as session:
        yield session
