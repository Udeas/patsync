from sqlmodel import SQLModel, create_engine, Session, select
from app.core.config import settings

# This now pulls automatically from your .env via the config file
engine = create_engine(settings.DATABASE_URL)

def test_connection():
    try:
        with Session(engine) as session:
            session.execute(select(1))
        print("✅ Database connection successful!")
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    test_connection()