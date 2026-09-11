import os
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import sessionmaker

DB_HOST = os.getenv("DB_HOST", "gamecubby-db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "gamecubby")
DB_USER = os.getenv("DB_USER", "gamecubby")
DB_PASSWORD = os.getenv("DB_PASSWORD", "gamecubby")

POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "5"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))
POOL_PRE_PING = os.getenv("DB_POOL_PRE_PING", "true").lower() == "true"
POOL_USE_LIFO = os.getenv("DB_POOL_USE_LIFO", "true").lower() == "true"

DATABASE_URL = URL.create(
    "postgresql",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=int(DB_PORT),
    database=DB_NAME,
)

engine = create_engine(
    DATABASE_URL,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_timeout=POOL_TIMEOUT,
    pool_recycle=POOL_RECYCLE,
    pool_pre_ping=POOL_PRE_PING,
    pool_use_lifo=POOL_USE_LIFO,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
