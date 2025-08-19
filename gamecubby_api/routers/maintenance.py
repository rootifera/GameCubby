from __future__ import annotations

import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..utils.maintenance import (
    get_status_dict,
    enter_maintenance as _enter_maintenance,
    exit_maintenance as _exit_maintenance,
)

try:
    from ..db import engine as _db_engine  # type: ignore
except Exception:
    _db_engine = None

router = APIRouter(prefix="/admin/maintenance", tags=["maintenance"])


@router.get("/status")
def maintenance_status():
    """
    Return current maintenance status (no DB access).
    """
    return get_status_dict()


@router.post("/enter")
def maintenance_enter():
    """
    Enable maintenance mode (idempotent), then dispose DB pools (best-effort).
    """
    st = _enter_maintenance(reason="restore", by="api")

    try:
        if _db_engine is not None:
            _db_engine.dispose()
    except Exception as e:
        logging.warning(f"[maintenance_enter] engine.dispose() failed: {e}")

    return JSONResponse(
        content={
            "ok": True,
            "enabled": st.enabled,
            "reason": st.reason,
            "by": st.by,
            "started_at": st.started_at,
            "allow": st.allow,
        },
        status_code=200,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/exit")
def maintenance_exit():
    """
    Disable maintenance mode (idempotent).
    """
    st = _exit_maintenance()
    return JSONResponse(
        content={"ok": True, "enabled": st.enabled},
        status_code=200,
        headers={"Cache-Control": "no-store"},
    )
