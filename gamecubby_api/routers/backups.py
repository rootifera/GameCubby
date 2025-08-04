from fastapi.responses import StreamingResponse
from ..utils.backup import create_backup
from ..utils.auth import get_current_admin
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/backup", tags=["Backup"])


@router.get("/", response_class=StreamingResponse, dependencies=[Depends(get_current_admin)])
async def backup_database():
    return create_backup()
