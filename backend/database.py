import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

load_dotenv()

# Reads the DATABASE_URL from your .env file
# If it's missing we crash immediately with a clear message
# rather than some confusing error later
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set. Add it to your .env file.")


# The engine is the actual connection to your Neon database
# pool_pre_ping=True means: before using a connection, check it's still alive
# Important because Neon goes to sleep after inactivity and connections go stale
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


# SessionLocal is a factory — calling SessionLocal() gives you a fresh session
# A session is like an open conversation with the database
# autocommit=False means nothing is saved until you explicitly call commit()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


# This is what your API endpoints will use to get a database session
# The yield keyword means: give the session to the endpoint, then after
# the endpoint finishes, the finally block closes the session automatically
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Creates all tables in your database based on your models
# Safe to run multiple times — it won't drop existing tables
def create_tables():
    from models import Base
    Base.metadata.create_all(bind=engine)
    print("All tables created.")


# Quick sanity check — run this to confirm Neon is reachable
def test_connection():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Database connection successful.")
    except Exception as e:
        print(f"Database connection failed: {e}")