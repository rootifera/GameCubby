from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..schemas.setup import FirstRunRequest
from ..utils.setup import perform_first_run_setup, is_first_run_done

router = APIRouter(prefix="/first_run", tags=["Setup"])


@router.post("")
def first_run(payload: FirstRunRequest, db: Session = Depends(get_db)):
    try:
        perform_first_run_setup(
            db=db,
            admin_username=payload.admin_username,
            admin_password=payload.admin_password,
            igdb_client_id=payload.igdb_client_id,
            igdb_client_secret=payload.igdb_client_secret,
            query_limit=payload.query_limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True, "message": "Initial setup complete"}


@router.get("/status", response_model=bool)
def first_run_status(db: Session = Depends(get_db)) -> bool:
    """
    Returns True if initial setup has been completed, otherwise False.
    """
    return is_first_run_done(db)