from contextlib import contextmanager
from ..db import get_db
from sqlalchemy.orm import Session


@contextmanager
def with_db() -> Session:
    """
    Safely open and close a DB session.
    Use this in utils or anywhere outside FastAPI's Depends().
    Example:

        with with_db() as db:
            ...
    """
    db_gen = get_db()
    db = next(db_gen)
    try:
        yield db
    finally:
        db_gen.close()
