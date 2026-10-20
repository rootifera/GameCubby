import os
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import sessionmaker

DB_HOST = os.getenv("DB_HOST", "gamecubby-db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "gamecubby")
DB_USER = os.getenv("DB_USER", "gamecubby")
DB_PASSWORD = os.getenv("DB_PASSWORD", "gamecubby")

# Per worker process. With 2 workers the defaults allow at most 40 connections, well
# inside PostgreSQL's default max_connections of 100 (which also serves backups/restores).
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
POOL_CAPACITY = POOL_SIZE + MAX_OVERFLOW
# How long a request waits for a free connection before giving up. Short on purpose: a
# request that can't get one in a few seconds should fail fast (the API answers 503 with
# Retry-After) instead of tying up a worker thread for 30 s.
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "10"))
# Upper bound for any single SQL statement, so one pathological query can't hold a
# connection forever. 0 disables. (Alembic migrations use their own engine, unaffected.)
STATEMENT_TIMEOUT_MS = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "30000"))
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
    connect_args={"options": f"-c statement_timeout={STATEMENT_TIMEOUT_MS}"} if STATEMENT_TIMEOUT_MS > 0 else {},
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
